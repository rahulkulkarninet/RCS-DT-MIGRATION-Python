INSERT  INTO tblAccount WITH ( ROWLOCK )
        ( LoadID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          EntityID ,
          StatusID ,
          AccountStatusID ,
          ProductID ,
          AccountTypeID ,
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
                ISNULL(RC.MA_Status_AccountStatusID, {{AccountStatusID_Creation}}) , -- set by status_service.py
                P.ProductID ,
                ATY.AccountTypeID ,
                LEFT(RC.Debtor_Code, 250) ,
                NULL ,
                LEFT(CR.ClientRef, 100) ,   -- AccountNumberClient
                LEFT(REFS.OtherRefs, 100) , -- AccountNumberOther
                RC.Full_Debt_Code ,
                ISNULL(RC.Operator_ContactID, {{DefaultOperatorContactID}}) , -- set by operator_contact_service.py
                RC.Orig_Debt ,
                RC.Debit_Amts ,
                RC.Paid_Amts ,
                -- Debtrak keeps LoadDate / LUPLastPaymentDate in UTC and renders them in local
                -- time; DateOfDebt is a date only. RCS supplies Sydney local times, so an entry
                -- after ~1 pm displayed a day late until this conversion (Louisa, 2026-10-13).
                CAST(RC.Date_Time_Entered AS date) ,                                                              -- DateOfDebt
                RC.Diary_Date ,
                CONVERT(datetime, RC.Date_Time_Entered AT TIME ZONE 'AUS Eastern Standard Time' AT TIME ZONE 'UTC') , -- LoadDate
                RC.Closed ,
                RC.Accept_Date ,
                RC.Next_Act ,
                RC.Last_Pay_Amt ,
                CONVERT(datetime, RC.Last_Pay_Date AT TIME ZONE 'AUS Eastern Standard Time' AT TIME ZONE 'UTC') ,     -- LUPLastPaymentDate
                RC.Reason_Closed_ClosureReasonID , -- set by closure_reason_service.py
                LEFT(RC.Score_Colour_DB, 30) ,
                RC.Date_of_Debt ,
                NULL ,
                RC.SystemID,
                RC.Account_No
        FROM    [RC_ACCOUNT_EXTRACT] RC

                OUTER APPLY ( SELECT TOP 1
                                        ProductID
                              FROM      tblProduct
                              WHERE     Product = RC.WorkType
                              ORDER BY  ProductID
                            ) P

                OUTER APPLY ( SELECT TOP 1
                                        AccountTypeID
                              FROM      tblAccountType
                              WHERE     AccountType = RC.Worktype
                                        AND StatusID = 1
                              ORDER BY  AccountTypeID
                            ) ATY

                CROSS APPLY ( SELECT NULLIF(LTRIM(RTRIM(RC.Account_No)), '') AS ClientRef
                            ) CR

                CROSS APPLY ( SELECT STRING_AGG(X.Ref, ' | ') WITHIN GROUP ( ORDER BY X.Ord ) AS OtherRefs
                              FROM   ( SELECT MIN(V.Ord) AS Ord ,
                                              V.Ref
                                       FROM   ( VALUES ( 1, NULLIF(LTRIM(RTRIM(RC.Debt_Ref_No)), '') ),
                                                       ( 2, NULLIF(LTRIM(RTRIM(RC.Debt_Ref_No2)), '') ),
                                                       ( 3, NULLIF(LTRIM(RTRIM(RC.Debt_Ref_No3)), '') ),
                                                       ( 4, NULLIF(LTRIM(RTRIM(RC.Debt_Ref_No_4)), '') ),
                                                       ( 5, CONVERT(nvarchar(100), RC.Short_Debt_Code) )
                                              ) V ( Ord, Ref )
                                       WHERE  V.Ref IS NOT NULL
                                              AND V.Ref <> ISNULL(CR.ClientRef, '')
                                       GROUP BY V.Ref
                                     ) X
                            ) REFS

                CROSS APPLY ( SELECT TRY_CONVERT(DATETIME,
                                        NULLIF(LTRIM(RTRIM(RC.Closed)), '')) AS DateClosed
                            ) CD

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


BEGIN TRY
    DECLARE @refreshLoadIdStats nvarchar(max) = N'';
    SELECT  @refreshLoadIdStats += N'UPDATE STATISTICS dbo.tblAccount ' + QUOTENAME(s.name) + N'; '
    FROM    sys.stats s
            JOIN sys.stats_columns sc ON sc.object_id = s.object_id
                                         AND sc.stats_id = s.stats_id
                                         AND sc.stats_column_id = 1
            JOIN sys.columns c ON c.object_id = sc.object_id AND c.column_id = sc.column_id
    WHERE   s.object_id = OBJECT_ID(N'dbo.tblAccount')
            AND c.name = N'LoadID';
    IF @refreshLoadIdStats <> N''
        EXEC sys.sp_executesql @refreshLoadIdStats;
END TRY
BEGIN CATCH
    PRINT 'LoadID statistics on tblAccount not refreshed: ' + ERROR_MESSAGE();
END CATCH;