-- One tblInvoice row per RC_STATEMENT row (one per payment), carrying the
-- source "invoice information" shown on the WorkDesk Payment Transaction screen:
--   Month        -> InvoiceFromDate / InvoiceToDate (first / last day of Accounting_Month, MMYYYY)
--   Run Name     -> ClientReference
--   Date Created -> IssueDate and CreateTS (Date_Statement_Record_Created)
--   Invoice No   -> InvoiceRef (e.g. RSM2511-081); source Tran_Key kept in Z_ID
INSERT  INTO tblInvoice WITH ( ROWLOCK )
        ( EntityID ,
          AccountID ,
          InvoiceDesc ,
          IssueDate ,
          InvoiceFromDate ,
          InvoiceToDate ,
          PaymentToSelection ,
          InvoiceTotal ,
          CreateTS ,
          CreateID ,
          CreateSessionID ,
          StatusID ,
          InvoiceRef ,
          ClientReference ,
          Z_ID ,
          Reversed
        )
        SELECT  {{EntityID}} ,
                A.AccountID ,
                S.Particulars ,
                ISNULL(S.Date_Statement_Record_Created, S.[Date]) ,
                M.MonthStart ,
                M.MonthEnd ,
                '2' , --Direct
                NULL , --RC TO Provide Field
                ISNULL(S.Date_Statement_Record_Created, S.[Date]) ,
                1 ,
                {{CurrentSessionID}} ,
                1 ,
                ISNULL(NULLIF(LTRIM(RTRIM(S.Invoice_No)), ''), CONVERT(nvarchar(100), S.Tran_Key)) ,
                S.Run_Name ,
                S.Tran_Key ,
                0
        FROM    RC_STATEMENT S
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CONVERT(nvarchar(100), S.Extended_Debt_Code)
                CROSS APPLY ( SELECT  CASE WHEN LEN(S.Accounting_Month) = 6 AND S.Accounting_Month NOT LIKE '%[^0-9]%'
                                           THEN TRY_CONVERT(date, RIGHT(S.Accounting_Month, 4) + LEFT(S.Accounting_Month, 2) + '01')
                                      END AS MonthStart ) M0
                CROSS APPLY ( SELECT  M0.MonthStart ,
                                      DATEADD(DAY, -1, DATEADD(MONTH, 1, M0.MonthStart)) AS MonthEnd ) M
        WHERE   A.LoadID = {{LoadID}}
        ;

-- Link each migrated payment to its invoice row.
-- RC_PAYMENTS.Transaction_No is stored on tblBankTransaction.Z_REF (048) and equals RC_STATEMENT.Tran_Key (= tblInvoice.Z_ID).
UPDATE  P
SET     P.InvoiceID = I.InvoiceID
FROM    tblPayment P
        INNER JOIN tblBankTransaction BT WITH ( NOLOCK ) ON BT.BankTransactionID = P.BankTransactionID
        INNER JOIN tblInvoice I WITH ( NOLOCK ) ON I.AccountID = P.AccountID
                                               AND I.Z_ID = TRY_CONVERT(int, BT.Z_REF)
WHERE   P.LoadID = {{LoadID}}
        AND P.InvoiceID IS NULL
        ;

-- Newer Debtrak builds (dev-debtrak since Apr-2026) add InvoiceNumber / IssuedDate to tblInvoice.
-- Fill them when present so the IntelliEdge UI sees the invoice; skipped silently where the columns do not exist.
IF COL_LENGTH('dbo.tblInvoice', 'InvoiceNumber') IS NOT NULL AND COL_LENGTH('dbo.tblInvoice', 'IssuedDate') IS NOT NULL
BEGIN
    EXEC sp_executesql N'
        UPDATE  I
        SET     I.InvoiceNumber = I.InvoiceRef ,
                I.IssuedDate    = I.IssueDate
        FROM    tblInvoice I
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountID = I.AccountID
        WHERE   A.LoadID = @LoadID
                AND I.Z_ID IS NOT NULL
                AND I.InvoiceNumber IS NULL ;' ,
        N'@LoadID int' , @LoadID = {{LoadID}} ;
END
;
