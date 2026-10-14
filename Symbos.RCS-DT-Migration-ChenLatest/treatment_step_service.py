"""Derive the GS-COMBINED step each open account is allocated at (78.tblAccount_Treatment).

Mirrors status_service.py: a config file (variables/treatment_step_codes.json), a map
table rebuilt on every run (RC_TREATMENT_CODE_MAP), and a derived column on the staging
extract (RC_ACCOUNT_EXTRACT.Treatment_NewStep, plus Treatment_NewTreatmentCode for the
check report) that the SQL batch reads. The source columns keep the values RCS sent.

The rule is Suz's own (see the config's _comment): ladder offset of the new treatment +
RCS next step, capped at the end of that treatment's ladder; untreated open accounts go
to the default step unless an age band catches them; closed accounts get nothing.
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import derived_mapping

SOURCE_TABLE = 'RC_ACCOUNT_EXTRACT'
TARGET_COLUMN = 'Treatment_NewStep'
TARGET_CODE_COLUMN = 'Treatment_NewTreatmentCode'
MAP_TABLE = 'RC_TREATMENT_CODE_MAP'
_MAP_INSERT_CHUNK = 400   # 5 parameters a row, well under the 2100-parameter limit


class TreatmentStepService:
    """Config -> RC_TREATMENT_CODE_MAP -> RC_ACCOUNT_EXTRACT.Treatment_NewStep."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    # --- schema -----------------------------------------------------------------

    def target_columns_exist(self) -> bool:
        return (derived_mapping.column_exists(self.db_helper, SOURCE_TABLE, TARGET_COLUMN)
                and derived_mapping.column_exists(self.db_helper, SOURCE_TABLE, TARGET_CODE_COLUMN))

    def ensure_target_columns(self) -> List[str]:
        """Add the derived columns to an existing staging table. Returns the columns added.

        The schema file carries them for a fresh deploy; an environment whose
        RC_ACCOUNT_EXTRACT predates them gets them here (same as Migrations/008) so
        a run is not blocked on a hand-run ALTER.
        """
        db_helper = self.db_helper
        if not db_helper or not getattr(db_helper, 'pyodbc_connection', None):
            return []
        # Find every missing column before the first ALTER: column_exists reads through
        # the SQLAlchemy connection, and an uncommitted ALTER on the pyodbc connection
        # holds a schema lock that would block that read (self-deadlock).
        missing = [(column, sql_type)
                   for column, sql_type in ((TARGET_COLUMN, 'INT'), (TARGET_CODE_COLUMN, 'NVARCHAR(50)'))
                   if not derived_mapping.column_exists(db_helper, SOURCE_TABLE, column)]
        if not missing:
            return []
        added: List[str] = []
        connection = db_helper.pyodbc_connection
        cursor = connection.cursor()
        try:
            for column, sql_type in missing:
                cursor.execute(f'ALTER TABLE dbo.{SOURCE_TABLE} ADD [{column}] {sql_type} NULL')
                added.append(column)
            connection.commit()
            return added
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    # --- config -----------------------------------------------------------------

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> Optional[str]:
        """Return a message describing the first problem, or None when the file is usable."""
        if not isinstance(config, dict):
            return 'treatment_step_codes.json must contain a JSON object'
        ladder = config.get('ladder')
        codes = config.get('rcs_treatment_codes')
        untreated = config.get('untreated')
        if not isinstance(ladder, dict) or not ladder:
            return "treatment_step_codes.json needs a non-empty 'ladder' object"
        for new_code, spec in ladder.items():
            if not isinstance(spec, dict) or 'first_step' not in spec or 'last_step' not in spec:
                return f"ladder entry '{new_code}' needs first_step and last_step"
            if int(spec['first_step']) < 1 or int(spec['last_step']) < int(spec['first_step']):
                return f"ladder entry '{new_code}' has an impossible first_step/last_step"
        if not isinstance(codes, dict):
            return "treatment_step_codes.json needs an 'rcs_treatment_codes' object"
        for new_code, rcs_codes in codes.items():
            if new_code not in ladder:
                return f"rcs_treatment_codes names '{new_code}', which is not in the ladder"
            if not isinstance(rcs_codes, list):
                return f"rcs_treatment_codes['{new_code}'] must be a list"
        if not isinstance(untreated, dict) or 'default_step' not in untreated:
            return "treatment_step_codes.json needs 'untreated.default_step'"
        for band in untreated.get('age_bands', []) or []:
            if not isinstance(band, dict) or 'max_age_days' not in band or 'step' not in band:
                return 'every untreated.age_bands entry needs max_age_days and step'
        return None

    @staticmethod
    def load_code_map_frame(config: Dict[str, Any]) -> Tuple[pd.DataFrame, int]:
        """One row per RCS treatment code: (RCS_Code, New_Treatment_Code, Step_Offset, Last_Step).

        Returns the frame and the number of duplicate codes skipped (first listing wins,
        as account_status_codes.json does).
        """
        ladder = config['ladder']
        rows: List[Dict[str, Any]] = []
        seen = set()
        duplicates = 0
        for new_code, rcs_codes in config['rcs_treatment_codes'].items():
            spec = ladder[new_code]
            offset = int(spec['first_step']) - 1
            last = int(spec['last_step'])
            for code in rcs_codes:
                key = str(code).strip()
                if not key:
                    continue
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                rows.append({
                    'RCS_Code': key,
                    'New_Treatment_Code': str(new_code),
                    'Step_Offset': offset,
                    'Last_Step': last,
                })
        return pd.DataFrame(rows, columns=['RCS_Code', 'New_Treatment_Code', 'Step_Offset', 'Last_Step']), duplicates

    # --- map table --------------------------------------------------------------

    def write_code_map(self, frame: pd.DataFrame) -> int:
        """Create RC_TREATMENT_CODE_MAP if needed, then replace its rows. Returns rows written."""
        db_helper = self.db_helper
        if not db_helper or not getattr(db_helper, 'pyodbc_connection', None):
            return 0
        connection = db_helper.pyodbc_connection
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"IF OBJECT_ID(N'dbo.{MAP_TABLE}', N'U') IS NULL "
                f"CREATE TABLE dbo.{MAP_TABLE} ("
                "RCS_Code NVARCHAR(50) NOT NULL PRIMARY KEY, "
                "New_Treatment_Code NVARCHAR(50) NOT NULL, "
                "Step_Offset INT NOT NULL, "
                "Last_Step INT NOT NULL)"
            )
            cursor.execute(f'TRUNCATE TABLE dbo.{MAP_TABLE}')
            written = 0
            rows = [tuple(r) for r in frame.itertuples(index=False, name=None)]
            for start in range(0, len(rows), _MAP_INSERT_CHUNK):
                chunk = rows[start:start + _MAP_INSERT_CHUNK]
                placeholders = ', '.join(['(?, ?, ?, ?)'] * len(chunk))
                params = [v for row in chunk for v in (str(row[0]), str(row[1]), int(row[2]), int(row[3]))]
                cursor.execute(
                    f'INSERT INTO dbo.{MAP_TABLE} (RCS_Code, New_Treatment_Code, Step_Offset, Last_Step) '
                    f'VALUES {placeholders}',
                    params,
                )
                written += len(chunk)
            connection.commit()
            return written
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    # --- derived column ---------------------------------------------------------

    def assign_steps(self, config: Dict[str, Any]) -> Dict[str, int]:
        """Fill Treatment_NewStep / Treatment_NewTreatmentCode for every open account.

        One transaction: clear both columns, set the treated rows from the map table,
        then the untreated open rows from the age bands / default. Returns counts.
        """
        db_helper = self.db_helper
        if not db_helper or not getattr(db_helper, 'pyodbc_connection', None):
            return {'treated': 0, 'untreated': 0, 'closed': 0}

        cols = config.get('source_columns', {}) or {}
        current = derived_mapping.clean_sql(f"rc.[{cols.get('current_treatment', 'Current_Treatment')}]")
        next_step = f"TRY_CONVERT(INT, rc.[{cols.get('next_step', 'MA_Next_Step_No')}])"
        closed = f"rc.[{cols.get('closed_date', 'Date_Closed')}]"
        is_open = f"({closed} IS NULL OR LTRIM(RTRIM(CAST({closed} AS NVARCHAR(100)))) = '')"
        age_days = (f"DATEDIFF(DAY, TRY_CONVERT(DATETIME, rc.[{cols.get('age_from', 'Date_Time_Entered')}]), "
                    f"CAST(GETDATE() AS DATE))")

        untreated = config['untreated']
        bands = sorted(untreated.get('age_bands', []) or [], key=lambda b: int(b['max_age_days']))
        band_sql = ' '.join(
            f"WHEN {age_days} <= {int(b['max_age_days'])} THEN {int(b['step'])}" for b in bands
        )
        untreated_step = (f"CASE {band_sql} ELSE {int(untreated['default_step'])} END"
                          if band_sql else str(int(untreated['default_step'])))

        connection = db_helper.pyodbc_connection
        cursor = connection.cursor()

        def rowcount() -> int:
            cursor.execute('SELECT @@ROWCOUNT')
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        try:
            cursor.execute(
                f'UPDATE dbo.{SOURCE_TABLE} SET [{TARGET_COLUMN}] = NULL, [{TARGET_CODE_COLUMN}] = NULL '
                f'WHERE [{TARGET_COLUMN}] IS NOT NULL OR [{TARGET_CODE_COLUMN}] IS NOT NULL'
            )
            # 1. accounts on a known RCS treatment with a numeric next step
            cursor.execute(
                f"""
                UPDATE rc
                SET rc.[{TARGET_COLUMN}] = CASE WHEN m.Step_Offset + {next_step} > m.Last_Step
                                                THEN m.Last_Step
                                                ELSE m.Step_Offset + {next_step} END,
                    rc.[{TARGET_CODE_COLUMN}] = m.New_Treatment_Code
                FROM dbo.{SOURCE_TABLE} AS rc
                INNER JOIN dbo.{MAP_TABLE} AS m ON m.RCS_Code = {current}
                WHERE {is_open} AND {next_step} IS NOT NULL AND {next_step} >= 1
                """
            )
            treated = rowcount()
            # 2. every other open account: no treatment, unknown code, or no usable step
            cursor.execute(
                f"""
                UPDATE rc
                SET rc.[{TARGET_COLUMN}] = {untreated_step},
                    rc.[{TARGET_CODE_COLUMN}] = 'UNTREATED'
                FROM dbo.{SOURCE_TABLE} AS rc
                WHERE {is_open} AND rc.[{TARGET_COLUMN}] IS NULL
                """
            )
            untreated_rows = rowcount()
            cursor.execute(f'SELECT COUNT(*) FROM dbo.{SOURCE_TABLE} AS rc WHERE NOT {is_open}')
            closed_rows = int(cursor.fetchone()[0])
            connection.commit()
            return {'treated': treated, 'untreated': untreated_rows, 'closed': closed_rows}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    # --- checks -----------------------------------------------------------------

    def unmapped_treatment_codes(self, config: Dict[str, Any]) -> List[Tuple[str, int]]:
        """RCS treatment codes on open accounts that the config does not know, with counts.

        Those accounts fall to the untreated rule; the list is for the log and for
        the next edit of treatment_step_codes.json.
        """
        db_helper = self.db_helper
        if not db_helper:
            return []
        cols = config.get('source_columns', {}) or {}
        current = derived_mapping.clean_sql(f"rc.[{cols.get('current_treatment', 'Current_Treatment')}]")
        closed = f"rc.[{cols.get('closed_date', 'Date_Closed')}]"
        frame = db_helper.execute_query(
            f"""
            SELECT {current} AS rcs_code, COUNT(*) AS n
            FROM dbo.{SOURCE_TABLE} AS rc
            WHERE ({closed} IS NULL OR LTRIM(RTRIM(CAST({closed} AS NVARCHAR(100)))) = '')
              AND {current} IS NOT NULL AND {current} <> ''
              AND NOT EXISTS (SELECT 1 FROM dbo.{MAP_TABLE} AS m WHERE m.RCS_Code = {current})
            GROUP BY {current}
            ORDER BY n DESC
            """
        )
        if frame is None or frame.empty:
            return []
        return [(str(code), int(n)) for code, n in frame.itertuples(index=False, name=None)]

    def step_summary(self) -> List[Tuple[str, int, int]]:
        """(new treatment code, step, accounts) for the log."""
        db_helper = self.db_helper
        if not db_helper:
            return []
        frame = db_helper.execute_query(
            f"""
            SELECT [{TARGET_CODE_COLUMN}] AS code, [{TARGET_COLUMN}] AS step, COUNT(*) AS n
            FROM dbo.{SOURCE_TABLE}
            WHERE [{TARGET_COLUMN}] IS NOT NULL
            GROUP BY [{TARGET_CODE_COLUMN}], [{TARGET_COLUMN}]
            ORDER BY [{TARGET_COLUMN}]
            """
        )
        if frame is None or frame.empty:
            return []
        return [(str(c), int(s), int(n)) for c, s, n in frame.itertuples(index=False, name=None)]
