from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import derived_mapping
import text_normalization

# Frequency keeps the code sent; the resolved tblFrequency ID goes in the derived column
# Frequency_FrequencyID, read by "78.final loops and sps to run.sql". Replaces the
# hardcoded CASE WHEN AR.Frequency = 'W' THEN 2 ... ELSE 0 block that used to derive
# FrequencyID there, whose ELSE 0 wrote an FK value that does not exist in tblFrequency.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_ARRANGEMENT'
SOURCE_COLUMN = 'Frequency'
TARGET_COLUMN = 'Frequency_FrequencyID'

LOOKUP_TABLE = 'tblFrequency'
LOOKUP_ID_COLUMN = 'FrequencyID'
LOOKUP_LABEL_COLUMN = 'Frequency'


class FrequencyService:
    """Encapsulates Frequency mapping, normalization, and validation logic."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_frequency_mapping_frame(
        self,
        frequency_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in frequency_mapping.items():
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

    def target_column_exists(self) -> bool:
        return derived_mapping.column_exists(self.db_helper, SOURCE_TABLE, TARGET_COLUMN)

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

    def read_source_frequencies(self) -> pd.DataFrame:
        """Distinct non-null, non-blank Frequency values."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['raw_frequency'])

        frame = derived_mapping.read_distinct_values(
            db_helper, SOURCE_TABLE, SOURCE_COLUMN, 'raw_frequency'
        )
        if frame.empty:
            return pd.DataFrame(columns=['raw_frequency'])

        # dropna before astype(str), which would otherwise turn a NULL into 'None'.
        frame = frame.dropna(subset=['raw_frequency'])
        frame['raw_frequency'] = frame['raw_frequency'].astype(str)
        return frame[frame['raw_frequency'] != ''].copy()

    def build_frequency_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        empty_columns = ['raw_frequency', 'frequency_id', 'target_label']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_frequencies = self.read_source_frequencies()
        if source_frequencies.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return (
                pd.DataFrame(columns=empty_columns),
                sorted(source_frequencies['raw_frequency'].drop_duplicates().tolist()),
            )

        source_frequencies['normalized_frequency'] = (
            text_normalization.normalize_lookup_series(source_frequencies['raw_frequency'])
        )
        source_frequencies['frequency_key'] = text_normalization.match_key_series(
            source_frequencies['normalized_frequency']
        )

        lookup_frame['normalized_lookup'] = text_normalization.normalize_lookup_series(
            lookup_frame[LOOKUP_LABEL_COLUMN]
        )
        lookup_frame['frequency_key'] = text_normalization.match_key_series(
            lookup_frame['normalized_lookup']
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['frequency_key'], keep='first')

        resolved_frame = source_frequencies.merge(
            lookup_frame[['frequency_key', LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN]].rename(
                columns={
                    LOOKUP_ID_COLUMN: 'direct_frequency_id',
                    LOOKUP_LABEL_COLUMN: 'direct_label',
                }
            ),
            on='frequency_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']] if not mapping_frame.empty
            else pd.DataFrame(columns=['source_key', 'target_key']),
            left_on='frequency_key',
            right_on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['frequency_key', LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN]].rename(
                columns={
                    'frequency_key': 'target_key',
                    LOOKUP_ID_COLUMN: 'mapped_frequency_id',
                    LOOKUP_LABEL_COLUMN: 'mapped_label',
                }
            ),
            on='target_key',
            how='left',
        )

        # A raw value that already matches a tblFrequency label wins over whatever the
        # JSON maps it to.
        resolved_frame['resolved_frequency_id'] = resolved_frame['mapped_frequency_id']
        resolved_frame['resolved_label'] = resolved_frame['mapped_label']
        resolved_frame.loc[
            resolved_frame['direct_frequency_id'].notna(),
            'resolved_frequency_id',
        ] = resolved_frame['direct_frequency_id']
        resolved_frame.loc[
            resolved_frame['direct_frequency_id'].notna(),
            'resolved_label',
        ] = resolved_frame['direct_label']

        invalid_frequencies = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_frequency_id'].isna(),
                'raw_frequency',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_frequency_id'].notna(),
            ['raw_frequency', 'resolved_frequency_id', 'resolved_label'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={
                'resolved_frequency_id': 'frequency_id',
                'resolved_label': 'target_label',
            }
        )
        resolution_frame['frequency_id'] = resolution_frame['frequency_id'].astype(int)

        return resolution_frame, invalid_frequencies

    def bulk_update_frequencies(self, resolution_frame: pd.DataFrame) -> int:
        """Fill Frequency_FrequencyID; Frequency is only read. Returns rows mapped.

        Unlike the arrangement type transform there is no default: inventing a
        frequency for an unknown code would fabricate a payment schedule. Unmapped
        values get no ID, are reported by the check step, and land as a NULL
        FrequencyID in "78.final loops and sps to run.sql" rather than the old bogus 0.
        """
        if not self.source_table_exists():
            return 0
        pairs = (
            []
            if resolution_frame.empty
            else resolution_frame[['raw_frequency', 'frequency_id']].itertuples(
                index=False, name=None
            )
        )
        mapped, _ = derived_mapping.assign_ids(
            self.db_helper, SOURCE_TABLE, SOURCE_COLUMN, TARGET_COLUMN, pairs
        )
        return mapped

    def get_invalid_frequencies_from_db(self) -> List[str]:
        """Post-update re-check: non-blank Frequency values left without an ID."""
        if not self.source_table_exists():
            return []
        return derived_mapping.read_unresolved_values(
            self.db_helper, SOURCE_TABLE, SOURCE_COLUMN, TARGET_COLUMN
        )
