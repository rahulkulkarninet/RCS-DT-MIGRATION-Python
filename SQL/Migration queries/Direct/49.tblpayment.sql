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
                -- Commission is stored ex-tax in Debtrak. RC_PAYMENTS.Comm_Amt is GST-inclusive before ~Apr-2024 and
                -- GST-exclusive after, so take the ex-GST figure from the linked COMT (commission charge) transaction
                -- when one exists (Cl_Amount is always GST-inclusive there); fall back to Comm_Amt (dishonours have no COMT).
                COALESCE(CT.Cl_Amount - CT.Cl_GST_Amt, P.Comm_Amt) ,
                NULL ,
                CT.Cl_GST_Amt ,                                   -- GST on the commission
                CASE WHEN ISNULL(CT.Cl_GST_Amt, 0) <> 0 THEN 10 END ,   -- AU GST rate, percent (matches native rows)

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
                OUTER APPLY ( SELECT TOP 1
                                        T.Cl_Amount ,
                                        T.Cl_GST_Amt
                              FROM      RC_TRANSACTION T
                              WHERE     T.Type = 'COMT'
                                        AND T.Pay_Tran_No = P.Transaction_No
                              ORDER BY  T.ZID
                            ) CT   -- commission charge transaction for this payment
                LEFT JOIN CSRC_OperatorContactMapping OM ON  P.Payment_Operator = OM.OperatorCode
        WHERE   A.LoadID = {{LoadID}}
                AND BT.StatusID = 1
                AND BT.LoadID = {{LoadID}}
        ;