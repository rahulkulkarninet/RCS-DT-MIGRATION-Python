INSERT  INTO tblPrincipal WITH ( ROWLOCK )
        ( AccountID ,
          TransactionDate ,
          TransactionAmount ,
          TransactionDesc ,
          ClientTransactionReference ,
		  LUPAllocatedAmount,
          LUPBalance ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID,
		  Z_REF
        )
        SELECT  A.AccountID ,
                PR.Invoice_Date ,
                PR.Invoice_Amount ,
                PR.Description ,
                PR.Account_No ,
	            ISNULL(PR.Total_Paid_Amount, 0) ,
                ISNULL(PR.Outstanding, 0) ,
                1 ,
                {{CurrentSessionID}} ,
                PR.Entry_Date , --CreateTS,
                1 ,
                {{LoadID}},
                REPLACE(REPLACE(REPLACE(PR.Invoice_Number, CHAR(13), ''), CHAR(10), ''), ' ', '')

        FROM    [RC_DRDBINVOICE] PR
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = PR.Full_Debt_Code
        WHERE   A.LoadID = {{LoadID}}
;
