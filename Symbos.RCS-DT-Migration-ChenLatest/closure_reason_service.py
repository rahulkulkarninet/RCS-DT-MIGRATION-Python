from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import derived_mapping
import text_normalization

# Reason_Closed keeps the value sent; the resolved tblClosureReason ID goes in the
# derived column Reason_Closed_ClosureReasonID, which feeds the ClosureReason column in
# 01.tblaccount.sql.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_ACCOUNT_EXTRACT'
SOURCE_COLUMN = 'Reason_Closed'
TARGET_COLUMN = 'Reason_Closed_ClosureReasonID'

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
      - NULL or blank gets no ID, because "no closure reason" is meaningful
      - a value that maps (via JSON or a direct label match) gets that label's ID
      - a value that does not map gets the configured fallback label's ID
    """

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def target_column_exists(self) -> bool:
        return derived_mapping.column_exists(self.db_helper, SOURCE_TABLE, TARGET_COLUMN)

    def label_id(self, label: Optional[str]) -> Optional[int]:
        """The ClosureReasonID of an exact tblClosureReason label, or None."""
        if not label:
            return None
        lookup_frame = self.read_lookup_frame()
        hits = lookup_frame.loc[lookup_frame[LOOKUP_LABEL_COLUMN] == str(label), LOOKUP_ID_COLUMN]
        return None if hits.empty else int(hits.iloc[0])

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

        frame = derived_mapping.read_distinct_values(
            db_helper, SOURCE_TABLE, SOURCE_COLUMN, 'raw_reason'
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
        # JSON maps it to.
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
        """Fill Reason_Closed_ClosureReasonID; Reason_Closed is only read.

        Mapped values get their ID, then every remaining non-blank value gets the
        fallback label's ID. NULL and blank get none: absence of a closure reason is not
        "other". Returns (rows_mapped, rows_defaulted), in one transaction.
        """
        pairs = (
            []
            if resolution_frame.empty
            else resolution_frame[['raw_reason', 'closure_reason_id']].itertuples(
                index=False, name=None
            )
        )
        return derived_mapping.assign_ids(
            self.db_helper,
            SOURCE_TABLE,
            SOURCE_COLUMN,
            TARGET_COLUMN,
            pairs,
            default_id=self.label_id(fallback_label),
            default_scope=derived_mapping.DEFAULT_UNMAPPED,
        )

    def get_invalid_closure_reasons_from_db(self) -> List[str]:
        """Post-update re-check: non-blank Reason_Closed values left without an ID.

        Expected to be empty whenever a fallback label is configured, since the sweep
        catches everything. Non-empty means the fallback is switched off.
        """
        return derived_mapping.read_unresolved_values(
            self.db_helper, SOURCE_TABLE, SOURCE_COLUMN, TARGET_COLUMN
        )
