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
          Z_REF,
          Z_REF2,
          Reference,
          Description
        )
        SELECT DISTINCT
                -- Same fallback as 48.tblbanktransaction: reversed payments carry the amount only in Payment_Amount_1.
                X.Amount ,
                -- Reversal legs carry the original payment's dates in the extract; the day the bank
                -- bounced it (Date_Dishonoured) is the real reversal date, as a native reversal would use.
                IIF(X.IsReversalLeg = 1, ISNULL(P.Date_Dishonoured, P.Date_Time_Entered), P.Date_Time_Entered) ,
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

                NULL,
                {{CurrentSessionID}} ,
                IIF(X.IsReversalLeg = 1, ISNULL(P.Date_Dishonoured, P.Date_Time_Entered), P.Date_Time_Entered) , -- GETDATE() ,
                1 ,
                {{LoadID}} ,
                IIF(P.Rev_Code IS NULL, 0, 1),
				P.AllocatedPrincipal,
				P.AllocatedOverpayment,
				P.AllocatedCost,
                P.ZID, -- Payment Key
                REPLACE(REPLACE(REPLACE(P.Z_REF, CHAR(13), ''), CHAR(10), ''), ' ', ''), -- Invoice No
                RS.Run_Name , -- Z_REF2
                -- Reference / Description are the payment-level fields the Edit Payment dialog shows
                -- ("Reference number" / "Description"). Surface the RCS WorkDesk numbers there:
                -- Transaction_No = "Transaction No", ZID = "Payment Ref. No".
                NULLIF(LTRIM(RTRIM(P.Transaction_No)), ''),
                CONCAT_WS(' | ',
                          NULLIF(LTRIM(RTRIM(P.Payment_Description)), ''),
                          'RCS Transaction No: ' + NULLIF(LTRIM(RTRIM(P.Transaction_No)), ''),
                          'RCS Payment Ref No: ' + CONVERT(nvarchar(20), P.ZID))

        FROM    RC_PAYMENTS P
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON CONVERT(nvarchar(100), P.Debt_Code) = A.AccountNumberPrevious
                INNER JOIN tblBankTransaction BT WITH ( NOLOCK ) ON bt.Z_REF = P.Transaction_No
                CROSS APPLY ( SELECT  COALESCE(NULLIF(P.Payment_Amount, 0), P.Payment_Amount_1) AS Amount ) X0
                CROSS APPLY ( SELECT  X0.Amount ,
                                      -- The negative row of a reversed/dishonoured pair (both rows carry Rev_Code).
                                      IIF(P.Rev_Code IS NOT NULL AND X0.Amount < 0, 1, 0) AS IsReversalLeg ) X
                OUTER APPLY ( SELECT TOP 1
                                        T.Cl_Amount ,
                                        T.Cl_GST_Amt
                              FROM      RC_TRANSACTION T
                              WHERE     T.Type = 'COMT'
                                        AND T.Pay_Tran_No = P.Transaction_No
                              ORDER BY  T.ZID
                            ) CT   -- commission charge transaction for this payment
                OUTER APPLY ( SELECT TOP 1
                                        NULLIF(LTRIM(RTRIM(S.Run_Name)), '') AS Run_Name
                              FROM      RC_STATEMENT S
                              WHERE     CONVERT(nvarchar(50), S.Tran_Key) = LTRIM(RTRIM(P.Transaction_No))
                              ORDER BY  S.Tran_Key
                            ) RS
        WHERE   A.LoadID = {{LoadID}}
                AND BT.StatusID = 1
                AND BT.LoadID = {{LoadID}}
        ;

-- Link each reversal to the payment it reverses, the way spPaymentReverse does natively.
-- RCS exports a reversed/dishonoured payment as two rows sharing one ZID: the original (+) and
-- the reversal (-). Both legs point at each other through Reversed_PaymentID, the reversal leg
-- carries the ReversalTypeID, and the reversal's bank transaction points at the original's.
DECLARE @ReversalPairs TABLE
        ( Orig_PaymentID INT PRIMARY KEY ,
          Rev_PaymentID INT NOT NULL ,
          Orig_BankTransactionID INT NULL ,
          Rev_BankTransactionID INT NULL ,
          Rev_Reference NVARCHAR(200) NULL
        );

INSERT  INTO @ReversalPairs
        ( Orig_PaymentID ,
          Rev_PaymentID ,
          Orig_BankTransactionID ,
          Rev_BankTransactionID ,
          Rev_Reference
        )
        SELECT  O.PaymentID ,
                R.PaymentID ,
                O.BankTransactionID ,
                R.BankTransactionID ,
                R.Reference
        FROM    ( SELECT    AccountID ,
                            Z_ID
                  FROM      tblPayment WITH ( NOLOCK )
                  WHERE     LoadID = {{LoadID}}
                            AND Reversed = 1
                            AND StatusID = 1
                  GROUP BY  AccountID ,
                            Z_ID
                  HAVING    COUNT(*) = 2
                            AND SUM(IIF(Payment > 0, 1, 0)) = 1
                            AND SUM(IIF(Payment < 0, 1, 0)) = 1
                ) G
                INNER JOIN tblPayment O WITH ( NOLOCK ) ON O.AccountID = G.AccountID
                                                         AND O.Z_ID = G.Z_ID
                                                         AND O.LoadID = {{LoadID}}
                                                         AND O.Reversed = 1
                                                         AND O.StatusID = 1
                                                         AND O.Payment > 0
                INNER JOIN tblPayment R WITH ( NOLOCK ) ON R.AccountID = G.AccountID
                                                         AND R.Z_ID = G.Z_ID
                                                         AND R.LoadID = {{LoadID}}
                                                         AND R.Reversed = 1
                                                         AND R.StatusID = 1
                                                         AND R.Payment < 0
        ;

UPDATE  R
SET     R.Reversed_PaymentID = RP.Orig_PaymentID ,
        -- RCS Payment_Status 'D' is a bank dishonour; anything else ('R', or 'C' with a Rev_Code) is a plain reversal.
        R.ReversalTypeID = IIF(EXISTS ( SELECT  1
                                        FROM    RC_PAYMENTS P
                                        WHERE   LTRIM(RTRIM(P.Transaction_No)) = RP.Rev_Reference
                                                AND P.Payment_Status = 'D' ),
                               H.Dishonour_ReversalTypeID, H.Default_ReversalTypeID)
FROM    tblPayment R WITH ( ROWLOCK )
        INNER JOIN @ReversalPairs RP ON RP.Rev_PaymentID = R.PaymentID
        CROSS JOIN ( SELECT TOP 1
                            Default_ReversalTypeID ,
                            Dishonour_ReversalTypeID
                     FROM   vwHost
                   ) H
;

UPDATE  O
SET     O.Reversed_PaymentID = RP.Rev_PaymentID
FROM    tblPayment O WITH ( ROWLOCK )
        INNER JOIN @ReversalPairs RP ON RP.Orig_PaymentID = O.PaymentID
;

UPDATE  RBT
SET     RBT.Reversed_BankTransactionID = RP.Orig_BankTransactionID
FROM    tblBankTransaction RBT WITH ( ROWLOCK )
        INNER JOIN @ReversalPairs RP ON RP.Rev_BankTransactionID = RBT.BankTransactionID
WHERE   RBT.LoadID = {{LoadID}}
        AND RP.Orig_BankTransactionID <> RP.Rev_BankTransactionID
;
