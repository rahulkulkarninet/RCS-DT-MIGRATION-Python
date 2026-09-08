INSERT  INTO tblAccount WITH ( ROWLOCK )
        ( LoadID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          EntityID ,
          StatusID ,
          AccountStatusID ,
          ProductID ,
          AccountName ,
          AccountNumber ,
          AccountNumberClient ,
          AccountNumberOther ,
          AccountNumberPrevious ,
          AccountManager_ContactID ,
          LUPFirstPrincipal ,
          LUPTotalPrincipal ,
          LUPTotalPayment ,
          DateOfDebt ,
          LUPLastUserActionDate ,
          LoadDate ,
          CloseDate ,
          EntitySupplyDate,
          NextActionDate ,
          LUPLastPaymentAmount ,
          LUPLastPaymentDate ,
          ClosureReason ,
          LUPScore ,
          RecoveryStartDate ,
          LUPLastPhoneContactDate ,
          Z_DB,
          Z_REF
        )
        SELECT 
                {{LoadID}} ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                {{EntityID}} ,
                1 ,
                ISNULL(ASMap.AccountStatusID, {{AccountStatusID_Creation}}) ,
                P.ProductID ,
                LEFT(RC.Debtor_Code, 250) ,
                NULL ,
                rc.Debt_Ref_No ,
                RC.Short_Debt_Code ,
                RC.Full_Debt_Code ,
                ISNULL(OM.ContactIDDestination, 1) ,
                RC.Orig_Debt ,
                RC.Debit_Amts ,
                RC.Paid_Amts ,
                RC.Date_Time_Entered ,
                RC.Diary_Date ,
                RC.Date_Time_Entered ,
                RC.Closed ,
                RC.Accept_Date ,
                RC.Next_Act ,
                RC.Last_Pay_Amt ,
                RC.Last_Pay_Date ,
                CRMap.ClosureReasonID ,
                LEFT(RC.Score_Colour_DB, 30) ,
                RC.Date_of_Debt ,
                NULL ,
                RC.SystemID,
                RC.Account_No
        FROM    [RC_ACCOUNT_EXTRACT] RC

                OUTER APPLY ( SELECT TOP 1
                                        AccountStatusID
                              FROM      tblAccountStatus
                              WHERE     AccountStatus = RC.MA_Status
                            ) AsMap

                OUTER APPLY ( SELECT TOP 1
                                        ProductID
                              FROM      tblProduct
                              WHERE     Product = RC.WorkType
                              ORDER BY  ProductID
                            ) P

                CROSS APPLY ( SELECT TRY_CONVERT(DATETIME,
                                        NULLIF(LTRIM(RTRIM(RC.Closed)), '')) AS DateClosed
                            ) CD
                LEFT JOIN tblClosureReason CRMap ON RC.Reason_Closed = CRMap.ClosureReason
                LEFT JOIN CSRC_OperatorContactMapping OM ON  RC.Operator = OM.OperatorCode


        WHERE   CD.DateClosed IS NULL
                OR CD.DateClosed > DATEADD(MONTH, -{{ClosedAccountRetentionMonths}}, GETDATE())
                OR RC.Last_Pay_Date > DATEADD(MONTH, -{{RecentPaymentMonths}}, GETDATE())
                OR EXISTS ( SELECT  1
                            FROM    RC_PAYMENTS PMT
                            WHERE   PMT.Debt_Code = RC.Full_Debt_Code
                                    AND PMT.Date_Time_Entered > DATEADD(MONTH, -{{RecentPaymentMonths}}, GETDATE()) )
        ORDER BY
                RC.Last_Pay DESC
;