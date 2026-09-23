from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Staging column rewritten in place to the canonical tblClosureReason label, the same way
# RC_ACCOUNT_EXTRACT.MA_Status is rewritten to the tblAccountStatus label. Feeds the
# ClosureReason column in 01.tblaccount.sql.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_ACCOUNT_EXTRACT'
SOURCE_COLUMN = 'Reason_Closed'

# Named by the convention the other three lookups follow (tblAccountStatus/AccountStatus,
# tblArrangementType/ArrangementType, tblBankTransactionMethod/BankTransactionMethod).
# No migration query references this table by name, so if the real DT schema differs,
# these three constants are the only place to correct it.
LOOKUP_TABLE = 'tblClosureReason'
LOOKUP_ID_COLUMN = 'ClosureReasonID'
LOOKUP_LABEL_COLUMN = 'ClosureReason'


class ClosureReasonService:
    """Encapsulates Reason_Closed mapping, normalization, and validation logic.

    The defaulting rule is the inverse of the arrangement type service:
      - NULL or blank stays as-is, because "no closure reason" is meaningful
      - a value that maps (via JSON or a direct label match) becomes that label
      - a value that does not map is swept to the configured fallback label
    """

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_closure_reason_mapping_frame(
        self,
        reason_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in reason_mapping.items():
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

    def read_source_closure_reasons(self) -> pd.DataFrame:
        """Distinct non-null, non-blank Reason_Closed values.

        Blank is excluded along with NULL: neither is "a value", so neither is mapped
        or swept to the fallback.
        """
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=['raw_reason'])

        frame = db_helper.execute_query(
            f"""
            SELECT DISTINCT CAST({SOURCE_COLUMN} AS NVARCHAR(4000)) AS raw_reason
            FROM {SOURCE_TABLE}
            WHERE {SOURCE_COLUMN} IS NOT NULL
              AND LTRIM(RTRIM({SOURCE_COLUMN})) <> ''
            """
        )
        if frame.empty or 'raw_reason' not in frame.columns:
            return pd.DataFrame(columns=['raw_reason'])

        # dropna before astype(str), which would otherwise turn a NULL that slipped past
        # the IS NOT NULL predicate into the literal string 'None'.
        frame = frame.dropna(subset=['raw_reason'])
        frame['raw_reason'] = frame['raw_reason'].astype(str).str.strip()
        return frame[frame['raw_reason'] != ''].copy()

    def resolve_fallback_label(self, fallback_label: Optional[str]) -> Optional[str]:
        """Match the configured fallback against tblClosureReason, returning its exact label.

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
        lookup_frame['reason_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[LOOKUP_LABEL_COLUMN])
        )
        matches = lookup_frame.loc[lookup_frame['reason_key'] == wanted_key, LOOKUP_LABEL_COLUMN]
        if matches.empty:
            return None

        return str(matches.iloc[0])

    def build_closure_reason_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Returns (resolved values, values that will fall through to the fallback)."""
        empty_columns = ['raw_reason', 'closure_reason_id']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_reasons = self.read_source_closure_reasons()
        if source_reasons.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return (
                pd.DataFrame(columns=empty_columns),
                sorted(source_reasons['raw_reason'].drop_duplicates().tolist()),
            )

        source_reasons['normalized_reason'] = text_normalization.normalize_lookup_series(
            source_reasons['raw_reason']
        )
        source_reasons['reason_key'] = text_normalization.match_key_series(
            source_reasons['normalized_reason']
        )

        lookup_frame['normalized_lookup'] = text_normalization.normalize_lookup_series(
            lookup_frame[LOOKUP_LABEL_COLUMN]
        )
        lookup_frame['reason_key'] = text_normalization.match_key_series(
            lookup_frame['normalized_lookup']
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['reason_key'], keep='first')

        resolved_frame = source_reasons.merge(
            lookup_frame[['reason_key', LOOKUP_ID_COLUMN]].rename(
                columns={LOOKUP_ID_COLUMN: 'direct_reason_id'}
            ),
            on='reason_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']] if not mapping_frame.empty
            else pd.DataFrame(columns=['source_key', 'target_key']),
            left_on='reason_key',
            right_on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['reason_key', LOOKUP_ID_COLUMN]].rename(
                columns={'reason_key': 'target_key', LOOKUP_ID_COLUMN: 'mapped_reason_id'}
            ),
            on='target_key',
            how='left',
        )

        # A raw value that already matches a tblClosureReason label wins over whatever the
        # JSON maps it to, so a re-run leaves already-rewritten rows alone.
        resolved_frame['resolved_reason_id'] = resolved_frame['mapped_reason_id']
        resolved_frame.loc[
            resolved_frame['direct_reason_id'].notna(),
            'resolved_reason_id',
        ] = resolved_frame['direct_reason_id']

        unmapped_reasons = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_reason_id'].isna(),
                'raw_reason',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_reason_id'].notna(),
            ['raw_reason', 'resolved_reason_id'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={'resolved_reason_id': 'closure_reason_id'}
        )
        resolution_frame['closure_reason_id'] = (
            resolution_frame['closure_reason_id'].astype(int)
        )

        return resolution_frame, unmapped_reasons

    def bulk_update_closure_reasons(
        self,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Rewrite mapped values, then sweep remaining non-null values to fallback_label.

        NULL and blank are never touched. Returns (rows_updated, rows_defaulted); both
        statements run in one transaction.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection:
            return 0, 0

        if resolution_frame.empty and not fallback_label:
            return 0, 0

        cursor = db_helper.pyodbc_connection.cursor()
        rows_updated = 0
        rows_defaulted = 0

        try:
            if not resolution_frame.empty:
                # Shared sessions can process multiple customers; clear any prior temp
                # table safely.
                cursor.execute(
                    "IF OBJECT_ID('tempdb..#ClosureReasonResolution') IS NOT NULL "
                    'DROP TABLE #ClosureReasonResolution'
                )
                cursor.execute(
                    """
                    CREATE TABLE #ClosureReasonResolution (
                        raw_reason NVARCHAR(4000) NOT NULL,
                        closure_reason_id INT NOT NULL
                    )
                    """
                )
                cursor.executemany(
                    'INSERT INTO #ClosureReasonResolution '
                    '(raw_reason, closure_reason_id) VALUES (?, ?)',
                    list(
                        resolution_frame[['raw_reason', 'closure_reason_id']].itertuples(
                            index=False, name=None
                        )
                    ),
                )
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = t.{LOOKUP_LABEL_COLUMN}
                    FROM {SOURCE_TABLE} AS rc
                    INNER JOIN #ClosureReasonResolution AS cr
                        ON CAST(rc.{SOURCE_COLUMN} AS NVARCHAR(4000)) = cr.raw_reason
                    INNER JOIN {LOOKUP_TABLE} AS t
                        ON t.{LOOKUP_ID_COLUMN} = cr.closure_reason_id
                    WHERE rc.{SOURCE_COLUMN} <> t.{LOOKUP_LABEL_COLUMN}
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated = int(row[0]) if row and row[0] is not None else 0

                cursor.execute('DROP TABLE #ClosureReasonResolution')

            if fallback_label:
                # Anything still holding a real value that is not a tblClosureReason label
                # could not be mapped, so it becomes the catch-all. NULL and blank are
                # deliberately excluded: absence of a closure reason is not "other".
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

    def get_invalid_closure_reasons_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblClosureReason match.

        Expected to be empty whenever a fallback label is configured, since the sweep
        catches everything. Non-empty means the fallback is switched off.
        """
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_reasons = self.read_source_closure_reasons()
        if source_reasons.empty:
            return []

        lookup_frame = self.read_lookup_frame()
        source_reasons['reason_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_reasons['raw_reason'])
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

        invalid = source_reasons[~source_reasons['reason_key'].isin(lookup_keys)]
        return sorted(invalid['raw_reason'].drop_duplicates().tolist())
