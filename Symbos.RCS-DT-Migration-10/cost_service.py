"""Cost code mapping: RC_COSTS_EXTRACT's wide [Chg_<code>] columns -> RC_STAGING_COSTS.

The odd one out among the code-mapping domains. Status, payment method, arrangement
type, frequency, related party type, incident type and closure reason all rewrite a
staging *value* in place so the migration SQL can join on a label. A cost code is not a
value - it is part of the column name, one `Chg_<code>` per cost type on a single wide
row per debtor - so there is nothing to rewrite. Instead this unpivots those columns
into RC_STAGING_COSTS with CostTypeID and MasterCostID already resolved, and
51.tblcosts.sql reads that table.

What used to be hardcoded in 51.tblcosts.sql and is now config:
  - the 59 ('ADM', ISNULL([Chg_ADM], 0)) code/column pairs in its CROSS APPLY
  - CASE WHEN CostField = 'COL' THEN 12 ELSE 2 END -> MasterCostID
  - the code -> CostTypeID lookup, which was an INNER JOIN to CSRC_CostTypeMapping

That INNER JOIN is why this exists. CSRC_CostTypeMapping is reference data seeded
per environment, it had no row for COL, and an INNER JOIN drops what it cannot match:
on dev load 238 every one of the 11,038 COL charges - $403,234.13, of which
$358,488.29 was still outstanding - vanished with no error, tblCost was left completely
empty, and accounts whose COL charge had been paid ended up with a negative balance
because 49.tblpayment.sql still copied the payment's AllocatedCost across. So a charged
code with no mapping is fatal here, not a warning: better a stopped customer than
silently unmigrated money.

Table and column names are hardcoded identifiers, never user input, so interpolating
them into SQL is safe and matches the rest of the repo. Cost codes come from an
edited-by-hand JSON, so they are validated against CODE_PATTERN before reaching a
statement.
"""

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization

SOURCE_TABLE = 'RC_COSTS_EXTRACT'
SOURCE_KEY_COLUMN = 'Debtor_Code'
CHARGE_COLUMN_PREFIX = 'Chg_'

STAGING_TABLE = 'RC_STAGING_COSTS'
STAGING_SCHEMA_FILE = 'SQL/Schemas/RC_STAGING_COSTS Schema.sql'

COST_TYPE_LOOKUP_TABLE = 'tblCostType'
COST_TYPE_ID_COLUMN = 'CostTypeID'
COST_TYPE_LABEL_COLUMN = 'CostType'

MASTER_COST_LOOKUP_TABLE = 'tblMasterCost'
MASTER_COST_ID_COLUMN = 'MasterCostID'
MASTER_COST_LABEL_COLUMN = 'MasterCost'

# A cost code becomes part of a column name and of a SQL string literal. Anything
# outside this cannot be either, so it is rejected rather than escaped.
CODE_PATTERN = re.compile(r'^[A-Za-z0-9_]{1,20}$')


class CostService:
    """Encapsulates cost code mapping, resolution, and RC_STAGING_COSTS rebuilds."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def load_cost_mapping_frame(
        self,
        cost_type_mapping: Dict[str, Any],
        master_cost_mapping: Optional[Dict[str, Any]] = None,
        default_master_cost: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, int, List[str]]:
        """One row per configured cost code.

        Returns (frame, duplicate_codes, rejected_codes). A code appearing under two
        cost types is counted as a duplicate and the first wins, matching the way the
        other domains treat a code listed twice.
        """
        master_cost_mapping = master_cost_mapping or {}
        default_master_cost = (default_master_cost or '').strip()

        # code -> master cost label, inverted from the {label: [codes]} shape the
        # other domain files use so the per-code override is a dict lookup below.
        master_cost_by_code: Dict[str, str] = {}
        for label, codes in master_cost_mapping.items():
            if not isinstance(codes, list):
                continue
            for code in codes:
                if code is None:
                    continue
                key = text_normalization.match_key(code)
                if key and key not in master_cost_by_code:
                    master_cost_by_code[key] = str(label).strip()

        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0
        rejected_codes: List[str] = []

        for label, codes in cost_type_mapping.items():
            if not isinstance(codes, list):
                continue

            cost_type_label = str(label).strip()

            for code in codes:
                if code is None:
                    continue

                source_code = str(code).strip()
                if not source_code:
                    continue

                if not CODE_PATTERN.match(source_code):
                    rejected_codes.append(source_code)
                    continue

                code_key = text_normalization.match_key(source_code)
                if code_key in seen_codes:
                    duplicate_codes += 1
                    continue

                seen_codes.add(code_key)
                master_cost_label = master_cost_by_code.get(
                    code_key, default_master_cost
                )
                rows.append(
                    {
                        'source_code': source_code,
                        'code_key': code_key,
                        'source_column': f'{CHARGE_COLUMN_PREFIX}{source_code}',
                        'cost_type_label': cost_type_label,
                        'cost_type_key': text_normalization.match_key(
                            text_normalization.normalize_lookup_key(cost_type_label)
                        ),
                        'master_cost_label': master_cost_label,
                        'master_cost_key': text_normalization.match_key(
                            text_normalization.normalize_lookup_key(master_cost_label)
                        ),
                    }
                )

        columns = [
            'source_code', 'code_key', 'source_column', 'cost_type_label',
            'cost_type_key', 'master_cost_label', 'master_cost_key',
        ]
        frame = pd.DataFrame(rows, columns=columns)
        return frame, duplicate_codes, sorted(set(rejected_codes))

    # ------------------------------------------------------------------
    # Database reads
    # ------------------------------------------------------------------

    def source_table_exists(self) -> bool:
        return self._table_exists(SOURCE_TABLE)

    def staging_table_exists(self) -> bool:
        return self._table_exists(STAGING_TABLE)

    def _table_exists(self, table_name: str) -> bool:
        db_helper = self.db_helper
        if not db_helper:
            return False

        present = db_helper.execute_query(
            f"SELECT name FROM sys.tables WHERE name = '{table_name}'"
        )
        return not present.empty

    def _read_lookup_frame(
        self,
        table: str,
        id_column: str,
        label_column: str,
    ) -> pd.DataFrame:
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=[id_column, label_column])

        lookup_frame = db_helper.execute_query(
            f"""
            SELECT {id_column},
                   CAST({label_column} AS NVARCHAR(4000)) AS {label_column}
            FROM {table}
            WHERE {label_column} IS NOT NULL
            """
        )
        if lookup_frame.empty or label_column not in lookup_frame.columns:
            return pd.DataFrame(columns=[id_column, label_column])

        lookup_frame[label_column] = (
            lookup_frame[label_column].astype(str).str.strip()
        )
        lookup_frame = lookup_frame[lookup_frame[label_column] != ''].copy()
        lookup_frame['lookup_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(lookup_frame[label_column])
        )
        return lookup_frame.drop_duplicates(subset=['lookup_key'], keep='first')

    def read_cost_type_lookup_frame(self) -> pd.DataFrame:
        return self._read_lookup_frame(
            COST_TYPE_LOOKUP_TABLE, COST_TYPE_ID_COLUMN, COST_TYPE_LABEL_COLUMN
        )

    def read_master_cost_lookup_frame(self) -> pd.DataFrame:
        return self._read_lookup_frame(
            MASTER_COST_LOOKUP_TABLE, MASTER_COST_ID_COLUMN, MASTER_COST_LABEL_COLUMN
        )

    def read_source_charge_columns(self) -> List[str]:
        """The [Chg_<code>] columns RC_COSTS_EXTRACT actually has.

        Read rather than assumed so a JSON code whose column does not exist is named
        by the check step instead of failing the unpivot with an invalid column name,
        and so a code added to the extract but not to the JSON can be spotted.
        """
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return []

        frame = db_helper.execute_query(
            f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{SOURCE_TABLE}'
              AND COLUMN_NAME LIKE '{CHARGE_COLUMN_PREFIX}%'
            """
        )
        if frame.empty or 'COLUMN_NAME' not in frame.columns:
            return []

        return sorted(
            name for name in frame['COLUMN_NAME'].astype(str).tolist()
            if CODE_PATTERN.match(name[len(CHARGE_COLUMN_PREFIX):])
        )

    def read_charged_codes(self) -> Dict[str, Tuple[int, Decimal]]:
        """code -> (rows carrying a non-zero charge, total charged).

        One aggregate over the wide table rather than a query per column: there are 71
        of them and staging holds a single customer at a time.
        """
        db_helper = self.db_helper
        charge_columns = self.read_source_charge_columns()
        if not db_helper or not charge_columns:
            return {}

        selects = []
        for column in charge_columns:
            code = column[len(CHARGE_COLUMN_PREFIX):]
            selects.append(
                f'SUM(CASE WHEN ISNULL([{column}], 0) <> 0 THEN 1 ELSE 0 END) '
                f'AS rows_{code}'
            )
            selects.append(f'SUM(ISNULL([{column}], 0)) AS total_{code}')

        frame = db_helper.execute_query(
            f"SELECT {', '.join(selects)} FROM {SOURCE_TABLE} WITH (NOLOCK)"
        )
        if frame.empty:
            return {}

        row = frame.iloc[0]
        charged: Dict[str, Tuple[int, Decimal]] = {}
        for column in charge_columns:
            code = column[len(CHARGE_COLUMN_PREFIX):]
            count = row.get(f'rows_{code}')
            total = row.get(f'total_{code}')
            count = int(count) if pd.notna(count) else 0
            if count > 0:
                charged[code] = (
                    count,
                    Decimal(str(total)) if pd.notna(total) else Decimal(0),
                )
        return charged

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def build_cost_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
        excluded_codes: Optional[Dict[str, Any]] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
        """Resolve every configured code to a CostTypeID and MasterCostID.

        Returns (resolution_frame, problems) where problems collects, by kind, what
        cannot be migrated as configured:
          unresolved_cost_types   JSON label absent from tblCostType
          unresolved_master_costs JSON label absent from tblMasterCost
          missing_columns         configured code with no Chg_ column on the extract
          unmapped_charged_codes  extract column carrying money that nothing maps
        Only the last is about the data; the first three are about the config.
        """
        empty_columns = [
            'source_code', 'source_column', 'cost_type_id', 'master_cost_id',
        ]
        problems: Dict[str, List[str]] = {
            'unresolved_cost_types': [],
            'unresolved_master_costs': [],
            'missing_columns': [],
            'unmapped_charged_codes': [],
        }

        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), problems

        excluded_keys = {
            text_normalization.match_key(code)
            for code in (excluded_codes or {})
        }

        charge_columns = set(self.read_source_charge_columns())
        charged_codes = self.read_charged_codes()

        resolution_frame = pd.DataFrame(columns=empty_columns)

        if not mapping_frame.empty:
            cost_types = self.read_cost_type_lookup_frame()
            master_costs = self.read_master_cost_lookup_frame()

            resolved = mapping_frame.merge(
                cost_types[['lookup_key', COST_TYPE_ID_COLUMN]].rename(
                    columns={
                        'lookup_key': 'cost_type_key',
                        COST_TYPE_ID_COLUMN: 'cost_type_id',
                    }
                ) if not cost_types.empty
                else pd.DataFrame(columns=['cost_type_key', 'cost_type_id']),
                on='cost_type_key',
                how='left',
            )
            resolved = resolved.merge(
                master_costs[['lookup_key', MASTER_COST_ID_COLUMN]].rename(
                    columns={
                        'lookup_key': 'master_cost_key',
                        MASTER_COST_ID_COLUMN: 'master_cost_id',
                    }
                ) if not master_costs.empty
                else pd.DataFrame(columns=['master_cost_key', 'master_cost_id']),
                on='master_cost_key',
                how='left',
            )

            problems['unresolved_cost_types'] = sorted(
                resolved.loc[resolved['cost_type_id'].isna(), 'cost_type_label']
                .drop_duplicates()
                .tolist()
            )
            problems['unresolved_master_costs'] = sorted(
                resolved.loc[resolved['master_cost_id'].isna(), 'master_cost_label']
                .drop_duplicates()
                .tolist()
            )
            problems['missing_columns'] = sorted(
                resolved.loc[
                    ~resolved['source_column'].isin(charge_columns),
                    'source_code',
                ]
                .drop_duplicates()
                .tolist()
            )

            usable = resolved[
                resolved['cost_type_id'].notna()
                & resolved['master_cost_id'].notna()
                & resolved['source_column'].isin(charge_columns)
            ]
            if not usable.empty:
                resolution_frame = usable[empty_columns].drop_duplicates(
                    ignore_index=True
                )
                resolution_frame['cost_type_id'] = (
                    resolution_frame['cost_type_id'].astype(int)
                )
                resolution_frame['master_cost_id'] = (
                    resolution_frame['master_cost_id'].astype(int)
                )

        # A charge on a code nothing maps and nothing excludes is the failure this
        # service exists to make visible. Reported with its amount, because the size
        # of what would be dropped is the whole argument for stopping.
        migrating_keys = set()
        if not resolution_frame.empty:
            migrating_keys = {
                text_normalization.match_key(code)
                for code in resolution_frame['source_code'].tolist()
            }

        for code, (count, total) in sorted(charged_codes.items()):
            code_key = text_normalization.match_key(code)
            if code_key in migrating_keys or code_key in excluded_keys:
                continue
            problems['unmapped_charged_codes'].append(
                f'{code} ({count} row(s), {total} charged)'
            )

        return resolution_frame, problems

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def rebuild_staging_costs(
        self,
        resolution_frame: pd.DataFrame,
        load_id: int,
        session_id: int,
    ) -> int:
        """Replace this LoadID's RC_STAGING_COSTS rows with the unpivoted charges.

        The unpivot runs server-side as one INSERT ... SELECT rather than reading the
        wide table into pandas and writing it back: the shape is the same CROSS APPLY
        51.tblcosts.sql used to carry, and the rows never need to leave the server.
        Delete and insert share one transaction, so a failure leaves the previous
        contents intact.

        An empty resolution frame still deletes. A re-run that resolves nothing has to
        clear what the previous run staged, or 51.tblcosts.sql would migrate costs this
        configuration no longer produces.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection:
            return 0

        if resolution_frame.empty:
            cursor = db_helper.pyodbc_connection.cursor()
            try:
                cursor.execute(
                    f'DELETE FROM {STAGING_TABLE} WHERE LoadID = ?', int(load_id)
                )
                db_helper.pyodbc_connection.commit()
                return 0
            except Exception:
                db_helper.pyodbc_connection.rollback()
                raise
            finally:
                cursor.close()

        values_rows = []
        for row in resolution_frame.itertuples(index=False):
            # Validated against CODE_PATTERN at load time, so neither the code nor
            # the column name can carry a quote or a bracket.
            values_rows.append(
                f"('{row.source_code}', '{row.source_column}', "
                f'ISNULL(S.[{row.source_column}], 0), '
                f'{int(row.cost_type_id)}, {int(row.master_cost_id)})'
            )

        cursor = db_helper.pyodbc_connection.cursor()
        try:
            cursor.execute(
                f'DELETE FROM {STAGING_TABLE} WHERE LoadID = ?', int(load_id)
            )
            cursor.execute(
                f"""
                INSERT INTO {STAGING_TABLE} WITH (ROWLOCK)
                    (Debtor_Code, CostTypeCode, SourceColumn, Amount,
                     CostTypeID, MasterCostID, LoadID, CreateID,
                     CreateSessionID, CreateTS, StatusID)
                SELECT S.[{SOURCE_KEY_COLUMN}],
                       V.CostTypeCode,
                       V.SourceColumn,
                       V.Amount,
                       V.CostTypeID,
                       V.MasterCostID,
                       ?,
                       1,
                       ?,
                       GETDATE(),
                       1
                FROM {SOURCE_TABLE} AS S WITH (NOLOCK)
                CROSS APPLY (VALUES
                    {(',' + chr(10) + '                    ').join(values_rows)}
                ) V(CostTypeCode, SourceColumn, Amount, CostTypeID, MasterCostID)
                WHERE V.Amount <> 0
                  AND S.[{SOURCE_KEY_COLUMN}] IS NOT NULL
                """,
                int(load_id),
                int(session_id),
            )
            cursor.execute('SELECT @@ROWCOUNT')
            row = cursor.fetchone()
            rows_inserted = int(row[0]) if row and row[0] is not None else 0

            db_helper.pyodbc_connection.commit()
            return rows_inserted

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Post-update re-check
    # ------------------------------------------------------------------

    def get_unmapped_charged_codes_from_db(
        self,
        load_id: int,
        excluded_codes: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Charged codes that RC_STAGING_COSTS did not pick up, read back from the DB.

        Deliberately independent of the resolution frame: it compares what the extract
        charges against what actually landed, so a code lost anywhere between the JSON
        and the insert is caught rather than assumed absent.
        """
        db_helper = self.db_helper
        if not db_helper:
            return []

        charged_codes = self.read_charged_codes()
        if not charged_codes:
            return []

        excluded_keys = {
            text_normalization.match_key(code)
            for code in (excluded_codes or {})
        }

        staged_keys = set()
        if self.staging_table_exists():
            staged = db_helper.execute_query(
                f"""
                SELECT DISTINCT CAST(CostTypeCode AS NVARCHAR(20)) AS CostTypeCode
                FROM {STAGING_TABLE} WITH (NOLOCK)
                WHERE LoadID = {int(load_id)}
                  AND CostTypeCode IS NOT NULL
                """
            )
            if not staged.empty and 'CostTypeCode' in staged.columns:
                staged_keys = {
                    text_normalization.match_key(code)
                    for code in staged['CostTypeCode'].astype(str).tolist()
                }

        unmapped = []
        for code, (count, total) in sorted(charged_codes.items()):
            code_key = text_normalization.match_key(code)
            if code_key in staged_keys or code_key in excluded_keys:
                continue
            unmapped.append(f'{code} ({count} row(s), {total} charged)')
        return unmapped
