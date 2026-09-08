from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Staging column rewritten in place to the canonical tblFrequency label, the same way
# RC_ARRANGEMENT.Arrangement_Type is rewritten to the tblArrangementType label. Replaces
# the hardcoded CASE WHEN AR.Frequency = 'W' THEN 2 ... ELSE 0 block that used to derive
# FrequencyID in "76.final loops and sps to run.sql", whose ELSE 0 wrote an FK value that
# does not exist in tblFrequency.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_ARRANGEMENT'
SOURCE_COLUMN = 'Frequency'

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

    def get_source_column_width(self) -> Optional[int]:
        """Declared character length of the staging column, or None if unknown.

        RC_ARRANGEMENT.Frequency ships as NVARCHAR(10) because it only ever held the
        1-2 character legacy codes. Canonical tblFrequency labels are longer than that
        ('Fortnightly' is 11 characters), so rewriting in place fails with a truncation
        error unless the column has been widened. -1 means NVARCHAR(MAX).
        """
        db_helper = self.db_helper
        if not db_helper:
            return None

        frame = db_helper.execute_query(
            f"""
            SELECT CHARACTER_MAXIMUM_LENGTH AS max_length
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{SOURCE_TABLE}'
              AND COLUMN_NAME = '{SOURCE_COLUMN}'
            """
        )
        if frame.empty or 'max_length' not in frame.columns:
            return None

        max_length = frame['max_length'].iloc[0]
        if pd.isna(max_length):
            return None

        return int(max_length)

    def check_source_column_fits(self, resolution_frame: pd.DataFrame) -> Optional[str]:
        """Return an actionable error when a canonical label will not fit, else None."""
        if resolution_frame.empty or 'target_label' not in resolution_frame.columns:
            return None

        column_width = self.get_source_column_width()
        # -1 is NVARCHAR(MAX); None means the column could not be inspected, in which
        # case let the UPDATE surface the real error rather than blocking on a guess.
        if column_width is None or column_width < 0:
            return None

        labels = resolution_frame['target_label'].astype(str)
        longest = labels.loc[labels.str.len().idxmax()]
        if len(longest) <= column_width:
            return None

        return (
            f'{SOURCE_TABLE}.{SOURCE_COLUMN} is NVARCHAR({column_width}) but the '
            f"canonical tblFrequency label '{longest}' is {len(longest)} characters, "
            'so rewriting it in place would be truncated. Widen the column first: '
            f'ALTER TABLE {SOURCE_TABLE} ALTER COLUMN {SOURCE_COLUMN} NVARCHAR(100) NOT NULL;'
        )

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

        frame = db_helper.execute_query(
            f"""
            SELECT DISTINCT CAST({SOURCE_COLUMN} AS NVARCHAR(4000)) AS raw_frequency
            FROM {SOURCE_TABLE}
            WHERE {SOURCE_COLUMN} IS NOT NULL
            """
        )
        if frame.empty or 'raw_frequency' not in frame.columns:
            return pd.DataFrame(columns=['raw_frequency'])

        # dropna before astype(str), which would otherwise turn a NULL that slipped past
        # the IS NOT NULL predicate into the literal string 'None'.
        frame = frame.dropna(subset=['raw_frequency'])
        frame['raw_frequency'] = frame['raw_frequency'].astype(str).str.strip()
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
        # JSON maps it to, so a re-run leaves already-rewritten rows alone.
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
        """Rewrite mapped values to their canonical tblFrequency label.

        Returns rows_updated. Unlike the arrangement type transform there is no default:
        RC_ARRANGEMENT.Frequency is NOT NULL, and inventing a frequency for an unknown
        code would fabricate a payment schedule. Unmapped values are left untouched and
        reported by the check step, landing as a NULL FrequencyID via the LEFT JOIN in
        "76.final loops and sps to run.sql" rather than the old bogus 0.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection:
            return 0

        if resolution_frame.empty:
            return 0

        width_error = self.check_source_column_fits(resolution_frame)
        if width_error:
            raise ValueError(width_error)

        cursor = db_helper.pyodbc_connection.cursor()

        try:
            # Shared sessions can process multiple customers; clear any prior temp
            # table safely.
            cursor.execute(
                "IF OBJECT_ID('tempdb..#FrequencyResolution') IS NOT NULL "
                'DROP TABLE #FrequencyResolution'
            )
            cursor.execute(
                """
                CREATE TABLE #FrequencyResolution (
                    raw_frequency NVARCHAR(4000) NOT NULL,
                    frequency_id INT NOT NULL
                )
                """
            )
            cursor.executemany(
                'INSERT INTO #FrequencyResolution '
                '(raw_frequency, frequency_id) VALUES (?, ?)',
                list(
                    resolution_frame[['raw_frequency', 'frequency_id']].itertuples(
                        index=False, name=None
                    )
                ),
            )
            cursor.execute(
                f"""
                UPDATE rc
                SET rc.{SOURCE_COLUMN} = t.{LOOKUP_LABEL_COLUMN}
                FROM {SOURCE_TABLE} AS rc
                INNER JOIN #FrequencyResolution AS fr
                    ON CAST(rc.{SOURCE_COLUMN} AS NVARCHAR(4000)) = fr.raw_frequency
                INNER JOIN {LOOKUP_TABLE} AS t
                    ON t.{LOOKUP_ID_COLUMN} = fr.frequency_id
                WHERE rc.{SOURCE_COLUMN} <> t.{LOOKUP_LABEL_COLUMN}
                """
            )
            cursor.execute('SELECT @@ROWCOUNT')
            row = cursor.fetchone()
            rows_updated = int(row[0]) if row and row[0] is not None else 0

            cursor.execute('DROP TABLE #FrequencyResolution')

            db_helper.pyodbc_connection.commit()
            return rows_updated

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    def get_invalid_frequencies_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblFrequency match."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_frequencies = self.read_source_frequencies()
        if source_frequencies.empty:
            return []

        lookup_frame = self.read_lookup_frame()
        source_frequencies['frequency_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_frequencies['raw_frequency'])
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

        invalid = source_frequencies[~source_frequencies['frequency_key'].isin(lookup_keys)]
        return sorted(invalid['raw_frequency'].drop_duplicates().tolist())
