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
                CROSS APPLY ( SELECT TOP 1
                                        AccountStatusID
                              FROM      tblAccountStatus
                              WHERE     AccountStatus = RC.MA_Status
                            ) AsMap
                -- OUTER APPLY TOP 1, not a LEFT JOIN: tblProduct.Product is not
                -- unique. It holds 73 rows over 68 distinct values - 'Credit Card'
                -- twice and blank five times - so a join on it multiplies accounts.
                -- Every account in load 168 had WorkType 'Credit Card', which
                -- duplicated all 14,741 of them into 29,480, and every downstream
                -- file joining tblAccount inherited the fan-out: tblEntry took
                -- 16,439,156 rows from 8,221,310 notes.
                -- This mirrors the CROSS APPLY used just above for AccountStatus;
                -- OUTER rather than CROSS to keep the LEFT JOIN's optional semantics,
                -- and ORDER BY so the row chosen is deterministic between runs.
                OUTER APPLY ( SELECT TOP 1
                                        ProductID
                              FROM      tblProduct
                              WHERE     Product = RC.WorkType
                              ORDER BY  ProductID
                            ) P
                LEFT JOIN tblClosureReason CRMap ON RC.Reason_Closed = CRMap.ClosureReason
                LEFT JOIN CSRC_OperatorContactMapping OM ON  RC.Operator = OM.OperatorCode 
        ORDER BY 
                RC.Last_Pay DESC
;