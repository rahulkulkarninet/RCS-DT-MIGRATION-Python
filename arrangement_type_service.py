from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Staging column rewritten in place to the canonical tblArrangementType label, the same
# way RC_ACCOUNT_EXTRACT.MA_Status is rewritten to the tblAccountStatus label. Feeds the
# ArrangementTypeID TODO in 75.tblarrangement.sql.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_ARRANGEMENT'
SOURCE_COLUMN = 'Arrangement_Type'

LOOKUP_TABLE = 'tblArrangementType'
LOOKUP_ID_COLUMN = 'ArrangementTypeID'
LOOKUP_LABEL_COLUMN = 'ArrangementType'


class ArrangementTypeService:
    """Encapsulates Arrangement_Type mapping, normalization, and validation logic."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_arrangement_type_mapping_frame(
        self,
        type_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in type_mapping.items():
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

    def source_table_exists(self) -> bool:
        db_helper = self.db_helper
        if not db_helper:
            return False

        present = db_helper.execute_query(
            f"SELECT name FROM sys.tables WHERE name = '{SOURCE_TABLE}'"
        )
        return not present.empty

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

    def read_source_arrangement_types(self) -> pd.DataFrame:
        """Distinct non-null, non-blank Arrangement_Type values."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['raw_type'])

        frame = db_helper.execute_query(
            f"""
            SELECT DISTINCT CAST({SOURCE_COLUMN} AS NVARCHAR(4000)) AS raw_type
            FROM {SOURCE_TABLE}
            WHERE {SOURCE_COLUMN} IS NOT NULL
            """
        )
        if frame.empty or 'raw_type' not in frame.columns:
            return pd.DataFrame(columns=['raw_type'])

        # dropna before astype(str), which would otherwise turn a NULL that slipped past
        # the IS NOT NULL predicate into the literal string 'None'.
        frame = frame.dropna(subset=['raw_type'])
        frame['raw_type'] = frame['raw_type'].astype(str).str.strip()
        return frame[frame['raw_type'] != ''].copy()

    def resolve_default_label(self, default_label: Optional[str]) -> Optional[str]:
        """Match the configured default against tblArrangementType, returning its exact label.

        Returns None when defaulting is switched off (blank in the JSON) or when the
        configured label is not present in the lookup table.
        """
        if not default_label or not str(default_label).strip():
            return None

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return None

        wanted_key = text_normalization.match_key(
            text_normalization.normalize_lookup_key(default_label)
        )
        lookup_frame['type_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[LOOKUP_LABEL_COLUMN])
        )
        matches = lookup_frame.loc[lookup_frame['type_key'] == wanted_key, LOOKUP_LABEL_COLUMN]
        if matches.empty:
            return None

        return str(matches.iloc[0])

    def build_arrangement_type_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        empty_columns = ['raw_type', 'arrangement_type_id']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_types = self.read_source_arrangement_types()
        if source_types.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return (
                pd.DataFrame(columns=empty_columns),
                sorted(source_types['raw_type'].drop_duplicates().tolist()),
            )

        source_types['normalized_type'] = text_normalization.normalize_lookup_series(
            source_types['raw_type']
        )
        source_types['type_key'] = text_normalization.match_key_series(
            source_types['normalized_type']
        )

        lookup_frame['normalized_lookup'] = text_normalization.normalize_lookup_series(
            lookup_frame[LOOKUP_LABEL_COLUMN]
        )
        lookup_frame['type_key'] = text_normalization.match_key_series(
            lookup_frame['normalized_lookup']
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['type_key'], keep='first')

        resolved_frame = source_types.merge(
            lookup_frame[['type_key', LOOKUP_ID_COLUMN]].rename(
                columns={LOOKUP_ID_COLUMN: 'direct_type_id'}
            ),
            on='type_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']] if not mapping_frame.empty
            else pd.DataFrame(columns=['source_key', 'target_key']),
            left_on='type_key',
            right_on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['type_key', LOOKUP_ID_COLUMN]].rename(
                columns={'type_key': 'target_key', LOOKUP_ID_COLUMN: 'mapped_type_id'}
            ),
            on='target_key',
            how='left',
        )

        # A raw value that already matches a tblArrangementType label wins over whatever
        # the JSON maps it to, so a re-run leaves already-rewritten rows alone.
        resolved_frame['resolved_type_id'] = resolved_frame['mapped_type_id']
        resolved_frame.loc[
            resolved_frame['direct_type_id'].notna(),
            'resolved_type_id',
        ] = resolved_frame['direct_type_id']

        invalid_types = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_type_id'].isna(),
                'raw_type',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_type_id'].notna(),
            ['raw_type', 'resolved_type_id'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={'resolved_type_id': 'arrangement_type_id'}
        )
        resolution_frame['arrangement_type_id'] = (
            resolution_frame['arrangement_type_id'].astype(int)
        )

        return resolution_frame, invalid_types

    def bulk_update_arrangement_types(
        self,
        resolution_frame: pd.DataFrame,
        default_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Rewrite mapped values, then fill NULL/blank rows with default_label.

        Returns (rows_updated, rows_defaulted). Both statements run in one transaction.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection:
            return 0, 0

        if resolution_frame.empty and not default_label:
            return 0, 0

        cursor = db_helper.pyodbc_connection.cursor()
        rows_updated = 0
        rows_defaulted = 0

        try:
            if not resolution_frame.empty:
                # Shared sessions can process multiple customers; clear any prior temp
                # table safely.
                cursor.execute(
                    "IF OBJECT_ID('tempdb..#ArrangementTypeResolution') IS NOT NULL "
                    'DROP TABLE #ArrangementTypeResolution'
                )
                cursor.execute(
                    """
                    CREATE TABLE #ArrangementTypeResolution (
                        raw_type NVARCHAR(4000) NOT NULL,
                        arrangement_type_id INT NOT NULL
                    )
                    """
                )
                cursor.executemany(
                    'INSERT INTO #ArrangementTypeResolution '
                    '(raw_type, arrangement_type_id) VALUES (?, ?)',
                    list(
                        resolution_frame[['raw_type', 'arrangement_type_id']].itertuples(
                            index=False, name=None
                        )
                    ),
                )
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = t.{LOOKUP_LABEL_COLUMN}
                    FROM {SOURCE_TABLE} AS rc
                    INNER JOIN #ArrangementTypeResolution AS ar
                        ON CAST(rc.{SOURCE_COLUMN} AS NVARCHAR(4000)) = ar.raw_type
                    INNER JOIN {LOOKUP_TABLE} AS t
                        ON t.{LOOKUP_ID_COLUMN} = ar.arrangement_type_id
                    WHERE rc.{SOURCE_COLUMN} <> t.{LOOKUP_LABEL_COLUMN}
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated = int(row[0]) if row and row[0] is not None else 0

                cursor.execute('DROP TABLE #ArrangementTypeResolution')

            if default_label:
                # Blank is treated the same as NULL: the staging loads produce both.
                cursor.execute(
                    f"""
                    UPDATE {SOURCE_TABLE}
                    SET {SOURCE_COLUMN} = ?
                    WHERE {SOURCE_COLUMN} IS NULL
                       OR LTRIM(RTRIM({SOURCE_COLUMN})) = ''
                    """,
                    default_label,
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

    def get_invalid_arrangement_types_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblArrangementType match."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_types = self.read_source_arrangement_types()
        if source_types.empty:
            return []

        lookup_frame = self.read_lookup_frame()
        source_types['type_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_types['raw_type'])
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

        invalid = source_types[~source_types['type_key'].isin(lookup_keys)]
        return sorted(invalid['raw_type'].drop_duplicates().tolist())
