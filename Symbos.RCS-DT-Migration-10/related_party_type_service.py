from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import derived_mapping
import text_normalization

# Related_Party_Type_Code keeps the code sent; the resolved tblRelationship ID goes in the
# derived column Related_Party_Type_Code_RelationshipID, read by
# 28.tblaccount_contact_related_parties.sql. Replaces the hardcoded
# CASE WHEN RPA.Related_Party_Type_Code = 'GTR' THEN {{RelationshipID_Guarantor}} ... chain
# that used to be there, where the relationship targets were tokenised but the legacy
# code list was not.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_RELATEDPARTY'
SOURCE_COLUMN = 'Related_Party_Type_Code'
TARGET_COLUMN = 'Related_Party_Type_Code_RelationshipID'

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

    def read_source_related_party_types(self) -> pd.DataFrame:
        """Distinct non-null, non-blank Related_Party_Type_Code values."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['raw_type'])

        frame = derived_mapping.read_distinct_values(
            db_helper, SOURCE_TABLE, SOURCE_COLUMN, 'raw_type'
        )
        if frame.empty:
            return pd.DataFrame(columns=['raw_type'])

        # dropna before astype(str), which would otherwise turn a NULL into 'None'.
        frame = frame.dropna(subset=['raw_type'])
        frame['raw_type'] = frame['raw_type'].astype(str)
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

    def label_id(self, label: Optional[str]) -> Optional[int]:
        """The RelationshipID of an exact tblRelationship label, or None."""
        if not label:
            return None
        lookup_frame = self.read_lookup_frame()
        hits = lookup_frame.loc[lookup_frame[LOOKUP_LABEL_COLUMN] == str(label), LOOKUP_ID_COLUMN]
        return None if hits.empty else int(hits.iloc[0])

    def bulk_update_related_party_types(
        self,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Fill Related_Party_Type_Code_RelationshipID; the code is only read.

        Mapped values get their ID, then every remaining non-blank value gets the
        fallback label's ID. NULL and blank get none. Returns (rows_mapped,
        rows_defaulted), in one transaction.
        """
        if not self.source_table_exists():
            return 0, 0
        pairs = (
            []
            if resolution_frame.empty
            else resolution_frame[['raw_type', 'relationship_id']].itertuples(
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

    def get_invalid_related_party_types_from_db(self) -> List[str]:
        """Post-update re-check: non-blank codes left without a RelationshipID."""
        if not self.source_table_exists():
            return []
        return derived_mapping.read_unresolved_values(
            self.db_helper, SOURCE_TABLE, SOURCE_COLUMN, TARGET_COLUMN
        )
