from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Staging column rewritten in place to the canonical tblRelationship label, the same way
# RC_ARRANGEMENT.Arrangement_Type is rewritten to the tblArrangementType label. Replaces
# the hardcoded CASE WHEN RPA.Related_Party_Type_Code = 'GTR' THEN {{RelationshipID_Guarantor}}
# ... chain in 28.tblaccount_contact_related_parties.sql, where the relationship targets
# were tokenised but the legacy code list was not.
#
# Related_Party_Type_Code is read only by file 28, so rewriting it in place is safe.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_RELATEDPARTY'
SOURCE_COLUMN = 'Related_Party_Type_Code'

LOOKUP_TABLE = 'tblRelationship'
LOOKUP_ID_COLUMN = 'RelationshipID'
LOOKUP_LABEL_COLUMN = 'Relationship'


class RelatedPartyTypeService:
    """Encapsulates Related_Party_Type_Code mapping, normalization, and validation."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_related_party_type_mapping_frame(
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

    def get_source_column_width(self) -> Optional[int]:
        """Declared character length of the staging column, or None if unknown.

        Related_Party_Type_Code holds 3-character legacy codes, so it may well be
        narrower than the canonical tblRelationship labels it is rewritten to
        ('Additional Card Holder' is 22 characters). -1 means NVARCHAR(MAX).
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

    def check_source_column_fits(self, labels: List[str]) -> Optional[str]:
        """Return an actionable error when a canonical label will not fit, else None."""
        candidates = [str(label) for label in labels if label]
        if not candidates:
            return None

        column_width = self.get_source_column_width()
        # -1 is NVARCHAR(MAX); None means the column could not be inspected, in which
        # case let the UPDATE surface the real error rather than blocking on a guess.
        if column_width is None or column_width < 0:
            return None

        longest = max(candidates, key=len)
        if len(longest) <= column_width:
            return None

        return (
            f'{SOURCE_TABLE}.{SOURCE_COLUMN} is NVARCHAR({column_width}) but the '
            f"canonical tblRelationship label '{longest}' is {len(longest)} characters, "
            'so rewriting it in place would be truncated. Widen the column first: '
            f'ALTER TABLE {SOURCE_TABLE} ALTER COLUMN {SOURCE_COLUMN} NVARCHAR(100) NULL;'
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

    def read_source_related_party_types(self) -> pd.DataFrame:
        """Distinct non-null, non-blank Related_Party_Type_Code values."""
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

    def resolve_fallback_label(self, fallback_label: Optional[str]) -> Optional[str]:
        """Match the configured fallback against tblRelationship, returning its exact label.

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
        lookup_frame['type_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[LOOKUP_LABEL_COLUMN])
        )
        matches = lookup_frame.loc[lookup_frame['type_key'] == wanted_key, LOOKUP_LABEL_COLUMN]
        if matches.empty:
            return None

        return str(matches.iloc[0])

    def build_related_party_type_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        empty_columns = ['raw_type', 'relationship_id', 'target_label']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_types = self.read_source_related_party_types()
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
            lookup_frame[['type_key', LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN]].rename(
                columns={
                    LOOKUP_ID_COLUMN: 'direct_relationship_id',
                    LOOKUP_LABEL_COLUMN: 'direct_label',
                }
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
            lookup_frame[['type_key', LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN]].rename(
                columns={
                    'type_key': 'target_key',
                    LOOKUP_ID_COLUMN: 'mapped_relationship_id',
                    LOOKUP_LABEL_COLUMN: 'mapped_label',
                }
            ),
            on='target_key',
            how='left',
        )

        # A raw value that already matches a tblRelationship label wins over whatever the
        # JSON maps it to, so a re-run leaves already-rewritten rows alone.
        resolved_frame['resolved_relationship_id'] = resolved_frame['mapped_relationship_id']
        resolved_frame['resolved_label'] = resolved_frame['mapped_label']
        resolved_frame.loc[
            resolved_frame['direct_relationship_id'].notna(),
            'resolved_relationship_id',
        ] = resolved_frame['direct_relationship_id']
        resolved_frame.loc[
            resolved_frame['direct_relationship_id'].notna(),
            'resolved_label',
        ] = resolved_frame['direct_label']

        invalid_types = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_relationship_id'].isna(),
                'raw_type',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_relationship_id'].notna(),
            ['raw_type', 'resolved_relationship_id', 'resolved_label'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={
                'resolved_relationship_id': 'relationship_id',
                'resolved_label': 'target_label',
            }
        )
        resolution_frame['relationship_id'] = resolution_frame['relationship_id'].astype(int)

        return resolution_frame, invalid_types

    def bulk_update_related_party_types(
        self,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Rewrite mapped values, then sweep unmapped ones to fallback_label.

        Returns (rows_updated, rows_defaulted). Both statements run in one transaction.
        The fallback reproduces the ELSE {{RelationshipID_Other}} branch of the CASE this
        replaces; unlike that branch, the swept values are reported by the check step.
        NULL is left alone - file 28 inner-joins RC_RELATEDPARTY, and a related party with
        no type code at all is a data problem to surface, not to relabel.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection:
            return 0, 0

        if resolution_frame.empty and not fallback_label:
            return 0, 0

        labels = resolution_frame['target_label'].astype(str).tolist() \
            if not resolution_frame.empty else []
        if fallback_label:
            labels.append(str(fallback_label))
        width_error = self.check_source_column_fits(labels)
        if width_error:
            raise ValueError(width_error)

        cursor = db_helper.pyodbc_connection.cursor()
        rows_updated = 0
        rows_defaulted = 0

        try:
            if not resolution_frame.empty:
                # Shared sessions can process multiple customers; clear any prior temp
                # table safely.
                cursor.execute(
                    "IF OBJECT_ID('tempdb..#RelatedPartyTypeResolution') IS NOT NULL "
                    'DROP TABLE #RelatedPartyTypeResolution'
                )
                cursor.execute(
                    """
                    CREATE TABLE #RelatedPartyTypeResolution (
                        raw_type NVARCHAR(4000) NOT NULL,
                        relationship_id INT NOT NULL
                    )
                    """
                )
                cursor.executemany(
                    'INSERT INTO #RelatedPartyTypeResolution '
                    '(raw_type, relationship_id) VALUES (?, ?)',
                    list(
                        resolution_frame[['raw_type', 'relationship_id']].itertuples(
                            index=False, name=None
                        )
                    ),
                )
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = t.{LOOKUP_LABEL_COLUMN}
                    FROM {SOURCE_TABLE} AS rc
                    INNER JOIN #RelatedPartyTypeResolution AS rp
                        ON CAST(rc.{SOURCE_COLUMN} AS NVARCHAR(4000)) = rp.raw_type
                    INNER JOIN {LOOKUP_TABLE} AS t
                        ON t.{LOOKUP_ID_COLUMN} = rp.relationship_id
                    WHERE rc.{SOURCE_COLUMN} <> t.{LOOKUP_LABEL_COLUMN}
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated = int(row[0]) if row and row[0] is not None else 0

                cursor.execute('DROP TABLE #RelatedPartyTypeResolution')

            if fallback_label:
                # Anything left that is not already a tblRelationship label is unmapped;
                # sweep it to the fallback the way the old ELSE branch did.
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = ?
                    FROM {SOURCE_TABLE} AS rc
                    WHERE rc.{SOURCE_COLUMN} IS NOT NULL
                      AND LTRIM(RTRIM(rc.{SOURCE_COLUMN})) <> ''
                      AND NOT EXISTS (
                          SELECT 1 FROM {LOOKUP_TABLE} AS t
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

    def get_invalid_related_party_types_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblRelationship match."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_types = self.read_source_related_party_types()
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
