
SET NOCOUNT ON;

DECLARE @InsertedArangments TABLE
    (
      ID INT IDENTITY(1, 1) ,
      ArrangementID INT ,
      ACCOUNTID INT
    )

INSERT  INTO @InsertedArangments
        ( ArrangementID ,
          ACCOUNTID
        )
        SELECT  ArrangementID ,
                ACCOUNTID
        FROM    tblArrangement WITH ( NOLOCK )
        WHERE   LoadID = {{LoadID}}
                AND StatusID = 1

DECLARE @arrangementloopIndex INT = 1
DECLARE @arrangementmaxIndex INT;
DECLARE @currArrangementID INT;

SELECT  @arrangementmaxIndex = MAX(ID)
FROM    @InsertedArangments

DECLARE @InstalmentDate NVARCHAR(MAX)
DECLARE @InstalmentAmt NVARCHAR(MAX)
DECLARE @SMSReminder NVARCHAR(1)
DECLARE @EmailReminder NVARCHAR(MAX)
DECLARE @SMS NVARCHAR(500)
DECLARE @Email NVARCHAR(500)

	PRINT SYSDATETIME()
PRINT 'Creating ArrangementSchedule from Inserted Deals'

DECLARE @currAccountID INT;

WHILE ( @arrangementloopIndex <= @arrangementmaxIndex )
    BEGIN
        SELECT  @currAccountID = AccountID ,
                @currArrangementID = ArrangementID
        FROM    @InsertedArangments
        WHERE   ID = @arrangementloopIndex

        SELECT  @InstalmentDate = Instalment_Date ,
                @InstalmentAmt = Instalment_Amt ,
                @SMSReminder = DL.SMS_Reminder ,
                @SMS = DL.SMS_Mobile ,
                @EmailReminder = DL.Email_Reminder_Flag ,
                @Email = DL.Email_Address
        FROM    [RC_DEAL] DL
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CONVERT(nvarchar(100), DL.Extended_Debt_Code)
        WHERE   A.AccountID = @currAccountID


        IF ( @InstalmentDate IS NOT NULL
             AND @InstalmentAmt IS NOT NULL
           )
            BEGIN
                -- StatusID/IsPaid/payment columns mirror spGen_ArrangementScheduleSave.
                -- spArrangementScheduleSelectByArrangementID (used by the arrangement
                -- screen) filters StatusID = 1, so rows without it never display.
                INSERT  INTO tblArrangementSchedule
                        ( ArrangementID ,
                          InstallmentAmount ,
                          InstallmentDue ,
                          ArrangementTotalDueToDate ,
                          CreateID ,
                          CreateSessionID ,
                          CreateTS ,
                          StatusID ,
                          IsPaid ,
                          BankTransactionMethodID ,
                          BankAccountID ,
                          PaymentTokenID
                        )
                        SELECT  @currArrangementID ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                CONVERT(DATE, REPLACE(installmentDate.Line,'''',''), 120) ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                1 ,
                                {{CurrentSessionID}} ,
                                GETDATE() ,
                                1 ,
                                0 ,
                                ARR.BankTransactionMethodID ,
                                ARR.BankAccountID ,
                                ARR.PaymentTokenID
                        FROM    dbo.fnSplitTextIntoTable(@InstalmentAmt, '|') installmentAmt
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InstalmentDate, '|') installmentDate ON installmentAmt.[LineNo] = installmentDate.[LineNo]
                                CROSS JOIN tblArrangement ARR WITH ( NOLOCK )
                        WHERE   ARR.ArrangementID = @currArrangementID
            END
        IF ( @EmailReminder = 'Y' )
            BEGIN
                EXEC spArrangement_ReminderMethodSave @User_ContactID = 1, @User_SessionID = 1,
                    @ArrangementID = @currArrangementID, @ReminderMethodID = 2, @ContactDetailID = NULL,
                    @AddressID = NULL, @Value = @Email, @StatusID = 1, @ReminderDaysBeforeDue = NULL

            END
        IF ( @SMSReminder = 'Y' )
            BEGIN
                EXEC spArrangement_ReminderMethodSave @User_ContactID = 1, @User_SessionID = 1,
                    @ArrangementID = @currArrangementID, @ReminderMethodID = 1, @ContactDetailID = NULL,
                    @AddressID = NULL, @Value = @SMS, @StatusID = 1, @ReminderDaysBeforeDue = NULL
            END

        SET @arrangementloopIndex = @arrangementloopIndex + 1
    END





	PRINT SYSDATETIME()
PRINT 'Creating Arrangement from Arrangements'

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
          ArrangementDate
        )
        SELECT  A.AccountID ,		
                AR.Agreed_Amount ,
                1 ,
                {{CurrentSessionID}} ,
                AT.ArrangementTypeID ,--ArrangmentType, to run via mapping table
                AR.No_Instalments ,
                AR.First_Instal_Date ,
                AR.Last_Instal_Date ,
                BTM.BankTransactionMethodID ,--BankTransactionMethodID, to run via mapping table
                AR.Total_Paid ,
                AR.Total_Outstanding ,
                AR.Bal_At_Time_Of_Offer ,
                AR.Arrangement_Date , --GETDATE(),
                1 ,
                CASE 
                    WHEN (AR.Agreed_Amount - ISNULL(AR.Total_Paid,0) <= 0) THEN 2 --Successful
                    WHEN ((AR.Agreed_Amount - ISNULL(AR.Total_Paid,0) > 0) AND DATEDIFF(DAY, AR.Last_Instal_Date, GETDATE()) < 0) THEN 4 -- Failed
                    ELSE 1 -- In Progress                    
                END ,  
                F.FrequencyID , --FrequencyID, resolved via variables/frequency_codes.json
                {{LoadID}},
                Arrangement_Date

        FROM    [RC_ARRANGEMENT] AR
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CONVERT(nvarchar(100), AR.Extended_Debt_Code)
                LEFT JOIN tblArrangementType AT ON AR.Arrangement_Type = AT.ArrangementType
                LEFT JOIN tblBankTransactionMethod BTM ON AR.Payment_Method = BTM.BankTransactionMethod
                LEFT JOIN tblFrequency F ON AR.Frequency = F.Frequency
        WHERE   A.LoadID = {{LoadID}}


	PRINT SYSDATETIME()
PRINT 'Creating ArrangementSchedule from Inserted Arrangements'


DECLARE @ArInsertedArangments TABLE
    (
      ID INT IDENTITY(1, 1) ,
      ArrangementID INT ,
      ACCOUNTID INT
    )


INSERT  INTO @ArInsertedArangments
        ( ArrangementID ,
          ACCOUNTID
        )
        SELECT  ArrangementID ,
                ACCOUNTID
        FROM    tblArrangement WITH ( NOLOCK )
        WHERE   LoadID = {{LoadID}}
                AND StatusID = 1

DECLARE @arLoopIndex INT = 1
DECLARE @arMaxIndex INT;
DECLARE @currArID INT;

SELECT  @arMaxIndex = MAX(ID)
FROM    @arInsertedArangments

DECLARE @arInstalmentDate NVARCHAR(MAX)
DECLARE @arInstalmentAmt NVARCHAR(MAX)
DECLARE @arSMSReminder NVARCHAR(1)
DECLARE @arEmailReminder NVARCHAR(MAX)
DECLARE @arSMS NVARCHAR(1)
DECLARE @arEmail NVARCHAR(500)

DECLARE @currAccID INT;

PRINT 'Updating ArrangementSchedule table...'


WHILE ( @arLoopIndex <= @arMaxIndex )
    BEGIN
        SELECT  @currAccID = AccountID ,
                @currArID = ArrangementID
        FROM    @ArInsertedArangments
        WHERE   ID = @arLoopIndex

        SELECT  @arInstalmentDate = AR.Instalment_Date ,
                @arInstalmentAmt = AR.Instalment_Amount ,
                @arSMSReminder = AR.SMS_Reminder_Flag ,
                @arSMS = AR.SMS_Mobile ,
                @arEmailReminder = AR.Email_Reminder_Flag ,
                @arEmail = AR.Email_Address
        FROM    [RC_ARRANGEMENT] AR
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = CONVERT(nvarchar(100), AR.Extended_Debt_Code)
        WHERE   A.AccountID = @currAccID


        IF ( @arInstalmentDate IS NOT NULL
             AND @arInstalmentAmt IS NOT NULL
           )
            BEGIN
                -- StatusID/IsPaid/payment columns mirror spGen_ArrangementScheduleSave.
                -- spArrangementScheduleSelectByArrangementID (used by the arrangement
                -- screen) filters StatusID = 1, so rows without it never display.
                INSERT  INTO tblArrangementSchedule
                        ( ArrangementID ,
                          InstallmentAmount ,
                          InstallmentDue ,
                          ArrangementTotalDueToDate ,
                          CreateID ,
                          CreateSessionID ,
                          CreateTS ,
                          StatusID ,
                          IsPaid ,
                          BankTransactionMethodID ,
                          BankAccountID ,
                          PaymentTokenID
                        )
                        SELECT  @currArID ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                CONVERT(DATE, REPLACE(installmentDate.Line,'''',''), 120) ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                1 ,
                                {{CurrentSessionID}} ,
                                GETDATE() ,
                                1 ,
                                0 ,
                                ARR.BankTransactionMethodID ,
                                ARR.BankAccountID ,
                                ARR.PaymentTokenID
                        FROM    dbo.fnSplitTextIntoTable(@arInstalmentAmt, '|') installmentAmt
                                LEFT JOIN dbo.fnSplitTextIntoTable(@arInstalmentDate, '|') installmentDate ON installmentAmt.[LineNo] = installmentDate.[LineNo]
                                CROSS JOIN tblArrangement ARR WITH ( NOLOCK )
                        WHERE   ARR.ArrangementID = @currArID
            END
        IF ( @arEmailReminder = 'Y' )
            BEGIN
                EXEC spArrangement_ReminderMethodSave @User_ContactID = 1, @User_SessionID = 1,
                    @ArrangementID = @currArID, @ReminderMethodID = 2, @ContactDetailID = NULL,
                    @AddressID = NULL, @Value = @arEmail, @StatusID = 1, @ReminderDaysBeforeDue = NULL

            END
        IF ( @arSMSReminder = 'Y' )
            BEGIN
                EXEC spArrangement_ReminderMethodSave @User_ContactID = 1, @User_SessionID = 1,
                    @ArrangementID = @currArID, @ReminderMethodID = 1, @ContactDetailID = NULL,
                    @AddressID = NULL, @Value = @arSMS, @StatusID = 1, @ReminderDaysBeforeDue = NULL
            END

        SET @arLoopIndex = @arLoopIndex + 1
    END


-- Insert Account Status History (tblWorkflowLineAudit)


DECLARE @InsertedAccounts TABLE
    (
      ID INT IDENTITY(1, 1) ,
      AccountID INT
    )


INSERT  INTO @InsertedAccounts
        ( AccountID
        )
        SELECT  AccountID
        FROM    tblAccount WITH ( NOLOCK )
        WHERE   LoadID = {{LoadID}}
                AND StatusID = 1
				ORDER BY AccountID

DECLARE @loopIndex INT = 1
DECLARE @maxIndex INT;

SET @loopIndex = 1
SELECT  @maxIndex = MAX(ID)
FROM    @InsertedAccounts


DECLARE @currWorkflowLineID INT

DECLARE @currAccountStatusHistoryString NVARCHAR(MAX)
DECLARE @currAccountStatusTimestameString NVARCHAR(MAX)
DEClARE @currOperatorString NVARCHAR(MAX)

WHILE ( @loopIndex <= @maxIndex )
    BEGIN
        SELECT  @currAccountID = AccountID                
        FROM    @InsertedAccounts
        WHERE   ID = @loopIndex

        SELECT TOP 1 @currWorkflowLineID = WorkflowLineID
        FROM tblWorkflowLine WITH (NOLOCK)
        WHERE AccountID = @currAccountID ORDER BY WorkflowLineiD DESC

        SELECT 
            @currAccountStatusHistoryString = Status_history, 
            @currAccountStatusTimestameString = Stat_Code_Hist_date_time, 
            @currOperatorString = Stat_Code_Hist_Op
        FROM RC_ACCOUNT_EXTRACT
        WHERE Full_Debt_Code = (SELECT TOP 1 AccountNumberPrevious FROM tblAccount WHERE AccountID = @currAccountID)

        
        INSERT INTO tblWorkflowLineAudit(AccountID, WorkflowLineID, AccountStatusID, AuditTS, CreateID, CreateSessionID, StatusID, LoadID)        
        SELECT 
            @currAccountID,
            @currWorkflowLineID,

            ISNULL(AsMap.AccountStatusID, {{AccountStatusID_Creation}}),
            X.TimeStamp,      -- Default conversion
            1,
            {{CurrentSessionID}},
            1,
            {{LoadID}}
        FROM dbo.fnGetAccountStatusHistoryFromPipeData(@currAccountStatusHistoryString, @currAccountStatusTimestameString, @currOperatorString) X

        OUTER APPLY ( SELECT TOP 1
                                        AccountStatusID
                              FROM      tblAccountStatus
                              WHERE     AccountStatus = X.AccountStatus
                            ) AsMap
        -- The CSRC_OperatorContactMapping join that stood here is gone. It was dead:
        -- nothing from it reached the INSERT, which hardcodes CreateID 1, so the join
        -- was computed and discarded. It also named a customer-specific table, which
        -- is why the other seven uses now read tblContact directly.
        -- Attributing this audit row to X.Operator is a real improvement, but it is a
        -- behaviour change and belongs with the sign-off on who the operator codes map
        -- to - see variables/operator_contact_codes.json.

        SET @currAccountID = NULL
        SET @currWorkflowLineID = NULL
        SET @currAccountStatusHistoryString = NULL
        SET @currAccountStatusTimestameString = NULL
        SET @currOperatorString = NULL


        SET @loopIndex = @loopIndex + 1

    END


PRINT SYSDATETIME()
PRINT 'Finished Account Status History.'
PRINT 'Creating other police reports'


DECLARE @OtherPoliceReports TABLE (
    ID INT IDENTITY(1,1),
    AccountIncidentID INT,
    PoliceReports NVARCHAR(100),
    PoliceStations NVARCHAR(100)
)

INSERT INTO @OtherPoliceReports
    (
        AccountIncidentID,
        PoliceReports,
        PoliceStations
    )
SELECT
    AI.AccountIncidentID,
    DR.Other_Police_Report,
    DR.Other_Police_Stations
FROM tblaccount A
    JOIN tblAccountIncident AI ON AI.AccountID = A.AccountID
    JOIN RC_DEBTOR DR ON CONVERT(nvarchar(100), DR.Debt_Code) = A.AccountNumberPrevious
WHERE A.LoadID = {{LoadID}}
  AND LEN(DR.Other_Police_Report) > 0

IF EXISTS (SELECT 1 FROM @OtherPoliceReports)
BEGIN

    DECLARE @PoliceReports VARCHAR(MAX)
    DECLARE @PoliceStations VARCHAR(MAX)
    DECLARE @AccountIncidentID INT
    DECLARE @OPR_LoopIndex INT = 1
    DECLARE @OPR_MaxIndex INT

    SELECT @OPR_MaxIndex = MAX(ID)
    FROM @OtherPoliceReports

    WHILE (@OPR_LoopIndex <= @OPR_MaxIndex)
    BEGIN
        SELECT
            @AccountIncidentID = AccountIncidentID,
            @PoliceReports = PoliceReports,
            @PoliceStations = PoliceStations
        FROM @OtherPoliceReports
        WHERE ID = @OPR_LoopIndex

        IF (@PoliceReports IS NOT NULL)
        BEGIN
            INSERT INTO tblIncidentPolice WITH (ROWLOCK)
                (
                    AccountIncidentID,
                    PoliceAttended,
                    FileNumber,
                    PoliceStation,
                    CreateID,
                    CreateSessionID,
                    CreateTS,
                    StatusID,
                    LoadID
                )
            SELECT
                @AccountIncidentID,
                0,
                REPLACE(policeReport.Line, '''', ''),
                REPLACE(policeStation.Line, '''', ''),
                1,
                {{CurrentSessionID}},
                GETDATE(),
                1,
                {{LoadID}}
            FROM dbo.fnSplitTextIntoTable(@PoliceReports, '|') policeReport
                LEFT JOIN dbo.fnSplitTextIntoTable(@PoliceStations, '|') policeStation ON policeReport.[LineNo] = policeStation.[LineNo]
        END

        SET @OPR_LoopIndex += 1
    END
END

PRINT SYSDATETIME()
PRINT 'Finished other police reports.'

DECLARE @TodayDate DATETIME = dbo.fnDateEndOfDay(GETDATE());
DECLARE @OneWeekAgoDate DATETIME = dbo.fnDate(DATEADD(DAY, -7, GETDATE()));
DECLARE @OneMonthAgoDate DATETIME = dbo.fnDate(DATEADD(DAY, -30, GETDATE()));

IF OBJECT_ID('tempdb..#LUPPairs') IS NOT NULL DROP TABLE #LUPPairs;
CREATE TABLE #LUPPairs
(
	AccountID INT NOT NULL,
	ContactID INT NOT NULL,
	PRIMARY KEY (AccountID, ContactID)
);

INSERT INTO #LUPPairs (AccountID, ContactID)
SELECT DISTINCT A.AccountID, C.ContactID
FROM tblContact C WITH (NOLOCK)
	INNER JOIN tblAccount_Contact AC WITH (NOLOCK) ON C.ContactID = AC.ContactID
	INNER JOIN tblAccount A WITH (NOLOCK) ON AC.AccountID = A.AccountID
WHERE A.LoadID = {{LoadID}}
	AND A.CloseDate IS NULL
	AND A.StatusID = 1 AND AC.StatusID = 1 AND C.StatusID = 1;

PRINT CAST(SYSDATETIME() AS VARCHAR(19)) + ' Recalculating correspondence counters for '
    + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' account contacts.';

;WITH AccountContacts AS
(
	SELECT AccountID, ContactID FROM #LUPPairs
)
,Letter7DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(DISTINCT ch.CorrespondenceHistoryID) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN tblLetter L ON L.LetterID = ch.CorrespondenceId
	INNER JOIN tblCommunication_Contact c ON c.CommunicationID = L.CommunicationID
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'Letter'
	AND ch.CorrespondenceTS BETWEEN @OneWeekAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	-- UPDATED: Exclude digital letters by BOTH PrintStatusID and CommunicationMethodID
	AND ISNULL(L.PrintStatusID,0) <> -2
	AND ISNULL(c.CommunicationMethodID,0) <> 5 -- Exclude Digital communication method
	GROUP BY ch.AccountID, ch.ContactID
)
,Letter30DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(DISTINCT ch.CorrespondenceHistoryID) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN tblLetter L ON L.LetterID = ch.CorrespondenceId
	INNER JOIN tblCommunication_Contact c ON c.CommunicationID = L.CommunicationID
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'Letter'
	AND ch.CorrespondenceTS BETWEEN @OneMonthAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	-- UPDATED: Exclude digital letters by BOTH PrintStatusID and CommunicationMethodID
	AND ISNULL(L.PrintStatusID,0) <> -2
	AND ISNULL(c.CommunicationMethodID,0) <> 5 -- Exclude Digital communication method
	GROUP BY ch.AccountID, ch.ContactID
)
,Email7DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'Email'
	AND ch.CorrespondenceTS BETWEEN @OneWeekAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	AND ch.CorrespondenceStatusID IN (2, 9) -- #319: Delivered (2) + Externally Sent (9)
	GROUP BY ch.AccountID, ch.ContactID
)
,Email30DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'Email'
	AND ch.CorrespondenceTS BETWEEN @OneMonthAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	AND ch.CorrespondenceStatusID IN (2, 9) -- #319: Delivered (2) + Externally Sent (9)
	GROUP BY ch.AccountID, ch.ContactID
)
,SMS7DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'SMS'
	AND ch.CorrespondenceTS BETWEEN @OneWeekAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	AND ch.CorrespondenceStatusID IN (2, 8) -- #319: Successful (2) + Externally Sent (8)
	GROUP BY ch.AccountID, ch.ContactID
)
,SMS30DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0)  AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'SMS'
	AND ch.CorrespondenceTS BETWEEN @OneMonthAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	AND ch.CorrespondenceStatusID IN (2, 8) -- #319: Successful (2) + Externally Sent (8)
	GROUP BY ch.AccountID, ch.ContactID
)
,Phone7DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'Phone'
	AND ch.CorrespondenceTS BETWEEN @OneWeekAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	GROUP BY ch.AccountID, ch.ContactID
)
,Phone30DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'Phone'
	AND ch.CorrespondenceTS BETWEEN @OneMonthAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	GROUP BY ch.AccountID, ch.ContactID
)
,IVR7DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'IVR'
	AND ch.CorrespondenceTS BETWEEN @OneWeekAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	GROUP BY ch.AccountID, ch.ContactID
)
,IVR30DayCount AS
(
	SELECT ch.AccountID, ch.ContactID, COUNT(0) AS TotalCount
	FROM tblCorrespondenceHistory ch
	INNER JOIN AccountContacts ac ON ac.AccountID = ch.AccountID AND ac.ContactID = ch.ContactID
	WHERE ch.CorrespondenceType = 'IVR'
	AND ch.CorrespondenceTS BETWEEN @OneMonthAgoDate AND @TodayDate
	AND ch.StatusID = 1
	AND ch.CorrespondenceSolicited = 0 -- UNSOLICITED
	GROUP BY ch.AccountID, ch.ContactID
)
UPDATE ac
SET LUPLetterCountLast7days = ISNULL(l7.TotalCount,0),
LUPLetterCountLast30days = ISNULL(l30.TotalCount,0),
LUPEmailCountLast7days = ISNULL(e7.TotalCount,0),
LUPEmailCountLast30days = ISNULL(e30.TotalCount,0),
LUPSMSCountLast7days = ISNULL(s7.TotalCount,0),
LUPSMSCountLast30days = ISNULL(s30.TotalCount,0),
LUPPhoneCountLast7days = ISNULL(p7.TotalCount,0),
LUPPhoneCountLast30days = ISNULL(p30.TotalCount,0),
LUPIVRCountLast7days = ISNULL(v7.TotalCount,0),
LUPIVRCountLast30days = ISNULL(v30.TotalCount,0),
LUPCorrespondenceCountLast7days = ISNULL(l7.TotalCount,0) + ISNULL(e7.TotalCount,0) + ISNULL(s7.TotalCount,0) + ISNULL(p7.TotalCount,0) + ISNULL(v7.TotalCount,0),
LUPCorrespondenceCountLast30days = ISNULL(l30.TotalCount,0) + ISNULL(e30.TotalCount,0) + ISNULL(s30.TotalCount,0) + ISNULL(p30.TotalCount,0) + ISNULL(v30.TotalCount,0),
ModifyID = 1,
ModifySessionID = {{CurrentSessionID}},
ModifyTS = GETDATE()
FROM tblAccount_Contact ac
INNER JOIN AccountContacts acc ON acc.AccountID = ac.AccountID AND acc.ContactID = ac.ContactID
LEFT JOIN Letter7DayCount l7 ON l7.AccountID = ac.AccountID AND l7.ContactID = ac.ContactID
LEFT JOIN Letter30DayCount l30 ON l30.AccountID = ac.AccountID AND l30.ContactID = ac.ContactID
LEFT JOIN Email7DayCount e7 ON e7.AccountID = ac.AccountID AND e7.ContactID = ac.ContactID
LEFT JOIN Email30DayCount e30 ON e30.AccountID = ac.AccountID AND e30.ContactID = ac.ContactID
LEFT JOIN SMS7DayCount s7 ON s7.AccountID = ac.AccountID AND s7.ContactID = ac.ContactID
LEFT JOIN SMS30DayCount s30 ON s30.AccountID = ac.AccountID AND s30.ContactID = ac.ContactID
LEFT JOIN Phone7DayCount p7 ON p7.AccountID = ac.AccountID AND p7.ContactID = ac.ContactID
LEFT JOIN Phone30DayCount p30 ON p30.AccountID = ac.AccountID AND p30.ContactID = ac.ContactID
LEFT JOIN IVR7DayCount v7 ON v7.AccountID = ac.AccountID AND v7.ContactID = ac.ContactID
LEFT JOIN IVR30DayCount v30 ON v30.AccountID = ac.AccountID AND v30.ContactID = ac.ContactID
OPTION (RECOMPILE);

PRINT CAST(SYSDATETIME() AS VARCHAR(19)) + ' Correspondence counters updated for '
    + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' account contacts.';

DROP TABLE #LUPPairs;

    
PRINT SYSDATETIME()
PRINT 'Calculating account totals.'


SET @loopIndex = 1
SELECT  @maxIndex = MAX(ID)
FROM    @InsertedAccounts


WHILE ( @loopIndex <= @maxIndex )
    BEGIN

        SELECT  @currAccountID = AccountID
        FROM    @InsertedAccounts
        WHERE   ID = @loopIndex

        EXEC dbo.spAccountCalculateTotals @UserContactID = 1, @AccountID = @currAccountID

        SET @loopIndex = @loopIndex + 1

        -- Print message every 1000 iterations
        IF @loopIndex % 1000 = 0
        BEGIN
            PRINT CAST(SYSDATETIME() AS VARCHAR(19)) + ' Processing ' + CAST(@loopIndex AS VARCHAR(10))
        END

    END

PRINT SYSDATETIME()
PRINT 'Finished account totals.'