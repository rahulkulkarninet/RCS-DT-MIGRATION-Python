from typing import Any, Dict, List, Tuple

import pandas as pd

import derived_mapping
import text_normalization

# Staging tables whose Payment_Method is mapped to a tblBankTransactionMethod ID. The
# source keeps the value sent; the ID goes in each table's derived column
# Payment_Method_BankTransactionMethodID, read by 48.tblbanktransaction.sql (RC_PAYMENTS),
# 76.tblarrangement.sql (RC_DEAL) and 78's arrangement insert (RC_ARRANGEMENT).
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
PAYMENT_METHOD_SOURCES: Tuple[Tuple[str, str], ...] = (
    ('RC_PAYMENTS', 'Payment_Method'),
    ('RC_DEAL', 'Payment_Method'),
    ('RC_ARRANGEMENT', 'Payment_Method'),
)
TARGET_COLUMN = 'Payment_Method_BankTransactionMethodID'

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
            frame = derived_mapping.read_distinct_values(db_helper, table, column, 'raw_method')
            if frame.empty:
                continue

            # dropna before astype(str), which would otherwise turn a NULL into 'None'.
            frame = frame.dropna(subset=['raw_method'])
            frame['raw_method'] = frame['raw_method'].astype(str)
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

    def target_columns_missing(self) -> List[str]:
        """'table.column' for each present source table lacking its derived column."""
        return [
            f'{table}.{TARGET_COLUMN}'
            for table, _ in self.get_existing_sources()
            if not derived_mapping.column_exists(self.db_helper, table, TARGET_COLUMN)
        ]

    def bulk_update_payment_methods(self, resolution_frame: pd.DataFrame) -> Dict[str, int]:
        """Fill Payment_Method_BankTransactionMethodID per source; Payment_Method is only read.

        Every present source is processed, even one with nothing resolved, so its
        column is cleared rather than left holding an earlier run's IDs.
        """
        rows_updated: Dict[str, int] = {}
        for table, column in self.get_existing_sources():
            pairs = (
                []
                if resolution_frame.empty
                else resolution_frame.loc[
                    resolution_frame['source_table'] == table,
                    ['raw_method', 'bank_transaction_method_id'],
                ].itertuples(index=False, name=None)
            )
            mapped, _ = derived_mapping.assign_ids(
                self.db_helper, table, column, TARGET_COLUMN, pairs
            )
            rows_updated[table] = mapped
        return rows_updated

    def get_invalid_payment_methods_from_db(self) -> Dict[str, List[str]]:
        """Post-update re-check: non-blank Payment_Method values left without an ID."""
        invalid_by_table: Dict[str, List[str]] = {}
        for table, column in self.get_existing_sources():
            values = derived_mapping.read_unresolved_values(
                self.db_helper, table, column, TARGET_COLUMN
            )
            if values:
                invalid_by_table[table] = values
        return invalid_by_table
