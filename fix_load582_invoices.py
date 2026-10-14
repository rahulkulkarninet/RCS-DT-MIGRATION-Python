"""Apply the 075.tblinvoice fix to the whole SM9640 load (LoadID 582) in dev-debtrak.
Updates the 315 existing tblInvoice rows in place, links tblPayment.InvoiceID, fills the
DEV-only InvoiceNumber/IssuedDate columns, and reverts the two experimental values left on
the test payment 211587. One transaction; prints before/after counts.
Run from the repo root:  py -3 fix_load582_invoices.py
"""
import sys; sys.path.insert(0, r"C:\Documents\Symbos\RCS-DT-Migration\RCS-DT-Migration-Updated")
import db_manager as dbm
from sqlalchemy import text
h = dbm.DatabaseHelper('dev'); h.connect_sqlalchemy()
LOAD = 582
with h.sqlalchemy_engine.begin() as c:
    r0 = c.execute(text("UPDATE tblBankTransaction SET InvoiceID=NULL WHERE BankTransactionID=159427 AND InvoiceID=38200")).rowcount
    r0b = c.execute(text("UPDATE tblInvoice SET Description=NULL WHERE InvoiceID=38200 AND Description='MONTHEND 112025'")).rowcount
    r1 = c.execute(text("""
        UPDATE I SET
            I.InvoiceRef      = ISNULL(NULLIF(LTRIM(RTRIM(S.Invoice_No)), ''), CONVERT(nvarchar(100), S.Tran_Key)),
            I.IssueDate       = ISNULL(S.Date_Statement_Record_Created, S.[Date]),
            I.CreateTS        = ISNULL(S.Date_Statement_Record_Created, S.[Date]),
            I.InvoiceFromDate = M.MonthStart,
            I.InvoiceToDate   = DATEADD(DAY, -1, DATEADD(MONTH, 1, M.MonthStart)),
            I.ClientReference = S.Run_Name,
            I.Z_ID            = S.Tran_Key
        FROM tblInvoice I
        JOIN tblAccount A ON A.AccountID = I.AccountID AND A.LoadID = :l
        JOIN archive.SM9640_RC_STATEMENT S ON S.Tran_Key = TRY_CONVERT(int, I.InvoiceRef)
                                           AND CONVERT(nvarchar(100), S.Extended_Debt_Code) = A.AccountNumberPrevious
        CROSS APPLY (SELECT CASE WHEN LEN(S.Accounting_Month)=6 AND S.Accounting_Month NOT LIKE '%[^0-9]%'
                                 THEN TRY_CONVERT(date, RIGHT(S.Accounting_Month,4)+LEFT(S.Accounting_Month,2)+'01') END AS MonthStart) M
        WHERE I.Z_ID IS NULL"""), dict(l=LOAD)).rowcount
    r2 = c.execute(text("""
        UPDATE P SET P.InvoiceID = I.InvoiceID
        FROM tblPayment P
        JOIN tblBankTransaction BT ON BT.BankTransactionID = P.BankTransactionID
        JOIN tblInvoice I ON I.AccountID = P.AccountID AND I.Z_ID = TRY_CONVERT(int, BT.Z_REF)
        WHERE P.LoadID = :l AND P.InvoiceID IS NULL"""), dict(l=LOAD)).rowcount
    r3 = c.execute(text("""
        UPDATE I SET I.InvoiceNumber = I.InvoiceRef, I.IssuedDate = I.IssueDate
        FROM tblInvoice I JOIN tblAccount A ON A.AccountID = I.AccountID
        WHERE A.LoadID = :l AND I.Z_ID IS NOT NULL AND I.InvoiceNumber IS NULL"""), dict(l=LOAD)).rowcount
    print(f"reverted test extras: {r0}/{r0b} | invoices updated: {r1} | payments linked: {r2} | InvoiceNumber/IssuedDate filled: {r3}")
q = lambda s: print(h.execute_query(s).to_string(), "\n")
q(f"SELECT COUNT(*) invoices, SUM(CASE WHEN I.Z_ID IS NULL THEN 1 ELSE 0 END) no_zid, SUM(CASE WHEN I.ClientReference='MONTHEND' THEN 1 ELSE 0 END) monthend FROM tblInvoice I JOIN tblAccount A ON A.AccountID=I.AccountID WHERE A.LoadID={LOAD}")
q(f"SELECT COUNT(*) payments, SUM(CASE WHEN InvoiceID IS NULL THEN 1 ELSE 0 END) unlinked FROM tblPayment WHERE LoadID={LOAD}")
q(f"""SELECT COUNT(*) unlinked_without_statement_row FROM tblPayment P JOIN tblBankTransaction BT ON BT.BankTransactionID=P.BankTransactionID
      WHERE P.LoadID={LOAD} AND P.InvoiceID IS NULL AND NOT EXISTS (SELECT 1 FROM archive.SM9640_RC_STATEMENT S WHERE S.Tran_Key=TRY_CONVERT(int,BT.Z_REF))""")
