"""Explain which accounts 01.tblaccount kept, which it dropped, and why.

The migration's account population is decided by two filters in
`SQL/Migration queries/Direct/01.tblaccount.sql`: a retention WHERE clause, and
the tblAccountStatus lookup. When a downstream count looks short - notes that did
not migrate, an account nobody can find - the question is almost always which of
those two dropped the row. This answers that, and reconciles the answer against
what actually landed in tblAccount.

Read-only by construction: every statement is a SELECT.

Why this is a tool and not a query someone writes each time
----------------------------------------------------------
The retention clause cannot be inverted with NOT (...). Last_Pay_Date is
nullable, so `Last_Pay_Date > @cutoff` is UNKNOWN rather than FALSE on those
rows, and the enclosing OR chain is then UNKNOWN too. In the migration's own
WHERE that is harmless, because UNKNOWN and FALSE both exclude a row. The
negation does not round-trip though - NOT UNKNOWN is UNKNOWN - so
`WHERE NOT (<filter>)` silently reports only the rows where every clause is
definitively FALSE. On uat that is 408 rows against a true figure of 3,376.

So the filter is evaluated into a flag per row and the flag is tested, which is
also how the migration itself behaves. Getting this wrong understates the
exclusions by 8x and it fails quietly, which is why it lives here once rather
than being rewritten per investigation.

    python tools/audit_account_filter.py uat
    python tools/audit_account_filter.py uat --load-id 237
    python tools/audit_account_filter.py uat --by-status
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import db_manager as dbm  # noqa: E402
from config_parser import ConfigParser  # noqa: E402
from env_target import resolve_environment  # noqa: E402  - tools/, alongside this script

# Fallbacks matching variables/migration_variables.json -> constant_variables.
# Only used when the config cannot be read; --closed-months / --pay-months win
# over both, for asking what a different retention window would have kept.
DEFAULT_CLOSED_MONTHS = 13
DEFAULT_PAY_MONTHS = 6


def retention_months(environment: str, variables_dir: str) -> tuple:
    """(ClosedAccountRetentionMonths, RecentPaymentMonths) as 01 would see them."""
    try:
        config = ConfigParser(db_environment=environment,
                              variables_folder=variables_dir)
        variables = config.load_json('migration_variables.json')
        # {"migration_variables": {"constant_variables": {"variables": {...}}}}
        constants = (variables.get('migration_variables', variables)
                     .get('constant_variables', {})
                     .get('variables', {}))
        return (int(constants.get('ClosedAccountRetentionMonths', {})
                    .get('default', DEFAULT_CLOSED_MONTHS)),
                int(constants.get('RecentPaymentMonths', {})
                    .get('default', DEFAULT_PAY_MONTHS)))
    except Exception as e:                                       # noqa: BLE001
        print(f'  (could not read migration_variables.json: {e}; '
              f'using {DEFAULT_CLOSED_MONTHS}/{DEFAULT_PAY_MONTHS})')
        return DEFAULT_CLOSED_MONTHS, DEFAULT_PAY_MONTHS


def flags_cte(closed_months: int, pay_months: int) -> str:
    """01's predicates, per row, as flags rather than as a WHERE.

    Each disjunct is kept separate so the report can say which one saved an
    account, and CASE turns UNKNOWN into 0 exactly as the migration's WHERE
    turns it into an exclusion.
    """
    return f"""
    SELECT  RC.Full_Debt_Code ,
            RC.MA_Status ,
            RC.Last_Pay_Date ,
            CD.DateClosed ,
            CASE WHEN CD.DateClosed IS NULL THEN 1 ELSE 0 END AS D1_StillOpen ,
            CASE WHEN CD.DateClosed > DATEADD(MONTH, -{closed_months}, GETDATE())
                 THEN 1 ELSE 0 END AS D2_ClosedRecently ,
            CASE WHEN RC.Last_Pay_Date > DATEADD(MONTH, -{pay_months}, GETDATE())
                 THEN 1 ELSE 0 END AS D3_RecentLastPay ,
            CASE WHEN EXISTS ( SELECT 1 FROM RC_PAYMENTS PMT
                               WHERE PMT.Debt_Code = RC.Full_Debt_Code
                                 AND PMT.Date_Time_Entered
                                     > DATEADD(MONTH, -{pay_months}, GETDATE()) )
                 THEN 1 ELSE 0 END AS D4_RecentPayment ,
            CASE WHEN EXISTS ( SELECT 1 FROM tblAccountStatus
                               WHERE AccountStatus = RC.MA_Status )
                 THEN 1 ELSE 0 END AS StatusMapped
    FROM    RC_ACCOUNT_EXTRACT RC
            CROSS APPLY ( SELECT TRY_CONVERT(DATETIME,
                                 NULLIF(LTRIM(RTRIM(RC.Closed)), '')) AS DateClosed
                        ) CD
    """


PASSES_RETENTION = 'D1_StillOpen + D2_ClosedRecently + D3_RecentLastPay + D4_RecentPayment > 0'


def report(helper, flags: str, load_id, by_status: bool) -> None:
    def show(title: str, sql: str):
        print()
        print(title)
        print('-' * len(title))
        frame = helper.execute_query(sql)
        print('  (no rows)' if frame.empty else frame.to_string(index=False))
        return frame

    show('Filter decomposition', f"""
        WITH f AS ({flags})
        SELECT  COUNT(*) AS TotalStaged ,
                SUM(CASE WHEN {PASSES_RETENTION} AND StatusMapped = 1
                         THEN 1 ELSE 0 END) AS PassBoth ,
                SUM(CASE WHEN NOT ({PASSES_RETENTION}) AND StatusMapped = 1
                         THEN 1 ELSE 0 END) AS FailRetentionOnly ,
                SUM(CASE WHEN {PASSES_RETENTION} AND StatusMapped = 0
                         THEN 1 ELSE 0 END) AS FailStatusMapOnly ,
                SUM(CASE WHEN NOT ({PASSES_RETENTION}) AND StatusMapped = 0
                         THEN 1 ELSE 0 END) AS FailBoth
        FROM    f
    """)

    show('Which clause keeps each account (not mutually exclusive)', f"""
        WITH f AS ({flags})
        SELECT  SUM(D1_StillOpen) AS D1_StillOpen ,
                SUM(D2_ClosedRecently) AS D2_ClosedRecently ,
                SUM(D3_RecentLastPay) AS D3_RecentLastPay ,
                SUM(D4_RecentPayment) AS D4_RecentPayment
        FROM    f
    """)

    show('Statuses with no tblAccountStatus row', f"""
        WITH f AS ({flags})
        SELECT  ISNULL(MA_Status, '(null)') AS MA_Status ,
                COUNT(*) AS StagedRows ,
                SUM(CASE WHEN {PASSES_RETENTION} THEN 1 ELSE 0 END) AS WouldPassRetention
        FROM    f
        WHERE   StatusMapped = 0
        GROUP BY MA_Status
        ORDER BY COUNT(*) DESC
    """)

    if by_status:
        show('Excluded accounts by status', f"""
            WITH f AS ({flags})
            SELECT  ISNULL(MA_Status, '(null)') AS MA_Status ,
                    COUNT(*) AS Excluded ,
                    SUM(CASE WHEN Last_Pay_Date IS NULL THEN 1 ELSE 0 END) AS NeverPaid ,
                    MIN(DateClosed) AS OldestClosed ,
                    MAX(DateClosed) AS NewestClosed
            FROM    f
            WHERE   NOT ({PASSES_RETENTION}) OR StatusMapped = 0
            GROUP BY MA_Status
            ORDER BY COUNT(*) DESC
        """)

    show('What the exclusions take with them', f"""
        WITH f AS ({flags}) ,
        ex AS ( SELECT Full_Debt_Code , TRY_CONVERT(INT, Full_Debt_Code) AS CodeInt
                FROM   f
                WHERE  NOT ({PASSES_RETENTION}) OR StatusMapped = 0 )
        SELECT  (SELECT COUNT(*) FROM ex) AS ExcludedAccounts ,
                (SELECT COUNT(*) FROM RC_NOTES_EXTRACT N
                 WHERE EXISTS (SELECT 1 FROM ex WHERE ex.CodeInt = N.Extended_Debt_Code)
                ) AS NotesDropped ,
                (SELECT COUNT(*) FROM RC_TREATMENT T
                 WHERE EXISTS (SELECT 1 FROM ex WHERE ex.Full_Debt_Code = T.Full_Debt_Code)
                ) AS TreatmentsDropped ,
                (SELECT COUNT(*) FROM RC_PAYMENTS P
                 WHERE EXISTS (SELECT 1 FROM ex WHERE ex.Full_Debt_Code = P.Debt_Code)
                ) AS PaymentsDropped
    """)

    if load_id is None:
        print()
        print('Pass --load-id to reconcile these figures against tblAccount.')
        return

    # The reconciliation that matters: the filter's verdict should be a bijection
    # with what is in tblAccount. A non-zero either way means something other than
    # these two filters changed the population - a partial run, a later delete, or
    # staging that no longer matches the load.
    frame = show(f'Reconciliation against tblAccount LoadID {load_id}', f"""
        WITH f AS ({flags})
        SELECT  (SELECT COUNT(*) FROM f) AS StagedRows ,
                (SELECT COUNT(*) FROM f
                 WHERE {PASSES_RETENTION} AND StatusMapped = 1) AS ExpectedAccounts ,
                (SELECT COUNT(*) FROM tblAccount
                 WHERE LoadID = {load_id}) AS ActualAccounts ,
                (SELECT COUNT(*) FROM f
                 WHERE {PASSES_RETENTION} AND StatusMapped = 1
                   AND NOT EXISTS (SELECT 1 FROM tblAccount A
                                   WHERE A.LoadID = {load_id}
                                     AND A.AccountNumberPrevious = f.Full_Debt_Code)
                ) AS PassedButMissing ,
                (SELECT COUNT(*) FROM f
                 WHERE (NOT ({PASSES_RETENTION}) OR StatusMapped = 0)
                   AND EXISTS (SELECT 1 FROM tblAccount A
                               WHERE A.LoadID = {load_id}
                                 AND A.AccountNumberPrevious = f.Full_Debt_Code)
                ) AS ExcludedButPresent
    """)

    print()
    if frame.empty:
        return
    row = frame.iloc[0]
    if int(row['PassedButMissing']) == 0 and int(row['ExcludedButPresent']) == 0:
        print('Reconciled: the two filters account for the population exactly.')
    else:
        print(f"NOT reconciled: {int(row['PassedButMissing'])} row(s) pass the "
              f"filters but have no account, {int(row['ExcludedButPresent'])} "
              f"excluded row(s) have one. Something other than 01's filters "
              f"changed this load - check for a partial run, a later delete, or "
              f"staging reloaded since the load.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('environment', nargs='?', default=None,
                        help='Environment name, e.g. uat, testse, dev')
    parser.add_argument('--config', dest='config_path', default=None, metavar='PATH',
                        help='Environment file, or the directory holding <env>.env')
    parser.add_argument('--variables', dest='variables_path', default=None,
                        metavar='DIR', help='Folder holding migration_variables.json')
    parser.add_argument('--load-id', type=int, default=None,
                        help='Reconcile against this tblAccount LoadID')
    parser.add_argument('--by-status', action='store_true',
                        help='Break the excluded accounts down by MA_Status')
    parser.add_argument('--closed-months', type=int, default=None,
                        help='Override ClosedAccountRetentionMonths, to ask what a '
                             'different retention window would have kept')
    parser.add_argument('--pay-months', type=int, default=None,
                        help='Override RecentPaymentMonths')
    args = parser.parse_args()

    environment, config_dir = resolve_environment(args)
    variables_dir = os.path.abspath(
        args.variables_path or os.path.join(REPO_ROOT, 'variables'))

    closed_months, pay_months = retention_months(environment, variables_dir)
    if args.closed_months is not None:
        closed_months = args.closed_months
    if args.pay_months is not None:
        pay_months = args.pay_months

    print('Read-only: every statement is a SELECT. Nothing is written or created.')
    print(f'Environment {environment} '
          f'({os.path.join(config_dir, environment + ".env")})')
    print(f'ClosedAccountRetentionMonths={closed_months}, '
          f'RecentPaymentMonths={pay_months}'
          + ('  (overridden on the command line)'
             if args.closed_months is not None or args.pay_months is not None
             else ''))

    helper = dbm.DatabaseHelper(environment, config_path=config_dir)
    try:
        helper.connect_sqlalchemy()
        report(helper, flags_cte(closed_months, pay_months),
               args.load_id, args.by_status)
    finally:
        if helper.sqlalchemy_engine is not None:
            helper.sqlalchemy_engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
