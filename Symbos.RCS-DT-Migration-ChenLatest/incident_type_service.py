from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import derived_mapping
import text_normalization

# Cause_Description keeps the text sent; the resolved tblIncidentType ID goes in the
# derived column Cause_Description_IncidentTypeID, which 45.tblaccountincident.sql reads.
# Replaces the keyword CASE that used to derive IncidentTypeID there:
#
#   WHEN Cause_Description LIKE '%THEFT%'  THEN 2   -- Theft
#   WHEN Cause_Description LIKE '%FIRE%'   THEN 3   -- Fire
#   WHEN Cause_Description LIKE '%WATER%'  THEN 4   -- Flood
#   WHEN Cause_Description LIKE '%DAMAGE%' THEN 8   -- Damage
#   ELSE 9                                          -- Property
#
# Unlike the other transforms the source is free text rather than a code, so the match is
# a keyword scan with precedence rather than an equality lookup. That scan happens here,
# in load order, and only its result - an ID - is written.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_ACCOUNT_EXTRACT'
SOURCE_COLUMN = 'Cause_Description'
TARGET_COLUMN = 'Cause_Description_IncidentTypeID'

LOOKUP_TABLE = 'tblIncidentType'
LOOKUP_ID_COLUMN = 'IncidentTypeID'
LOOKUP_LABEL_COLUMN = 'IncidentType'


class IncidentTypeService:
    """Encapsulates Cause_Description keyword classification, ID assignment, and validation."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def target_column_exists(self) -> bool:
        return derived_mapping.column_exists(self.db_helper, SOURCE_TABLE, TARGET_COLUMN)

    def load_incident_type_rules(
        self,
        rules: List[Any],
    ) -> Tuple[List[Dict[str, str]], int]:
        """Normalise the ordered rule list. Returns (rules, skipped_count).

        Order is significant and preserved: the first rule whose keyword appears in the
        description wins, exactly as the CASE WHEN chain behaved.
        """
        loaded: List[Dict[str, str]] = []
        skipped = 0

        for rule in rules:
            if not isinstance(rule, dict):
                skipped += 1
                continue

            keyword = rule.get('contains')
            label = rule.get('incident_type')
            if not keyword or not label:
                skipped += 1
                continue

            normalized_keyword = text_normalization.normalize_lookup_key(keyword)
            if not normalized_keyword:
                skipped += 1
                continue

            loaded.append(
                {
                    'keyword': str(keyword).strip(),
                    'normalized_keyword': normalized_keyword,
                    'target_label': str(label).strip(),
                }
            )

        return loaded, skipped

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

    def resolve_label(self, label: Optional[str]) -> Optional[str]:
        """Match a configured label against tblIncidentType, returning its exact label."""
        if not label or not str(label).strip():
            return None

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return None

        wanted_key = text_normalization.match_key(
            text_normalization.normalize_lookup_key(label)
        )
        lookup_frame['type_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[LOOKUP_LABEL_COLUMN])
        )
        matches = lookup_frame.loc[lookup_frame['type_key'] == wanted_key, LOOKUP_LABEL_COLUMN]
        if matches.empty:
            return None

        return str(matches.iloc[0])

    def label_id(self, label: Optional[str]) -> Optional[int]:
        """The IncidentTypeID of an exact tblIncidentType label, or None."""
        if not label:
            return None
        lookup_frame = self.read_lookup_frame()
        hits = lookup_frame.loc[lookup_frame[LOOKUP_LABEL_COLUMN] == str(label), LOOKUP_ID_COLUMN]
        return None if hits.empty else int(hits.iloc[0])

    def read_source_descriptions(self) -> pd.DataFrame:
        """Distinct cleaned non-blank Cause_Description values."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['raw_description'])

        frame = derived_mapping.read_distinct_values(
            db_helper, SOURCE_TABLE, SOURCE_COLUMN, 'raw_description'
        )
        if frame.empty:
            return pd.DataFrame(columns=['raw_description'])

        # dropna before astype(str), which would otherwise turn a NULL into 'None'.
        frame = frame.dropna(subset=['raw_description'])
        frame['raw_description'] = frame['raw_description'].astype(str)
        return frame[frame['raw_description'] != ''].copy()

    def classify_description(
        self,
        description: str,
        rules: List[Dict[str, str]],
    ) -> Optional[str]:
        """First matching rule wins. Returns the target label, or None for no match."""
        haystack = text_normalization.normalize_lookup_key(description)
        for rule in rules:
            if rule['normalized_keyword'] in haystack:
                return rule['target_label']
        return None

    def build_incident_type_resolution_frame(
        self,
        rules: List[Dict[str, str]],
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Resolve every distinct description to an IncidentTypeID.

        A description that already is a tblIncidentType label takes that ID first, as
        it did when 45 joined the text to the label; otherwise the first keyword rule
        that matches decides. Returns (resolution_frame[raw_description,
        incident_type_id], unresolved_labels), where unresolved_labels lists configured
        labels absent from tblIncidentType - a JSON/database mismatch, reported rather
        than silently dropped. Descriptions matching neither are left out and picked up
        by the default sweep in bulk_update_incident_types.
        """
        empty_columns = ['raw_description', 'incident_type_id']

        source_descriptions = self.read_source_descriptions()
        if source_descriptions.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        ids_by_key: Dict[str, int] = {}
        for row in lookup_frame.itertuples(index=False):
            key = text_normalization.match_key(
                text_normalization.normalize_lookup_key(getattr(row, LOOKUP_LABEL_COLUMN))
            )
            ids_by_key.setdefault(key, int(getattr(row, LOOKUP_ID_COLUMN)))

        unresolved_labels: List[str] = []
        label_cache: Dict[str, Optional[int]] = {}

        def lookup(label: str) -> Optional[int]:
            if label not in label_cache:
                ident = ids_by_key.get(
                    text_normalization.match_key(text_normalization.normalize_lookup_key(label))
                )
                if ident is None and label not in unresolved_labels:
                    unresolved_labels.append(label)
                label_cache[label] = ident
            return label_cache[label]

        rows: List[Dict[str, Any]] = []

        for description in source_descriptions['raw_description'].drop_duplicates():
            direct = ids_by_key.get(
                text_normalization.match_key(
                    text_normalization.normalize_lookup_key(description)
                )
            )
            if direct is not None:
                rows.append({'raw_description': description, 'incident_type_id': direct})
                continue

            matched_label = self.classify_description(description, rules)
            if not matched_label:
                continue

            ident = lookup(matched_label)
            if ident is not None:
                rows.append({'raw_description': description, 'incident_type_id': ident})

        if not rows:
            return pd.DataFrame(columns=empty_columns), sorted(set(unresolved_labels))

        frame = pd.DataFrame(rows).drop_duplicates(
            subset=['raw_description'], keep='first', ignore_index=True
        )
        return frame, sorted(set(unresolved_labels))

    def bulk_update_incident_types(
        self,
        resolution_frame: pd.DataFrame,
        default_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Fill Cause_Description_IncidentTypeID; Cause_Description is only read.

        Classified descriptions get their ID, then every row still without one gets
        the default label's ID. Returns (rows_mapped, rows_defaulted), in one
        transaction. The sweep covers NULL and blank as well as unmatched text,
        reproducing the old ELSE branch, which caught NULL because a NULL never
        satisfies a LIKE.
        """
        pairs = (
            []
            if resolution_frame.empty
            else resolution_frame[['raw_description', 'incident_type_id']].itertuples(
                index=False, name=None
            )
        )
        return derived_mapping.assign_ids(
            self.db_helper,
            SOURCE_TABLE,
            SOURCE_COLUMN,
            TARGET_COLUMN,
            pairs,
            default_id=self.label_id(default_label),
            default_scope=derived_mapping.DEFAULT_ALL,
        )

    def get_invalid_incident_types_from_db(self) -> List[str]:
        """Post-update re-check: non-blank Cause_Description values left without an ID.

        Empty whenever a default is configured, since the sweep catches every row.
        """
        return derived_mapping.read_unresolved_values(
            self.db_helper, SOURCE_TABLE, SOURCE_COLUMN, TARGET_COLUMN
        )
