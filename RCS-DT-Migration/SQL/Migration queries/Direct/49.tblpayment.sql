INSERT  INTO tblPayment WITH ( ROWLOCK )
        ( Payment ,
          PaymentDate ,
          AccountID ,
          PaymentToID ,
          PaymentTypeID ,
          BankTransactionID ,
          Commission ,
          CommissionRate ,
          CommissionTax ,
          CommissionTaxRate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID ,
          Reversed,
		  LUPAllocatedPrincipal,
		  LUPAllocatedOverpayment,
		  LUPAllocatedCost,
		  Z_ID,
          Z_REF
        )
        SELECT DISTINCT
                P.Payment_Amount ,
                ( P.Date_Time_Entered ) ,
                A.AccountID ,
                IIF(P.Payment_Code = 'PAYD', 2, 1) ,    --Direct or Trust
                1 , --PaymentTypeID, to run via mapping table, if options are presented
                BT.BankTransactionID ,
                P.Comm_Amt ,
                NULL ,
                NULL ,
                NULL ,
                ISNULL(OM.ContactIDDestination, 1) ,
                {{CurrentSessionID}} ,
                P.Date_Time_Entered , -- GETDATE() ,
                1 ,
                {{LoadID}} ,
                IIF(P.Rev_Code IS NULL, 0, 1),
				P.AllocatedPrincipal,
				P.AllocatedOverpayment,
				P.AllocatedCost,
                P.ZID, -- Payment Key
                REPLACE(REPLACE(REPLACE(P.Z_REF, CHAR(13), ''), CHAR(10), ''), ' ', '') -- Invoice No

        FROM    RC_PAYMENTS P
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON P.Debt_Code = A.AccountNumberPrevious
                INNER JOIN tblBankTransaction BT WITH ( NOLOCK ) ON bt.Z_REF = P.Transaction_No
                LEFT JOIN CSRC_OperatorContactMapping OM ON  P.Payment_Operator = OM.OperatorCode
        WHERE   A.LoadID = {{LoadID}}
                AND BT.StatusID = 1
                AND BT.LoadID = {{LoadID}}
        ;