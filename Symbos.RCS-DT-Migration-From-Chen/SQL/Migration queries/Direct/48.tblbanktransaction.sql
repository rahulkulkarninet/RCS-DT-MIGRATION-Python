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
                ISNULL(COALESCE(NULLIF(P.Payment_Amount, 0), P.Payment_Amount_1), 0) ,
                -- Description: RCS Payment_Description is empty in the extracts, so surface the two
                -- RCS reference numbers the tester expects to see (WorkDesk "Transaction No" and
                -- "Payment Ref. No"). They are otherwise only stored in Z_REF / tblPayment.Z_ID,
                -- which no Debtrak screen displays.
                CONCAT_WS(' | ',
                          NULLIF(LTRIM(RTRIM(P.Payment_Description)), ''),
                          'RCS Transaction No: ' + NULLIF(LTRIM(RTRIM(P.Transaction_No)), ''),
                          'RCS Payment Ref No: ' + CONVERT(nvarchar(20), P.ZID)) ,
                P.Full_Reference_Details ,
                P.Effective_Date ,
                P.Payment_Method_BankTransactionMethodID, --BankTransactionMethodID, set by bank_transaction_method_service.py
                -- Banked-to account left blank (Rahul, 2026-10-09): the extract carries no banked-to
                -- account and the host default (vwHost.BankAccountID_DefaultHost) has been removed;
                -- the migration must not invent one.
                NULL ,
                1 , -- AUD, to run via mapping table
                P.Cheque_No ,
                P.BSB_Code ,
                P.Date_Cleared ,
                1.0 ,
                1 ,
                {{CurrentSessionID}} ,
                P.Date_Time_Entered , --GETDATE() ,
                1 ,
                {{LoadID}} ,
                P.Transaction_No
        FROM    RC_PAYMENTS P
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON CONVERT(nvarchar(100), P.Debt_Code) = A.AccountNumberPrevious
        WHERE   A.LoadID = {{LoadID}}
        ;