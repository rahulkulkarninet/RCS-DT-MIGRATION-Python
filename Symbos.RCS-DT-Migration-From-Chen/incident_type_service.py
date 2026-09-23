from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Staging column rewritten in place to the canonical tblIncidentType label, the same way
# RC_ACCOUNT_EXTRACT.MA_Status is rewritten to the tblAccountStatus label. Replaces the
# keyword CASE that used to derive IncidentTypeID in 45.tblaccountincident.sql:
#
#   WHEN Cause_Description LIKE '%THEFT%'  THEN 2   -- Theft
#   WHEN Cause_Description LIKE '%FIRE%'   THEN 3   -- Fire
#   WHEN Cause_Description LIKE '%WATER%'  THEN 4   -- Flood
#   WHEN Cause_Description LIKE '%DAMAGE%' THEN 8   -- Damage
#   ELSE 9                                          -- Property
#
# Unlike the other transforms the source is free text rather than a code, so the match is
# a keyword scan with precedence rather than an equality lookup. That scan happens here,
# in load order, and only its result is written back. Cause_Description has no other
# consumer in the migration and staging is truncated and reloaded every run, so
# overwriting it is safe.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_ACCOUNT_EXTRACT'
SOURCE_COLUMN = 'Cause_Description'

LOOKUP_TABLE = 'tblIncidentType'
LOOKUP_ID_COLUMN = 'IncidentTypeID'
LOOKUP_LABEL_COLUMN = 'IncidentType'


class IncidentTypeService:
    """Encapsulates Cause_Description keyword classification, rewrite, and validation."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

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

    def read_source_descriptions(self) -> pd.DataFrame:
        """Distinct non-null, non-blank Cause_Description values."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['raw_description'])

        frame = db_helper.execute_query(
            f"""
            SELECT DISTINCT CAST({SOURCE_COLUMN} AS NVARCHAR(4000)) AS raw_description
            FROM {SOURCE_TABLE}
            WHERE {SOURCE_COLUMN} IS NOT NULL
            """
        )
        if frame.empty or 'raw_description' not in frame.columns:
            return pd.DataFrame(columns=['raw_description'])

        # dropna before astype(str), which would otherwise turn a NULL that slipped past
        # the IS NOT NULL predicate into the literal string 'None'.
        frame = frame.dropna(subset=['raw_description'])
        frame['raw_description'] = frame['raw_description'].astype(str).str.strip()
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
        """Classify every distinct description and resolve it to a tblIncidentType label.

        Returns (resolution_frame, unresolved_labels). unresolved_labels lists configured
        labels absent from tblIncidentType - a JSON/database mismatch, reported rather
        than silently dropped. Descriptions matching no rule are left out entirely and
        picked up by the default sweep in bulk_update_incident_types.
        """
        empty_columns = ['raw_description', 'target_label']

        source_descriptions = self.read_source_descriptions()
        if source_descriptions.empty:
            return pd.DataFrame(columns=empty_columns), []

        unresolved_labels: List[str] = []
        label_cache: Dict[str, Optional[str]] = {}

        def lookup(label: str) -> Optional[str]:
            if label not in label_cache:
                resolved = self.resolve_label(label)
                if not resolved and label not in unresolved_labels:
                    unresolved_labels.append(label)
                label_cache[label] = resolved
            return label_cache[label]

        rows: List[Dict[str, str]] = []

        for description in source_descriptions['raw_description'].drop_duplicates():
            matched_label = self.classify_description(description, rules)
            if not matched_label:
                continue

            resolved = lookup(matched_label)
            if not resolved:
                continue

            # A description that is already the canonical label needs no rewrite, and
            # skipping it keeps a re-run idempotent.
            if description == resolved:
                continue

            rows.append({'raw_description': description, 'target_label': resolved})

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
        """Rewrite classified descriptions, then sweep everything else to default_label.

        Returns (rows_updated, rows_defaulted). Both statements run in one transaction.
        The sweep covers NULL and blank as well as unmatched text, reproducing the old
        ELSE branch, which caught NULL because a NULL never satisfies a LIKE.
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
                    "IF OBJECT_ID('tempdb..#IncidentTypeResolution') IS NOT NULL "
                    'DROP TABLE #IncidentTypeResolution'
                )
                cursor.execute(
                    """
                    CREATE TABLE #IncidentTypeResolution (
                        raw_description NVARCHAR(4000) NOT NULL,
                        target_label NVARCHAR(200) NOT NULL
                    )
                    """
                )
                cursor.executemany(
                    'INSERT INTO #IncidentTypeResolution '
                    '(raw_description, target_label) VALUES (?, ?)',
                    list(
                        resolution_frame[['raw_description', 'target_label']].itertuples(
                            index=False, name=None
                        )
                    ),
                )
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = it.target_label
                    FROM {SOURCE_TABLE} AS rc
                    INNER JOIN #IncidentTypeResolution AS it
                        ON CAST(rc.{SOURCE_COLUMN} AS NVARCHAR(4000)) = it.raw_description
                    WHERE rc.{SOURCE_COLUMN} <> it.target_label
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated = int(row[0]) if row and row[0] is not None else 0

                cursor.execute('DROP TABLE #IncidentTypeResolution')

            if default_label:
                # Anything not already a tblIncidentType label matched no keyword rule;
                # sweep it to the default the way the old ELSE branch did. NULL and blank
                # are included: the CASE gave those IncidentTypeID 9 too.
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{SOURCE_COLUMN} = ?
                    FROM {SOURCE_TABLE} AS rc
                    WHERE NOT EXISTS (
                        SELECT 1 FROM {LOOKUP_TABLE} AS t
                        WHERE t.{LOOKUP_LABEL_COLUMN} = rc.{SOURCE_COLUMN}
                    )
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

    def get_invalid_incident_types_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblIncidentType match."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_descriptions = self.read_source_descriptions()
        if source_descriptions.empty:
            return []

        lookup_frame = self.read_lookup_frame()
        source_descriptions['type_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(
                source_descriptions['raw_description']
            )
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

        invalid = source_descriptions[~source_descriptions['type_key'].isin(lookup_keys)]
        return sorted(invalid['raw_description'].drop_duplicates().tolist())
