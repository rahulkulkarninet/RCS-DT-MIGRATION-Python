"""Re-status in-scope accounts that have no active arrangement behind their RCS status.

Mirrors status_service.py / treatment_step_service.py: a config file
(variables/arrangement_status_rules.json) and derived columns on the staging extract. It
runs after both of them in the mapping phase and overrides what they derived:

  RC_ACCOUNT_EXTRACT.MA_Status_AccountStatusID   (read by 01.tblaccount)
  RC_ACCOUNT_EXTRACT.Treatment_NewStep /
  RC_ACCOUNT_EXTRACT.Treatment_NewTreatmentCode  (read by 78.tblAccount_Treatment)

and records what it saw in RC_ACCOUNT_EXTRACT.Arrangement_Active (INSTALMENT, DEAL or
NONE for every in-scope open account; NULL elsewhere) for the check reports.

The rule is Suz's (Treatment Mapping chat, 13 Oct 2026; see the config's _comment): an
open account in an instalment / PTP / dishonour status with no arrangement row carrying a
next instalment date and no deal with a due date (past or future: a PTP stays active
through Debtrak's grace period, Suz 13 Oct) is not left on an arrangement status. It goes to Treatment Allocated (keeping its derived step when it is
on a mapped RCS treatment, or at step 30 when it is untreated and the debt is a year old
or younger) or, untreated and older than a year, to Treatment - End of Process with no
treatment.
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import derived_mapping
import text_normalization
from status_service import TARGET_COLUMN as STATUS_ID_COLUMN
from treatment_step_service import TARGET_CODE_COLUMN as STEP_CODE_COLUMN
from treatment_step_service import TARGET_COLUMN as STEP_COLUMN

SOURCE_TABLE = 'RC_ACCOUNT_EXTRACT'
TARGET_COLUMN = 'Arrangement_Active'
UNTREATED_CODE = 'UNTREATED'   # what treatment_step_service writes for an open account with no mapped treatment

ACTIVE_INSTALMENT = 'INSTALMENT'
ACTIVE_DEAL = 'DEAL'
ACTIVE_NONE = 'NONE'


class ArrangementStatusService:
    """Config -> RC_ACCOUNT_EXTRACT.Arrangement_Active, status and step overrides."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    # --- schema -----------------------------------------------------------------

    def target_column_exists(self) -> bool:
        return derived_mapping.column_exists(self.db_helper, SOURCE_TABLE, TARGET_COLUMN)

    def ensure_target_column(self) -> List[str]:
        """Add Arrangement_Active to an existing staging table. Returns the columns added.

        The schema file carries it for a fresh deploy; an environment whose
        RC_ACCOUNT_EXTRACT predates it gets it here (same as Migrations/009).
        """
        db_helper = self.db_helper
        if not db_helper or not getattr(db_helper, 'pyodbc_connection', None):
            return []
        if derived_mapping.column_exists(db_helper, SOURCE_TABLE, TARGET_COLUMN):
            return []
        connection = db_helper.pyodbc_connection
        cursor = connection.cursor()
        try:
            cursor.execute(f'ALTER TABLE dbo.{SOURCE_TABLE} ADD [{TARGET_COLUMN}] NVARCHAR(20) NULL')
            connection.commit()
            return [TARGET_COLUMN]
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
            return 'arrangement_status_rules.json must contain a JSON object'
        scope = config.get('in_scope_statuses')
        if not isinstance(scope, dict) or not (scope.get('prefixes') or scope.get('codes')):
            return "arrangement_status_rules.json needs 'in_scope_statuses' with prefixes and/or codes"
        sources = config.get('active_arrangement')
        if not isinstance(sources, dict) or not sources:
            return "arrangement_status_rules.json needs a non-empty 'active_arrangement' object"
        for name, spec in sources.items():
            if not isinstance(spec, dict) or not all(k in spec for k in ('table', 'debt_code', 'date_column')):
                return f"active_arrangement '{name}' needs table, debt_code and date_column"
        rule = config.get('no_active_arrangement')
        if not isinstance(rule, dict):
            return "arrangement_status_rules.json needs a 'no_active_arrangement' object"
        with_code = rule.get('with_treatment_code')
        without = rule.get('without_treatment_code')
        if not isinstance(with_code, dict) or not with_code.get('status'):
            return "no_active_arrangement.with_treatment_code needs a status"
        if not isinstance(without, dict) or 'max_age_days' not in without:
            return "no_active_arrangement.without_treatment_code needs max_age_days, young and old"
        for band in ('young', 'old'):
            spec = without.get(band)
            if not isinstance(spec, dict) or not spec.get('status') or 'step' not in spec:
                return f"no_active_arrangement.without_treatment_code.{band} needs status and step (step may be null)"
        return None

    # --- lookups ----------------------------------------------------------------

    def resolve_status_ids(self, config: Dict[str, Any]) -> Tuple[Dict[str, int], List[str]]:
        """AccountStatusID for every status label the config names, by the label text.

        Same matching as status_service: the label is normalised and keyed, so dashes,
        spacing and case do not matter. Returns the resolved map and the labels left
        unresolved (a fatal configuration error for the caller).
        """
        rule = config['no_active_arrangement']
        labels = {
            str(rule['with_treatment_code']['status']).strip(),
            str(rule['without_treatment_code']['young']['status']).strip(),
            str(rule['without_treatment_code']['old']['status']).strip(),
        }
        db_helper = self.db_helper
        resolved: Dict[str, int] = {}
        if not db_helper:
            return resolved, sorted(labels)
        lookup = db_helper.execute_query(
            """
            SELECT AccountStatusID, CAST(AccountStatus AS NVARCHAR(4000)) AS AccountStatus
            FROM tblAccountStatus
            WHERE AccountStatus IS NOT NULL AND StatusID = 1
            """
        )
        keys: Dict[str, int] = {}
        if lookup is not None and not lookup.empty:
            for ident, label in lookup[['AccountStatusID', 'AccountStatus']].itertuples(index=False, name=None):
                key = text_normalization.match_key(text_normalization.normalize_lookup_key(str(label).strip()))
                keys.setdefault(key, int(ident))
        missing: List[str] = []
        for label in labels:
            key = text_normalization.match_key(text_normalization.normalize_lookup_key(label))
            if key in keys:
                resolved[label] = keys[key]
            else:
                missing.append(label)
        return resolved, sorted(missing)

    # --- SQL fragments ----------------------------------------------------------

    @staticmethod
    def _scope_sql(config: Dict[str, Any], status_expr: str) -> str:
        """WHERE fragment: the cleaned, upper-cased MA_Status is in scope."""
        scope = config['in_scope_statuses']
        parts: List[str] = []
        for prefix in scope.get('prefixes') or []:
            p = str(prefix).strip().upper().replace("'", "''")
            if p:
                parts.append(f"UPPER({status_expr}) LIKE '{p}%'")
        codes = [str(c).strip().upper().replace("'", "''") for c in (scope.get('codes') or []) if str(c).strip()]
        if codes:
            parts.append(f"UPPER({status_expr}) IN ({', '.join(repr(c) for c in codes)})")
        return '(' + ' OR '.join(parts) + ')' if parts else '(1 = 0)'

    @staticmethod
    def _exists_sql(spec: Dict[str, Any], debt_code_expr: str) -> str:
        """EXISTS fragment: the debt has a row in the arrangement/deal table that counts as active."""
        table = str(spec['table']).strip('[]')
        key = str(spec['debt_code']).strip('[]')
        date_col = str(spec['date_column']).strip('[]')
        date_expr = f"TRY_CONVERT(DATETIME, x.[{date_col}])"
        condition = f"{date_expr} IS NOT NULL"
        if spec.get('date_must_be_today_or_later'):
            condition += f" AND {date_expr} >= CAST(GETDATE() AS DATE)"
        return (f"EXISTS (SELECT 1 FROM dbo.[{table}] AS x "
                f"WHERE TRY_CONVERT(BIGINT, x.[{key}]) = TRY_CONVERT(BIGINT, {debt_code_expr}) AND {condition})")

    # --- derived columns --------------------------------------------------------

    def apply(self, config: Dict[str, Any], status_ids: Dict[str, int]) -> Dict[str, int]:
        """Fill Arrangement_Active and apply the no-arrangement overrides. One transaction.

        Returns counts: in_scope, active_instalment, active_deal, none, treated_to_status,
        young_to_step, old_no_treatment.
        """
        db_helper = self.db_helper
        zero = {'in_scope': 0, 'active_instalment': 0, 'active_deal': 0, 'none': 0,
                'treated_to_status': 0, 'young_to_step': 0, 'old_no_treatment': 0}
        if not db_helper or not getattr(db_helper, 'pyodbc_connection', None):
            return zero

        cols = config.get('source_columns', {}) or {}
        status = derived_mapping.clean_sql(f"rc.[{cols.get('status', 'MA_Status')}]")
        debt_code = f"rc.[{cols.get('debt_code', 'Full_Debt_Code')}]"
        closed = f"rc.[{cols.get('closed_date', 'Date_Closed')}]"
        is_open = f"({closed} IS NULL OR LTRIM(RTRIM(CAST({closed} AS NVARCHAR(100)))) = '')"
        age_days = (f"DATEDIFF(DAY, TRY_CONVERT(DATETIME, rc.[{cols.get('age_from', 'Date_Time_Entered')}]), "
                    f"CAST(GETDATE() AS DATE))")
        in_scope = f"{is_open} AND {self._scope_sql(config, status)}"

        sources = config['active_arrangement']
        instal = sources.get('instalment')
        deal = sources.get('deal')
        instal_exists = self._exists_sql(instal, debt_code) if instal else '(1 = 0)'
        deal_exists = self._exists_sql(deal, debt_code) if deal else '(1 = 0)'

        rule = config['no_active_arrangement']
        treated_status_id = status_ids[str(rule['with_treatment_code']['status']).strip()]
        without = rule['without_treatment_code']
        max_age = int(without['max_age_days'])
        young_status_id = status_ids[str(without['young']['status']).strip()]
        young_step = without['young'].get('step')
        old_status_id = status_ids[str(without['old']['status']).strip()]
        old_step = without['old'].get('step')

        treated = f"(rc.[{STEP_CODE_COLUMN}] IS NOT NULL AND rc.[{STEP_CODE_COLUMN}] <> '{UNTREATED_CODE}')"
        none_rows = f"rc.[{TARGET_COLUMN}] = '{ACTIVE_NONE}'"

        def step_assignment(step: Any) -> str:
            if step is None:
                return f"rc.[{STEP_COLUMN}] = NULL, rc.[{STEP_CODE_COLUMN}] = NULL"
            return f"rc.[{STEP_COLUMN}] = {int(step)}, rc.[{STEP_CODE_COLUMN}] = '{UNTREATED_CODE}'"

        connection = db_helper.pyodbc_connection
        cursor = connection.cursor()

        def rowcount() -> int:
            cursor.execute('SELECT @@ROWCOUNT')
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        def count(where: str) -> int:
            cursor.execute(f'SELECT COUNT(*) FROM dbo.{SOURCE_TABLE} AS rc WHERE {where}')
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        try:
            cursor.execute(
                f'UPDATE dbo.{SOURCE_TABLE} SET [{TARGET_COLUMN}] = NULL WHERE [{TARGET_COLUMN}] IS NOT NULL'
            )
            # 1. what each in-scope open account has behind its status
            cursor.execute(
                f"""
                UPDATE rc
                SET rc.[{TARGET_COLUMN}] = CASE WHEN {instal_exists} THEN '{ACTIVE_INSTALMENT}'
                                                WHEN {deal_exists} THEN '{ACTIVE_DEAL}'
                                                ELSE '{ACTIVE_NONE}' END
                FROM dbo.{SOURCE_TABLE} AS rc
                WHERE {in_scope}
                """
            )
            counts = dict(zero)
            counts['in_scope'] = rowcount()
            counts['active_instalment'] = count(f"rc.[{TARGET_COLUMN}] = '{ACTIVE_INSTALMENT}'")
            counts['active_deal'] = count(f"rc.[{TARGET_COLUMN}] = '{ACTIVE_DEAL}'")
            counts['none'] = count(none_rows)

            # 2. no active arrangement, on a mapped RCS treatment: status only, step stays
            cursor.execute(
                f"""
                UPDATE rc SET rc.[{STATUS_ID_COLUMN}] = {treated_status_id}
                FROM dbo.{SOURCE_TABLE} AS rc
                WHERE {none_rows} AND {treated}
                """
            )
            counts['treated_to_status'] = rowcount()

            # 3. no active arrangement, untreated, debt a year old or younger
            cursor.execute(
                f"""
                UPDATE rc SET rc.[{STATUS_ID_COLUMN}] = {young_status_id}, {step_assignment(young_step)}
                FROM dbo.{SOURCE_TABLE} AS rc
                WHERE {none_rows} AND NOT {treated} AND ISNULL({age_days}, {max_age + 1}) <= {max_age}
                """
            )
            counts['young_to_step'] = rowcount()

            # 4. no active arrangement, untreated, older: no treatment
            cursor.execute(
                f"""
                UPDATE rc SET rc.[{STATUS_ID_COLUMN}] = {old_status_id}, {step_assignment(old_step)}
                FROM dbo.{SOURCE_TABLE} AS rc
                WHERE {none_rows} AND NOT {treated} AND ISNULL({age_days}, {max_age + 1}) > {max_age}
                """
            )
            counts['old_no_treatment'] = rowcount()
            connection.commit()
            return counts
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    # --- checks -----------------------------------------------------------------

    def summary(self) -> List[Tuple[str, str, int]]:
        """(Arrangement_Active, RCS status, accounts) for the log."""
        db_helper = self.db_helper
        if not db_helper:
            return []
        frame = db_helper.execute_query(
            f"""
            SELECT [{TARGET_COLUMN}] AS active, UPPER({derived_mapping.clean_sql('[MA_Status]')}) AS rcs_status, COUNT(*) AS n
            FROM dbo.{SOURCE_TABLE}
            WHERE [{TARGET_COLUMN}] IS NOT NULL
            GROUP BY [{TARGET_COLUMN}], UPPER({derived_mapping.clean_sql('[MA_Status]')})
            ORDER BY [{TARGET_COLUMN}], n DESC
            """
        )
        if frame is None or frame.empty:
            return []
        return [(str(a), str(s), int(n)) for a, s, n in frame.itertuples(index=False, name=None)]
