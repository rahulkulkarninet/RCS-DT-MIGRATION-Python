from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Staging column rewritten in place to the canonical tblComplainant label, the same way
# RC_ACCOUNT_EXTRACT.MA_Status is rewritten to the tblAccountStatus label. Feeds the
# ComplainantId lookup in 78.tblComplaint.sql.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_COMPLAINT_EXTRACT'
SOURCE_COLUMN = 'CMP_Source'

LOOKUP_TABLE = 'tblComplainant'
LOOKUP_ID_COLUMN = 'ComplainantId'
LOOKUP_LABEL_COLUMN = 'Name'


class ComplainantService:
    """Encapsulates CMP_Source mapping, normalization, and validation logic.

    tblComplainant has no pre-existing rows for a new client, unlike
    tblAccountStatus/tblClosureReason/etc., so unlike those there is no built-in
    catch-all to fall back to - default_for_unmapped only takes effect once a
    real row with that label has been added to tblComplainant.
    """

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_complainant_mapping_frame(
        self,
        complainant_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in complainant_mapping.items():
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

    def source_table_exists(self) -> bool:
        """Not every customer has complaints, unlike RC_ACCOUNT_EXTRACT which always exists."""
        db_helper = self.db_helper
        if not db_helper:
            return False

        present = db_helper.execute_query(
            f"SELECT 1 AS found WHERE OBJECT_ID('{SOURCE_TABLE}') IS NOT NULL"
        )
        return not present.empty

    def read_source_complainants(self) -> pd.DataFrame:
        """Distinct non-null, non-blank CMP_Source values."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['raw_source'])

        frame = db_helper.execute_query(
            f"""
            SELECT DISTINCT CAST({SOURCE_COLUMN} AS NVARCHAR(4000)) AS raw_source
            FROM {SOURCE_TABLE}
            WHERE {SOURCE_COLUMN} IS NOT NULL
              AND LTRIM(RTRIM({SOURCE_COLUMN})) <> ''
            """
        )
        if frame.empty or 'raw_source' not in frame.columns:
            return pd.DataFrame(columns=['raw_source'])

        frame = frame.dropna(subset=['raw_source'])
        frame['raw_source'] = frame['raw_source'].astype(str).str.strip()
        return frame[frame['raw_source'] != ''].copy()

    def resolve_fallback_label(self, fallback_label: Optional[str]) -> Optional[str]:
        """Match the configured fallback against tblComplainant, returning its exact label.

        Returns None when the fallback is switched off (blank in the JSON) or when the
        configured label is not present in the lookup table - which for a new client
        means every unmapped CMP_Source value is reported invalid until a real
        tblComplainant row (and JSON entry) exists for it.
        """
        if not fallback_label or not str(fallback_label).strip():
            return None

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return None

        wanted_key = text_normalization.match_key(
            text_normalization.normalize_lookup_key(fallback_label)
        )
        lookup_frame['source_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[LOOKUP_LABEL_COLUMN])
        )
        matches = lookup_frame.loc[lookup_frame['source_key'] == wanted_key, LOOKUP_LABEL_COLUMN]
        if matches.empty:
            return None

        return str(matches.iloc[0])

    def build_complainant_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Returns (resolved values, values with no tblComplainant match)."""
        empty_columns = ['raw_source', 'complainant_id']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_values = self.read_source_complainants()
        if source_values.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return (
                pd.DataFrame(columns=empty_columns),
                sorted(source_values['raw_source'].drop_duplicates().tolist()),
            )

        source_values['normalized_source'] = text_normalization.normalize_lookup_series(
            source_values['raw_source']
        )
        source_values['source_key'] = text_normalization.match_key_series(
            source_values['normalized_source']
        )

        lookup_frame['normalized_lookup'] = text_normalization.normalize_lookup_series(
            lookup_frame[LOOKUP_LABEL_COLUMN]
        )
        lookup_frame['source_key'] = text_normalization.match_key_series(
            lookup_frame['normalized_lookup']
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['source_key'], keep='first')

        resolved_frame = source_values.merge(
            lookup_frame[['source_key', LOOKUP_ID_COLUMN]].rename(
                columns={LOOKUP_ID_COLUMN: 'direct_complainant_id'}
            ),
            on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']] if not mapping_frame.empty
            else pd.DataFrame(columns=['source_key', 'target_key']),
            on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['source_key', LOOKUP_ID_COLUMN]].rename(
                columns={'source_key': 'target_key', LOOKUP_ID_COLUMN: 'mapped_complainant_id'}
            ),
            on='target_key',
            how='left',
        )

        # A raw value that already matches a tblComplainant label wins over whatever the
        # JSON maps it to, mirroring the account status precedence.
        resolved_frame['resolved_complainant_id'] = resolved_frame['mapped_complainant_id']
        resolved_frame.loc[
            resolved_frame['direct_complainant_id'].notna(),
            'resolved_complainant_id',
        ] = resolved_frame['direct_complainant_id']

        invalid_values = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_complainant_id'].isna(),
                'raw_source',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_complainant_id'].notna(),
            ['raw_source', 'resolved_complainant_id'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={'resolved_complainant_id': 'complainant_id'}
        )
        resolution_frame['complainant_id'] = resolution_frame['complainant_id'].astype(int)

        return resolution_frame, invalid_values

    def bulk_update_complainants(
        self,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Rewrite mapped values, then sweep remaining non-null values to fallback_label.

        NULL and blank are never touched. Returns (rows_updated, rows_defaulted); both
        statements run in one transaction.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection or not self.source_table_exists():
            return 0, 0

        if resolution_frame.empty and not fallback_label:
            return 0, 0

        cursor = db_helper.pyodbc_connection.cursor()
        rows_updated = 0
        rows_defaulted = 0

        try:
            if not resolution_frame.empty:
                cursor.execute(
                    "IF OBJECT_ID('tempdb..#ComplainantResolution') IS NOT NULL "
                    'DROP TABLE #ComplainantResolution'
                )
                cursor.execute(
                    """
                    CREATE TABLE #ComplainantResolution (
                        raw_source NVARCHAR(4000) NOT NULL,
                        complainant_id INT NOT NULL
                    )
                    """
                )
                cursor.executemany(
                    'INSERT INTO #ComplainantResolution '
                    '(raw_source, complainant_id) VALUES (?, ?)',
                    list(
                        resolution_frame[['raw_source', 'complainant_id']].itertuples(
                            index=False, name=None
                        )
                    ),
                )
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = t.{LOOKUP_LABEL_COLUMN}
                    FROM {SOURCE_TABLE} AS rc
                    INNER JOIN #ComplainantResolution AS cr
                        ON CAST(rc.{SOURCE_COLUMN} AS NVARCHAR(4000)) = cr.raw_source
                    INNER JOIN {LOOKUP_TABLE} AS t
                        ON t.{LOOKUP_ID_COLUMN} = cr.complainant_id
                    WHERE rc.{SOURCE_COLUMN} <> t.{LOOKUP_LABEL_COLUMN}
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated = int(row[0]) if row and row[0] is not None else 0

                cursor.execute('DROP TABLE #ComplainantResolution')

            if fallback_label:
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = ?
                    FROM {SOURCE_TABLE} AS rc
                    WHERE rc.{SOURCE_COLUMN} IS NOT NULL
                      AND LTRIM(RTRIM(rc.{SOURCE_COLUMN})) <> ''
                      AND NOT EXISTS (
                            SELECT 1
                            FROM {LOOKUP_TABLE} AS t
                            WHERE t.{LOOKUP_LABEL_COLUMN} = rc.{SOURCE_COLUMN}
                          )
                    """,
                    fallback_label,
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_defaulted = int(row[0]) if row and row[0] is not None else 0

            db_helper.pyodbc_connection.commit()
            return rows_updated, rows_defaulted

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    def get_invalid_complainants_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblComplainant match."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_values = self.read_source_complainants()
        if source_values.empty:
            return []

        lookup_frame = self.read_lookup_frame()
        source_values['source_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_values['raw_source'])
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

        invalid = source_values[~source_values['source_key'].isin(lookup_keys)]
        return sorted(invalid['raw_source'].drop_duplicates().tolist())
