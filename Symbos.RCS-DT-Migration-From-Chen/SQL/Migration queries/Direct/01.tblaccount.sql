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
                ISNULL(OM.ContactID, {{DefaultOperatorContactID}}) ,
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

                OUTER APPLY ( SELECT TOP 1
                                        C.ContactID
                              FROM      tblContact C WITH ( NOLOCK )
                              WHERE     C.UserName = LTRIM(RTRIM(REPLACE(RC.Operator, NCHAR(160), ' ')))
                              ORDER BY  CASE WHEN ISNULL(C.StatusID, 0) = 1 THEN 0 ELSE 1 END ,
                                        C.ContactID
                            ) OM


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

-- Every later file filters on tblAccount.LoadID = this load, a value the
-- statistics have never seen until they are refreshed. With async auto-update
-- (on in test-debtrak) the next files compile against the old histogram: on
-- 2026-10-02 011 MIMO estimated 209 accounts for 10,719 and took 27s instead of
-- 0.1s. Refreshing the LoadID-led statistics here, synchronously, means every
-- later plan sees the real count. Only those statistics, so a large production
-- tblAccount is not rescanned; names looked up, not hard-coded, because they
-- differ between environments. Failure only costs plan quality, never the load.
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