from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Staging column rewritten in place to the canonical tblHardshipCause label, the same way
# RC_ACCOUNT_EXTRACT.MA_Status is rewritten to the tblAccountStatus label. Feeds the
# HardshipCauseID lookup in 78.tblHardship.sql.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_HARDSHIP_EXTRACT'
SOURCE_COLUMN = 'Hardship_Cause'

LOOKUP_TABLE = 'tblHardshipCause'
LOOKUP_ID_COLUMN = 'HardshipCauseID'
LOOKUP_LABEL_COLUMN = 'HardshipCause'


class HardshipCauseService:
    """Encapsulates Hardship_Cause mapping, normalization, and validation logic.

    Unlike every other lookup in this framework, this customer's extract carries
    Hardship_Cause as a raw tblHardshipCause.HardshipCauseID integer (e.g. '23' for
    'Illness'), not a text label - so a value that parses as an integer and matches an
    existing HardshipCauseID is resolved directly by ID, ahead of the usual JSON/label
    matching, which still applies for any future source that supplies text instead.

    NULL or blank stays as-is - a source row with no cause value is left untouched
    rather than swept to a default.
    """

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_hardship_cause_mapping_frame(
        self,
        cause_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in cause_mapping.items():
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
        """Not every customer has hardship applications, unlike RC_ACCOUNT_EXTRACT."""
        db_helper = self.db_helper
        if not db_helper:
            return False

        present = db_helper.execute_query(
            f"SELECT 1 AS found WHERE OBJECT_ID('{SOURCE_TABLE}') IS NOT NULL"
        )
        return not present.empty

    def read_source_causes(self) -> pd.DataFrame:
        """Distinct non-null, non-blank Hardship_Cause values."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['raw_cause'])

        frame = db_helper.execute_query(
            f"""
            SELECT DISTINCT CAST({SOURCE_COLUMN} AS NVARCHAR(4000)) AS raw_cause
            FROM {SOURCE_TABLE}
            WHERE {SOURCE_COLUMN} IS NOT NULL
              AND LTRIM(RTRIM({SOURCE_COLUMN})) <> ''
            """
        )
        if frame.empty or 'raw_cause' not in frame.columns:
            return pd.DataFrame(columns=['raw_cause'])

        frame = frame.dropna(subset=['raw_cause'])
        frame['raw_cause'] = frame['raw_cause'].astype(str).str.strip()
        return frame[frame['raw_cause'] != ''].copy()

    def resolve_fallback_label(self, fallback_label: Optional[str]) -> Optional[str]:
        """Match the configured fallback against tblHardshipCause, returning its exact label.

        Returns None when the fallback is switched off (blank in the JSON) or when the
        configured label is not present in the lookup table.
        """
        if not fallback_label or not str(fallback_label).strip():
            return None

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return None

        wanted_key = text_normalization.match_key(
            text_normalization.normalize_lookup_key(fallback_label)
        )
        lookup_frame['cause_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[LOOKUP_LABEL_COLUMN])
        )
        matches = lookup_frame.loc[lookup_frame['cause_key'] == wanted_key, LOOKUP_LABEL_COLUMN]
        if matches.empty:
            return None

        return str(matches.iloc[0])

    def build_hardship_cause_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Returns (resolved values, values that will fall through to the fallback).

        Resolution order per raw value: (1) numeric ID that exists in tblHardshipCause,
        (2) direct label match, (3) JSON mapping match.
        """
        empty_columns = ['raw_cause', 'hardship_cause_id']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_causes = self.read_source_causes()
        if source_causes.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return (
                pd.DataFrame(columns=empty_columns),
                sorted(source_causes['raw_cause'].drop_duplicates().tolist()),
            )

        lookup_ids = set(lookup_frame[LOOKUP_ID_COLUMN].astype(int).tolist())

        def numeric_id_match(raw_value: str) -> Optional[int]:
            try:
                candidate = int(str(raw_value).strip())
            except (TypeError, ValueError):
                return None
            return candidate if candidate in lookup_ids else None

        source_causes['numeric_id_match'] = source_causes['raw_cause'].apply(numeric_id_match)

        source_causes['normalized_cause'] = text_normalization.normalize_lookup_series(
            source_causes['raw_cause']
        )
        source_causes['cause_key'] = text_normalization.match_key_series(
            source_causes['normalized_cause']
        )

        lookup_frame['normalized_lookup'] = text_normalization.normalize_lookup_series(
            lookup_frame[LOOKUP_LABEL_COLUMN]
        )
        lookup_frame['cause_key'] = text_normalization.match_key_series(
            lookup_frame['normalized_lookup']
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['cause_key'], keep='first')

        resolved_frame = source_causes.merge(
            lookup_frame[['cause_key', LOOKUP_ID_COLUMN]].rename(
                columns={LOOKUP_ID_COLUMN: 'direct_cause_id'}
            ),
            on='cause_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']] if not mapping_frame.empty
            else pd.DataFrame(columns=['source_key', 'target_key']),
            left_on='cause_key',
            right_on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['cause_key', LOOKUP_ID_COLUMN]].rename(
                columns={'cause_key': 'target_key', LOOKUP_ID_COLUMN: 'mapped_cause_id'}
            ),
            on='target_key',
            how='left',
        )

        # Precedence: JSON-mapped label, then a direct label match, then (highest priority,
        # since it's an unambiguous exact FK reference) a numeric HardshipCauseID.
        resolved_frame['resolved_cause_id'] = resolved_frame['mapped_cause_id']
        resolved_frame.loc[
            resolved_frame['direct_cause_id'].notna(),
            'resolved_cause_id',
        ] = resolved_frame['direct_cause_id']
        resolved_frame.loc[
            resolved_frame['numeric_id_match'].notna(),
            'resolved_cause_id',
        ] = resolved_frame['numeric_id_match']

        unmapped_causes = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_cause_id'].isna(),
                'raw_cause',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_cause_id'].notna(),
            ['raw_cause', 'resolved_cause_id'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={'resolved_cause_id': 'hardship_cause_id'}
        )
        resolution_frame['hardship_cause_id'] = (
            resolution_frame['hardship_cause_id'].astype(int)
        )

        return resolution_frame, unmapped_causes

    def bulk_update_hardship_causes(
        self,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Rewrite mapped/ID-resolved values to the canonical label, then sweep remaining
        non-null values to fallback_label.

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
                    "IF OBJECT_ID('tempdb..#HardshipCauseResolution') IS NOT NULL "
                    'DROP TABLE #HardshipCauseResolution'
                )
                cursor.execute(
                    """
                    CREATE TABLE #HardshipCauseResolution (
                        raw_cause NVARCHAR(4000) NOT NULL,
                        hardship_cause_id INT NOT NULL
                    )
                    """
                )
                cursor.executemany(
                    'INSERT INTO #HardshipCauseResolution '
                    '(raw_cause, hardship_cause_id) VALUES (?, ?)',
                    list(
                        resolution_frame[['raw_cause', 'hardship_cause_id']].itertuples(
                            index=False, name=None
                        )
                    ),
                )
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = t.{LOOKUP_LABEL_COLUMN}
                    FROM {SOURCE_TABLE} AS rc
                    INNER JOIN #HardshipCauseResolution AS hc
                        ON CAST(rc.{SOURCE_COLUMN} AS NVARCHAR(4000)) = hc.raw_cause
                    INNER JOIN {LOOKUP_TABLE} AS t
                        ON t.{LOOKUP_ID_COLUMN} = hc.hardship_cause_id
                    WHERE rc.{SOURCE_COLUMN} <> t.{LOOKUP_LABEL_COLUMN}
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated = int(row[0]) if row and row[0] is not None else 0

                cursor.execute('DROP TABLE #HardshipCauseResolution')

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

    def get_invalid_hardship_causes_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblHardshipCause match."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_causes = self.read_source_causes()
        if source_causes.empty:
            return []

        lookup_frame = self.read_lookup_frame()
        source_causes['cause_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_causes['raw_cause'])
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

        invalid = source_causes[~source_causes['cause_key'].isin(lookup_keys)]
        return sorted(invalid['raw_cause'].drop_duplicates().tolist())
