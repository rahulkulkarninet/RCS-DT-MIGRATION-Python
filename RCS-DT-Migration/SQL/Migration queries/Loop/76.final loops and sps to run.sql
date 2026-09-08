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
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = DL.Extended_Debt_Code
        WHERE   A.AccountID = @currAccountID


        IF ( @InstalmentDate IS NOT NULL
             AND @InstalmentAmt IS NOT NULL
           )
            BEGIN
                INSERT  INTO tblArrangementSchedule
                        ( ArrangementID ,
                          InstallmentAmount ,
                          InstallmentDue ,
                          ArrangementTotalDueToDate ,
                          CreateID ,
                          CreateTS
                        )
                        SELECT  @currArrangementID ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                CONVERT(DATE, REPLACE(installmentDate.Line,'''',''), 120) ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                1 ,
                                GETDATE()
                        FROM    dbo.fnSplitTextIntoTable(@InstalmentAmt, '|') installmentAmt
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InstalmentDate, '|') installmentDate ON installmentAmt.[LineNo] = installmentDate.[LineNo]
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
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = AR.Extended_Debt_Code
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
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = AR.Extended_Debt_Code
        WHERE   A.AccountID = @currAccID


        IF ( @arInstalmentDate IS NOT NULL
             AND @arInstalmentAmt IS NOT NULL
           )
            BEGIN
                INSERT  INTO tblArrangementSchedule
                        ( ArrangementID ,
                          InstallmentAmount ,
                          InstallmentDue ,
                          ArrangementTotalDueToDate ,
                          CreateID ,
                          CreateTS
                        )
                        SELECT  @currArID ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                CONVERT(DATE, REPLACE(installmentDate.Line,'''',''), 120) ,
                                CONVERT(DECIMAL(18, 2), REPLACE(installmentAmt.Line,'''','')) ,
                                1 ,
                                GETDATE()
                        FROM    dbo.fnSplitTextIntoTable(@arInstalmentAmt, '|') installmentAmt
                                LEFT JOIN dbo.fnSplitTextIntoTable(@arInstalmentDate, '|') installmentDate ON installmentAmt.[LineNo] = installmentDate.[LineNo]
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
        LEFT JOIN CSRC_OperatorContactMapping OM ON OM.OperatorCode = X.Operator

        SET @currAccountID = NULL
        SET @currWorkflowLineID = NULL
        SET @currAccountStatusHistoryString = NULL
        SET @currAccountStatusTimestameString = NULL
        SET @currOperatorString = NULL


        SET @loopIndex = @loopIndex + 1

    END


PRINT SYSDATETIME()
PRINT 'Finished Account Status History.'


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
    JOIN RC_DEBTOR DR ON DR.Debt_Code = A.AccountNumberPrevious
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

DECLARE @currContactID INT

DECLARE @InsertedAccountContacts TABLE
(
ID INT IDENTITY(1, 1),
AccountID INT,
ContactID INT
)

INSERT INTO @InsertedAccountContacts
(AccountID,
ContactID
)
SELECT AC.AccountID, AC.ContactID
FROM tblAccount_Contact AC
JOIN tblAccount A ON A.AccountID = AC.AccountID
WHERE A.LoadID = {{LoadID}};

SET @loopIndex = 1
SELECT  @maxIndex = MAX(ID) FROM @InsertedAccountContacts

WHILE ( @loopIndex <= @maxIndex )
    BEGIN
        SELECT  @currAccountID = AccountID, @currContactID = ContactID
        FROM    @InsertedAccountContacts
        WHERE   ID = @loopIndex

        EXEC dbo.spAccount_Contact_CorrespondenceRecalculate
            @User_ContactID = 1,
            @User_SessionID = {{CurrentSessionID}},
            @AccountID = @currAccountID,
            @ContactID = @currContactID;

        SET @loopIndex = @loopIndex + 1

        -- Print message every 1000 iterations
        IF @loopIndex % 1000 = 0
        BEGIN
            PRINT CAST(SYSDATETIME() AS VARCHAR(19)) + ' Processing ' + CAST(@loopIndex AS VARCHAR(10))
        END

    END
    
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