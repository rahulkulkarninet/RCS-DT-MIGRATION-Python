from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

# Resolves the StateIDs that 44.tbladdress_Assign_StateID.sql leaves NULL.
#
# That file matches ADR.State = S.StateShort, i.e. the short code only, so free-text
# values such as 'New South Wales', 'N.S.W.' or 'VIC.' never resolve. This service maps
# those variants using variables/state_codes.json, rewrites tblAddress.State to the
# canonical StateShort and sets StateID in the same statement.
#
# Unlike the other transforms this runs AFTER the SQL batch rather than before it. The
# column it corrects is migrated data, not staging: tblAddress.State is populated
# mid-batch by files 37-43, from eleven different sources - segment 5 of the pipe
# delimited RC_DEBTOR / RC_RELATEDPARTY address strings, plus the discrete Pl_State,
# RepState, InsuredDriverState, TPD_State, TPO_State and IncidentState columns. By the
# time the batch finishes they have all collapsed into this one column, so a single pass
# here covers every source.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
TARGET_TABLE = 'tblAddress'
TARGET_COLUMN = 'State'
TARGET_ID_COLUMN = 'StateID'

LOOKUP_TABLE = 'tblState'
LOOKUP_ID_COLUMN = 'StateID'
LOOKUP_LABEL_COLUMN = 'StateShort'


class StateService:
    """Encapsulates state synonym mapping, normalization, and validation logic."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_state_mapping_frame(
        self,
        state_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        """Flatten {StateShort: [synonyms]} into one row per synonym.

        Keys beginning with '_' are treated as comments and ignored, matching the
        convention used in the other variables/*.json files.
        """
        rows: List[Dict[str, str]] = []
        seen_synonyms = set()
        duplicate_synonyms = 0

        for label, synonyms in state_mapping.items():
            if str(label).startswith('_') or not isinstance(synonyms, list):
                continue

            target_label = str(label).strip()
            normalized_target = text_normalization.normalize_lookup_key(target_label)

            # The canonical code is itself a valid source value. Its match key is what
            # punctuation variants collapse onto, so without this row 'N.S.W.' and 'VIC.'
            # would not resolve - and those are exactly the values file 44 cannot match.
            candidates = [target_label] + [s for s in synonyms if s is not None]

            for synonym in candidates:
                normalized_synonym = text_normalization.normalize_lookup_key(synonym)
                if not normalized_synonym:
                    continue

                synonym_key = text_normalization.match_key(normalized_synonym)
                if not synonym_key:
                    continue

                if synonym_key in seen_synonyms:
                    duplicate_synonyms += 1
                    continue

                seen_synonyms.add(synonym_key)
                rows.append(
                    {
                        'source_value': str(synonym).strip(),
                        'source_key': synonym_key,
                        'target_label': target_label,
                        'target_key': text_normalization.match_key(normalized_target),
                    }
                )

        return pd.DataFrame(rows), duplicate_synonyms

    def target_table_exists(self) -> bool:
        db_helper = self.db_helper
        if not db_helper:
            return False

        present = db_helper.execute_query(
            f"SELECT name FROM sys.tables WHERE name = '{TARGET_TABLE}'"
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

    def read_unresolved_address_states(self, load_id: Optional[int]) -> pd.DataFrame:
        """Distinct tblAddress.State values that file 44 could not resolve."""
        db_helper = self.db_helper
        if not db_helper or load_id is None or not self.target_table_exists():
            return pd.DataFrame(columns=['raw_state'])

        frame = db_helper.execute_query(
            f"""
            SELECT DISTINCT CAST(ADR.{TARGET_COLUMN} AS NVARCHAR(4000)) AS raw_state
            FROM {TARGET_TABLE} ADR WITH ( NOLOCK )
            WHERE ADR.LoadID = {int(load_id)}
              AND ADR.{TARGET_ID_COLUMN} IS NULL
              AND ADR.{TARGET_COLUMN} IS NOT NULL
            """
        )
        if frame.empty or 'raw_state' not in frame.columns:
            return pd.DataFrame(columns=['raw_state'])

        # dropna before astype(str), which would otherwise turn a NULL that slipped past
        # the IS NOT NULL predicate into the literal string 'None'.
        frame = frame.dropna(subset=['raw_state'])
        frame['raw_state'] = frame['raw_state'].astype(str).str.strip()
        return frame[frame['raw_state'] != ''].copy()

    def build_state_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
        load_id: Optional[int],
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Resolve each unresolved address state to a real StateID.

        Returns (resolution_frame, unresolved_labels). unresolved_labels lists JSON keys
        that are not present in tblState - a config/database mismatch, reported rather
        than silently dropped.
        """
        empty_columns = ['raw_state', 'state_id', 'target_label']

        source_states = self.read_unresolved_address_states(load_id)
        if source_states.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty or mapping_frame.empty:
            configured = [] if mapping_frame.empty else sorted(
                mapping_frame['target_label'].drop_duplicates().tolist()
            )
            return pd.DataFrame(columns=empty_columns), configured

        lookup_frame['state_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[LOOKUP_LABEL_COLUMN])
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['state_key'], keep='first')

        # Which configured StateShort codes are actually present in tblState.
        resolved_mapping = mapping_frame.merge(
            lookup_frame[['state_key', LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN]].rename(
                columns={'state_key': 'target_key'}
            ),
            on='target_key',
            how='left',
        )
        unresolved_labels = sorted(
            resolved_mapping.loc[resolved_mapping[LOOKUP_ID_COLUMN].isna(), 'target_label']
            .drop_duplicates()
            .tolist()
        )
        resolved_mapping = resolved_mapping.loc[resolved_mapping[LOOKUP_ID_COLUMN].notna()]

        source_states['state_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_states['raw_state'])
        )

        resolution_frame = source_states.merge(
            resolved_mapping[['source_key', LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN]],
            left_on='state_key',
            right_on='source_key',
            how='inner',
        )
        if resolution_frame.empty:
            return pd.DataFrame(columns=empty_columns), unresolved_labels

        resolution_frame = resolution_frame[
            ['raw_state', LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN]
        ].rename(
            columns={LOOKUP_ID_COLUMN: 'state_id', LOOKUP_LABEL_COLUMN: 'target_label'}
        )
        resolution_frame = resolution_frame.drop_duplicates(
            subset=['raw_state'], keep='first', ignore_index=True
        )
        resolution_frame['state_id'] = resolution_frame['state_id'].astype(int)

        return resolution_frame, unresolved_labels

    def bulk_update_address_states(
        self,
        resolution_frame: pd.DataFrame,
        load_id: Optional[int],
    ) -> int:
        """Rewrite State to the canonical StateShort and set StateID, in one statement.

        Scoped to this load and to rows file 44 left unresolved, so it can never disturb
        an address whose StateID is already correct.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection or load_id is None:
            return 0

        if resolution_frame.empty:
            return 0

        cursor = db_helper.pyodbc_connection.cursor()

        try:
            # Shared sessions can process multiple customers; clear any prior temp
            # table safely.
            cursor.execute(
                "IF OBJECT_ID('tempdb..#StateResolution') IS NOT NULL "
                'DROP TABLE #StateResolution'
            )
            cursor.execute(
                """
                CREATE TABLE #StateResolution (
                    raw_state NVARCHAR(4000) NOT NULL,
                    state_id INT NOT NULL
                )
                """
            )
            cursor.executemany(
                'INSERT INTO #StateResolution (raw_state, state_id) VALUES (?, ?)',
                list(
                    resolution_frame[['raw_state', 'state_id']].itertuples(
                        index=False, name=None
                    )
                ),
            )
            cursor.execute(
                f"""
                UPDATE ADR
                SET ADR.{TARGET_COLUMN} = t.{LOOKUP_LABEL_COLUMN},
                    ADR.{TARGET_ID_COLUMN} = t.{LOOKUP_ID_COLUMN}
                FROM {TARGET_TABLE} AS ADR WITH ( ROWLOCK )
                INNER JOIN #StateResolution AS sr
                    ON CAST(ADR.{TARGET_COLUMN} AS NVARCHAR(4000)) = sr.raw_state
                INNER JOIN {LOOKUP_TABLE} AS t
                    ON t.{LOOKUP_ID_COLUMN} = sr.state_id
                WHERE ADR.LoadID = {int(load_id)}
                  AND ADR.{TARGET_ID_COLUMN} IS NULL
                """
            )
            cursor.execute('SELECT @@ROWCOUNT')
            row = cursor.fetchone()
            rows_updated = int(row[0]) if row and row[0] is not None else 0

            cursor.execute('DROP TABLE #StateResolution')

            db_helper.pyodbc_connection.commit()
            return rows_updated

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    def get_invalid_states_from_db(self, load_id: Optional[int] = None) -> List[str]:
        """Post-update re-check: address states still unresolved for this load."""
        source_states = self.read_unresolved_address_states(load_id)
        if source_states.empty:
            return []

        return sorted(source_states['raw_state'].drop_duplicates().tolist())
