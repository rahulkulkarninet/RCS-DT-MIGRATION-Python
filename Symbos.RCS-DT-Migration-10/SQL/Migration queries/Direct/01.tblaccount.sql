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
                ISNULL(RC.MA_Status_AccountStatusID, {{AccountStatusID_Creation}}) , -- set by status_service.py
                P.ProductID ,
                LEFT(RC.Debtor_Code, 250) ,
                NULL ,
                rc.Debt_Ref_No ,
                RC.Short_Debt_Code ,
                RC.Full_Debt_Code ,
                ISNULL(RC.Operator_ContactID, {{DefaultOperatorContactID}}) , -- set by operator_contact_service.py
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