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
                ISNULL(P.Payment_Amount, 0) ,
                P.Payment_Description ,
                P.Full_Reference_Details ,
                P.Effective_Date ,
                BTM.BankTransactionMethodID, --BankTransactionMethodID, to run via mapping table
                {{BankAccountID_DefaultHost}} ,
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
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON P.Debt_Code = A.AccountNumberPrevious
                LEFT JOIN tblBankTransactionMethod BTM ON P.Payment_Method = BTM.BankTransactionMethod
        WHERE   A.LoadID = {{LoadID}}
        ;