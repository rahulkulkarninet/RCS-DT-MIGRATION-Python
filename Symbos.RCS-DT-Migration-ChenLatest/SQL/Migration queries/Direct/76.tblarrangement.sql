INSERT  INTO tblArrangement WITH ( ROWLOCK )
        ( AccountID ,
          ArrangementAmount ,
          CreateID ,
          CreateSessionID ,
          ArrangementTypeID ,--ArrangmentType, to run via mapping table
          NumberOfInstallmentPayments ,
          CommenceDate ,
          ArrangementEndDate ,
          BankTransactionMethodID ,--BankTransactionMethodID, to run via mapping table
          LUPTotalPayments ,
          LUPArrangementBalance ,
          AccountBalanceAtArrangement ,
          CreateTS ,
          StatusID ,
          ArrangementStatusID ,
          FrequencyID ,
          LoadID,
          ArrangementDate ,
          InstallmentAmount
        )
        SELECT  A.AccountID ,
                DL.Deal_Amount ,
                ISNULL(OPC.ContactID, {{DefaultOperatorContactID}}) , -- CreateID
                {{CurrentSessionID}} ,
                ISNULL({{ArrangementTypeID_Deal}}, 1) ,
                DL.No_Instalments ,
                DL.First_Instalment ,
                DL.Last_Instal_Date ,
                ISNULL(DL.Payment_Method_BankTransactionMethodID, 1) ,--BankTransactionMethodID, set by bank_transaction_method_service.py
                DL.Total_Paid ,
                DL.Total_Outstanding ,
                DL.Bal_At_Tme_Of_Offer ,
                DL.Date_of_Deal , --GETDATE(),
                1 ,
                CASE
                    WHEN (DL.Deal_Amount - ISNULL(DL.Total_Paid,0) <= 0) THEN 2 --Successful
                    WHEN UPPER(LTRIM(RTRIM(DL.Status))) IN ( 'PTPB', 'SFLB', 'INSTALB' ) THEN 4 -- Failed
                    WHEN DATEDIFF(DAY, DL.Due_Date, GETDATE()) > 0 THEN 4 -- Failed
                    ELSE 1 -- In Progress
                END ,
                NULL ,  --Deal is an Ad-hoc arrangement, no frequency4
                {{LoadID}},
                DL.Date_of_Deal ,
                INST.FirstInstalment -- InstallmentAmount
        FROM    [RC_DEAL] DL
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CONVERT(nvarchar(100), DL.Extended_Debt_Code)
                OUTER APPLY ( SELECT TOP 1
                                        C.ContactID
                              FROM      tblContact C WITH ( NOLOCK )
                              WHERE     C.IsUser = 1
                                        AND C.Z_REF = LTRIM(RTRIM(DL.Op_Code))
                              ORDER BY  CASE WHEN ISNULL(C.StatusID, 0) = 1 THEN 0 ELSE 1 END ,
                                        C.ContactID
                            ) OPC
                CROSS APPLY ( SELECT TRY_CONVERT(decimal(18, 2),
                                        REPLACE(LEFT(DL.Instalment_Amt, CHARINDEX('|', DL.Instalment_Amt + '|') - 1), '''', '')) AS FirstInstalment
                            ) INST
        WHERE   A.LoadID = {{LoadID}}
        ;