INSERT  INTO tblBankTransaction WITH ( ROWLOCK )
        ( BankTransaction ,
          BankTransactionDescription ,
          BankTransactionReference ,
          BankTransactionDate ,
          BankTransactionMethodID ,
          BankedTo_BankAccountID ,
          CurrencyID ,
          ChequeNumber ,
          FromBSB ,
          ChequeClearanceDate ,
          DishonouredDate ,
          CurrencyRate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID ,
          Z_REF
        )
        SELECT DISTINCT
                -- Reversed payments (Payment_Status 'R') arrive with Payment_Amount blank on the original
                -- and 0.00 on the reversal; the signed amount is only in Payment_Amount_1. Elsewhere the two
                -- columns are equal, so fall back whenever Payment_Amount is missing or zero.
                ISNULL(X.Amount, 0) ,
                -- Description: RCS Payment_Description is empty in the extracts, so surface the two
                -- RCS reference numbers the tester expects to see (WorkDesk "Transaction No" and
                -- "Payment Ref. No"). They are otherwise only stored in Z_REF / tblPayment.Z_ID,
                -- which no Debtrak screen displays.
                CONCAT_WS(' | ',
                          NULLIF(LTRIM(RTRIM(P.Payment_Description)), ''),
                          'RCS Transaction No: ' + NULLIF(LTRIM(RTRIM(P.Transaction_No)), ''),
                          'RCS Payment Ref No: ' + CONVERT(nvarchar(20), P.ZID)) ,
                P.Full_Reference_Details ,
                -- Reversal legs carry the original payment's dates in the extract; the day the bank
                -- bounced it (Date_Dishonoured) is the real reversal date, as a native reversal would use.
                IIF(X.IsReversalLeg = 1, ISNULL(P.Date_Dishonoured, P.Effective_Date), P.Effective_Date) ,
                P.Payment_Method_BankTransactionMethodID, --BankTransactionMethodID, set by bank_transaction_method_service.py
                -- Banked-to account left blank (Rahul, 2026-10-09): the extract carries no banked-to
                -- account and the host default (vwHost.BankAccountID_DefaultHost) has been removed;
                -- the migration must not invent one.
                NULL ,
                1 , -- AUD, to run via mapping table
                P.Cheque_No ,
                P.BSB_Code ,
                P.Date_Cleared ,
                IIF(X.IsReversalLeg = 1 AND P.Payment_Status = 'D', P.Date_Dishonoured, NULL) , -- DishonouredDate
                1.0 ,
                1 ,
                {{CurrentSessionID}} ,
                IIF(X.IsReversalLeg = 1, ISNULL(P.Date_Dishonoured, P.Date_Time_Entered), P.Date_Time_Entered) , --GETDATE() ,
                1 ,
                {{LoadID}} ,
                P.Transaction_No
        FROM    RC_PAYMENTS P
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON CONVERT(nvarchar(100), P.Debt_Code) = A.AccountNumberPrevious
                CROSS APPLY ( SELECT  COALESCE(NULLIF(P.Payment_Amount, 0), P.Payment_Amount_1) AS Amount ) X0
                CROSS APPLY ( SELECT  X0.Amount ,
                                      -- The negative row of a reversed/dishonoured pair (both rows carry Rev_Code).
                                      IIF(P.Rev_Code IS NOT NULL AND X0.Amount < 0, 1, 0) AS IsReversalLeg ) X
        WHERE   A.LoadID = {{LoadID}}
        ;
