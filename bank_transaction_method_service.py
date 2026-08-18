from typing import Any, Dict, List, Tuple

import pandas as pd

import text_normalization

# Staging tables whose Payment_Method column is rewritten in place to the canonical
# tblBankTransactionMethod label, the same way RC_ACCOUNT_EXTRACT.MA_Status is rewritten
# to the tblAccountStatus label. These feed 48.tblbanktransaction.sql, 49.tblpayment.sql
# and 75.tblarrangement.sql.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
PAYMENT_METHOD_SOURCES: Tuple[Tuple[str, str], ...] = (
    ('RC_PAYMENTS', 'Payment_Method'),
    ('RC_DEAL', 'Payment_Method'),
    ('RC_ARRANGEMENT', 'Payment_Method'),
)

LOOKUP_TABLE = 'tblBankTransactionMethod'
LOOKUP_ID_COLUMN = 'BankTransactionMethodID'
LOOKUP_LABEL_COLUMN = 'BankTransactionMethod'


class BankTransactionMethodService:
    """Encapsulates Payment_Method mapping, normalization, and validation logic."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_bank_transaction_method_mapping_frame(
        self,
        method_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in method_mapping.items():
            if not isinstance(codes, list):
                continue

            target_label = str(label).strip()
            normalized_target = text_normalization.normalize_lookup_key(target_label)

            for code in codes:
                if code is None:
                    continue

                normalized_code = text_normalization.normalize_lookup_key(code)
                if not normalized_code:
                    continue

                if normalized_code in seen_codes:
                    duplicate_codes += 1
                    continue

                seen_codes.add(normalized_code)
                rows.append(
                    {
                        'source_code': str(code).strip(),
                        'normalized_source': normalized_code,
                        'source_key': text_normalization.match_key(normalized_code),
                        'target_label': target_label,
                        'normalized_target': normalized_target,
                        'target_key': text_normalization.match_key(normalized_target),
                    }
                )

        return pd.DataFrame(rows), duplicate_codes

    def get_existing_sources(self) -> Tuple[Tuple[str, str], ...]:
        """Restrict to source tables that actually exist; a customer need not have all three."""
        db_helper = self.db_helper
        if not db_helper:
            return ()

        table_names = ', '.join(f"'{table}'" for table, _ in PAYMENT_METHOD_SOURCES)
        present = db_helper.execute_query(
            f'SELECT name FROM sys.tables WHERE name IN ({table_names})'
        )
        if present.empty or 'name' not in present.columns:
            return ()

        found = {str(name).upper() for name in present['name'].dropna().tolist()}
        return tuple((table, column) for table, column in PAYMENT_METHOD_SOURCES
                     if table.upper() in found)

    def build_payment_method_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        empty_columns = ['source_table', 'raw_method', 'bank_transaction_method_id']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_methods = self.read_source_payment_methods()
        if source_methods.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return (
                pd.DataFrame(columns=empty_columns),
                sorted(source_methods['raw_method'].drop_duplicates().tolist()),
            )

        source_methods['normalized_method'] = text_normalization.normalize_lookup_series(
            source_methods['raw_method']
        )
        source_methods['method_key'] = text_normalization.match_key_series(
            source_methods['normalized_method']
        )

        lookup_frame['normalized_lookup'] = text_normalization.normalize_lookup_series(
            lookup_frame[LOOKUP_LABEL_COLUMN]
        )
        lookup_frame['method_key'] = text_normalization.match_key_series(
            lookup_frame['normalized_lookup']
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['method_key'], keep='first')

        resolved_frame = source_methods.merge(
            lookup_frame[['method_key', LOOKUP_ID_COLUMN]].rename(
                columns={LOOKUP_ID_COLUMN: 'direct_method_id'}
            ),
            on='method_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']] if not mapping_frame.empty
            else pd.DataFrame(columns=['source_key', 'target_key']),
            left_on='method_key',
            right_on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['method_key', LOOKUP_ID_COLUMN]].rename(
                columns={'method_key': 'target_key', LOOKUP_ID_COLUMN: 'mapped_method_id'}
            ),
            on='target_key',
            how='left',
        )

        # A raw value that already matches a tblBankTransactionMethod label wins over
        # whatever the JSON maps it to, mirroring the account status precedence.
        resolved_frame['resolved_method_id'] = resolved_frame['mapped_method_id']
        resolved_frame.loc[
            resolved_frame['direct_method_id'].notna(),
            'resolved_method_id',
        ] = resolved_frame['direct_method_id']

        invalid_methods = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_method_id'].isna(),
                'raw_method',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_method_id'].notna(),
            ['source_table', 'raw_method', 'resolved_method_id'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={'resolved_method_id': 'bank_transaction_method_id'}
        )
        resolution_frame['bank_transaction_method_id'] = (
            resolution_frame['bank_transaction_method_id'].astype(int)
        )

        return resolution_frame, invalid_methods

    def read_source_payment_methods(self) -> pd.DataFrame:
        """Distinct non-empty Payment_Method values across every present source table."""
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=['source_table', 'raw_method'])

        frames: List[pd.DataFrame] = []
        for table, column in self.get_existing_sources():
            frame = db_helper.execute_query(
                f"""
                SELECT DISTINCT CAST({column} AS NVARCHAR(4000)) AS raw_method
                FROM {table}
                WHERE {column} IS NOT NULL
                """
            )
            if frame.empty or 'raw_method' not in frame.columns:
                continue

            # dropna before astype(str), which would otherwise turn a NULL that slipped
            # past the IS NOT NULL predicate into the literal string 'None'.
            frame = frame.dropna(subset=['raw_method'])
            frame['raw_method'] = frame['raw_method'].astype(str).str.strip()
            frame = frame[frame['raw_method'] != ''].copy()
            if frame.empty:
                continue

            frame['source_table'] = table
            frames.append(frame[['source_table', 'raw_method']])

        if not frames:
            return pd.DataFrame(columns=['source_table', 'raw_method'])

        return pd.concat(frames, ignore_index=True)

    def read_lookup_frame(self) -> pd.DataFrame:
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=[LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN])

        lookup_frame = db_helper.execute_query(
            f"""
            SELECT {LOOKUP_ID_COLUMN},
                   CAST({LOOKUP_LABEL_COLUMN} AS NVARCHAR(4000)) AS {LOOKUP_LABEL_COLUMN}
            FROM {LOOKUP_TABLE}
            WHERE {LOOKUP_LABEL_COLUMN} IS NOT NULL
            """
        )
        if lookup_frame.empty or LOOKUP_LABEL_COLUMN not in lookup_frame.columns:
            return pd.DataFrame(columns=[LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN])

        lookup_frame[LOOKUP_LABEL_COLUMN] = (
            lookup_frame[LOOKUP_LABEL_COLUMN].astype(str).str.strip()
        )
        return lookup_frame[lookup_frame[LOOKUP_LABEL_COLUMN] != ''].copy()

    def bulk_update_payment_methods(self, resolution_frame: pd.DataFrame) -> Dict[str, int]:
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection or resolution_frame.empty:
            return {}

        source_columns = dict(PAYMENT_METHOD_SOURCES)
        rows_updated: Dict[str, int] = {}
        cursor = db_helper.pyodbc_connection.cursor()

        try:
            # Shared sessions can process multiple customers; clear any prior temp table safely.
            cursor.execute(
                "IF OBJECT_ID('tempdb..#PaymentMethodResolution') IS NOT NULL "
                'DROP TABLE #PaymentMethodResolution'
            )
            cursor.execute(
                """
                CREATE TABLE #PaymentMethodResolution (
                    source_table NVARCHAR(128) NOT NULL,
                    raw_method NVARCHAR(4000) NOT NULL,
                    bank_transaction_method_id INT NOT NULL
                )
                """
            )
            cursor.executemany(
                'INSERT INTO #PaymentMethodResolution '
                '(source_table, raw_method, bank_transaction_method_id) VALUES (?, ?, ?)',
                list(
                    resolution_frame[
                        ['source_table', 'raw_method', 'bank_transaction_method_id']
                    ].itertuples(index=False, name=None)
                ),
            )

            for table in resolution_frame['source_table'].drop_duplicates().tolist():
                column = source_columns.get(table)
                if not column:
                    continue

                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{column} = t.{LOOKUP_LABEL_COLUMN}
                    FROM {table} AS rc
                    INNER JOIN #PaymentMethodResolution AS pr
                        ON CAST(rc.{column} AS NVARCHAR(4000)) = pr.raw_method
                        AND pr.source_table = '{table}'
                    INNER JOIN {LOOKUP_TABLE} AS t
                        ON t.{LOOKUP_ID_COLUMN} = pr.bank_transaction_method_id
                    WHERE rc.{column} <> t.{LOOKUP_LABEL_COLUMN}
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated[table] = int(row[0]) if row and row[0] is not None else 0

            cursor.execute('DROP TABLE #PaymentMethodResolution')

            db_helper.pyodbc_connection.commit()
            return rows_updated

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    def get_invalid_payment_methods_from_db(self) -> Dict[str, List[str]]:
        """Post-update re-check: staging values with no tblBankTransactionMethod match."""
        db_helper = self.db_helper
        if not db_helper:
            return {}

        source_methods = self.read_source_payment_methods()
        if source_methods.empty:
            return {}

        lookup_frame = self.read_lookup_frame()
        source_methods['method_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_methods['raw_method'])
        )

        if lookup_frame.empty:
            lookup_keys = set()
        else:
            lookup_keys = set(
                text_normalization.match_key_series(
                    text_normalization.normalize_lookup_series(
                        lookup_frame[LOOKUP_LABEL_COLUMN]
                    )
                )
                .dropna()
                .tolist()
            )

        invalid = source_methods[~source_methods['method_key'].isin(lookup_keys)]

        invalid_by_table: Dict[str, List[str]] = {}
        for table, group in invalid.groupby('source_table'):
            values = sorted(group['raw_method'].drop_duplicates().tolist())
            if values:
                invalid_by_table[str(table)] = values

        return invalid_by_table
