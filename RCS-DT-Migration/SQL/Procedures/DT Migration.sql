-- RCS/DT Migration script
-- 13/08/25 CC Change to add Collection costs & Payment allocations
-- 18/08/25 CC Change to derive Z_DB from RC_ACCOUNT_EXTRACT
-- 19/08/25 CC Change to allocate overpayments
-- 21/08/25 CC Change to make sure only valid reps are created as contacts
-- 27/08/25 CC Change to add additional DebtInfo fields for tranche #1
-- 01/11/25 CC Change to update contact counters and Insurance/accident details

--use [sqldb-glass-dev-rc]

DECLARE @EntityID INT = 114

DECLARE @LoadID INT
DECLARE @CurrentSessionID INT
DECLARE @AccountStatusID_Creation INT = NULL
DECLARE @ContactDetailTypeID_Home INT = NULL
-- Begin Mod 01/11/25
DECLARE @ContactDetailTypeID_Work INT = NULL
-- End Mod 01/11/25
DECLARE @ContactDetailTypeID_Mobile INT = NULL
DECLARE @ContactDetailTypeID_Email INT = NULL
DECLARE @AddressTypeID_Home INT = NULL
DECLARE @AddressTypeID_Mail INT = NULL
DECLARE @AddressTypeID_Legal INT = NULL
DECLARE @BankAccountID_DefaultHost INT = NULL
DECLARE @ContactTypeID_Individual INT = 4
DECLARE @ContactTypeID_Entity INT = 3
DECLARE @ContactTypeID_3PDM INT = NULL
DECLARE @DefaultCountryID INT
DECLARE @EntryTypeID_Treatment INT = NULL
DECLARE @EntryTypeID_Result INT = NULL
DECLARE @ArrangementTypeID_Deal INT = NULL
DECLARE @RelationshipID_3PDM INT = NULL

DECLARE @BankTransactionMethodID_DirectPayment INT

DECLARE @AccountSpecificsGroupID_DebtReferenceNumbers INT
DECLARE @AccountSpecificsGroupID_DrDebtInfo INT

DECLARE @AccountSpecificsGroupID_MIMO INT
DECLARE @AccountSpecificsGroupID_MTTP INT
DECLARE @AccountSpecificsGroupID_INOU INT
DECLARE @AccountSpecificsGroupID_LEAK INT
DECLARE @AccountSpecificsGroupID_NEWA INT
DECLARE @AccountSpecificsGroupID_EOCH INT
DECLARE @AccountSpecificsGroupID_COPY INT
DECLARE @AccountSpecificsGroupID_METQ INT
DECLARE @AccountSpecificsGroupID_MISS INT
DECLARE @AccountSpecificsGroupID_DLO INT
DECLARE @AccountSpecificsGroupID_BILL INT
-- RelationshipIDs for related parties (tblRelationship)
DECLARE @RelationshipID_Guarantor INT = 19
DECLARE @RelationshipID_Spouse INT = 2
DECLARE @RelationshipID_Reference INT = 20
DECLARE @RelationshipID_Solicitor INT = 6
DECLARE @RelationshipID_AdditionalCardHolder INT = 21
DECLARE @RelationshipID_Witness INT
DECLARE @RelationshipID_Other INT = 22
-- Begin mod 01/11/25
DECLARE @ContactTypeID_Insured INT = 21
DECLARE @ContactTypeID_InsuredRep INT = 16
DECLARE @ContactTypeID_InsuredDriver INT = 17
DECLARE @ContactTypeID_ThirdPartyDriver INT = 18
DECLARE @ContactTypeID_ThirdPartyOwner INT = 19
DECLARE @ContactTypeID_ThirdPartyInsurer INT = 20

DECLARE @RelationshipID_Insured INT = 41
DECLARE @RelationshipID_InsuredRep INT = 36
DECLARE @RelationshipID_InsuredDriver INT = 37
DECLARE @RelationshipID_ThirdPartyDriver INT = 38
DECLARE @RelationshipID_ThirdPartyOwner INT = 39
DECLARE @RelationshipID_ThirdPartyInsurer INT = 40
-- End mod 01/11/25

SELECT  @AccountStatusID_Creation = ISNULL(AccountStatusID_Creation, 1) ,
        @ContactDetailTypeID_Home = ISNULL(ContactDetailTypeID_HomePhone, 1) ,
-- Begin mod 01/11/25
        @ContactDetailTypeID_Work = ISNULL(ContactDetailTypeID_WorkPhone, 1) ,
-- End mod 01/11/25
        @ContactDetailTypeID_Mobile = ISNULL(ContactDetailTypeID_MobilePhone, 2) ,
        @ContactDetailTypeID_Email = ISNULL(ContactDetailTypeID_DefaultEmail, 4) ,
        @AddressTypeID_Home = ISNULL(AddressTypeID_Home, 1) ,
        @AddressTypeID_Mail = ISNULL(AddressTypeID_Mail, 3) ,
        @BankAccountID_DefaultHost = ISNULL(BankAccountID_DefaultHost, 95) ,
        @DefaultCountryID = ISNULL(DefaultCountryID, 1) ,
        @ContactTypeID_3PDM = ISNULL(ContactTypeID_3PDM, 5),
        @RelationshipID_3PDM = ISNULL(@RelationshipID_3PDM, 11),
		@RelationshipID_Witness = ISNULL(RelationshipID_Witness,17)
FROM    vwHost H1
INNER JOIN vwHost2 H2 ON H1.HostID = H2.HostID

SELECT  @AddressTypeID_Legal = AddressTypeID
FROM    tblAddressType
WHERE   AddressType = 'Legal'

SELECT  @EntryTypeID_Treatment = ISNULL(EntryTypeID, -1)
FROM    tblEntryType
WHERE   EntryType = 'Treatment'
 --Defatul to System Note if missing
SELECT  @EntryTypeID_Result = ISNULL(EntryTypeID, -1)
FROM    tblEntryType
WHERE   EntryType = 'Result'
 --Defatul to System Note if missing

SELECT  @ArrangementTypeID_Deal = ISNULL(ArrangementTypeID, 1)
FROM    tblArrangementType
WHERE   ArrangementType = 'Deal'

SELECT  @BankTransactionMethodID_DirectPayment = BankTransactionMethodID
FROM    tblBankTransactionMethod
WHERE   LTRIM(RTRIM(BankTransactionMethod)) = 'Direct Payment'

SELECT  @AccountSpecificsGroupID_DebtReferenceNumbers = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'DebtReferenceNumbers'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_DrDebtInfo = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'DrDebtInfo'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_MIMO = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'MIMO'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_MTTP = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'MTTP'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_INOU = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'INOU'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_LEAK = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'LEAK'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_NEWA = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'NEWA'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_EOCH = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'EOCH'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_COPY = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'COPY'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_METQ = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'METQ'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_MISS = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'MISS'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_DLO = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'DLO'
        AND StatusID = 1

SELECT  @AccountSpecificsGroupID_BILL = MetaField_AccountSpecificsGroupID
FROM    tblMetaField_AccountSpecificsGroup
WHERE   MetaField_AccountSpecificsGroup = 'BILL'
        AND StatusID = 1



--CREATE LOG TABLE

DROP TABLE IF EXISTS tblMigrationLog;

CREATE TABLE tblMigrationLog
    (
      MigrationLogID INT IDENTITY(1, 1) ,
      MigrationLogTS DATETIME2(7) ,
      MigrationLogMessage NVARCHAR(MAX),
      LoadID INT NULL
    );


PRINT SYSDATETIME()
PRINT 'Starting Migration'


INSERT  INTO tblLoad
        ( LoadDescription ,
-- Begin mod 01/11/25
          EntityID,
-- End Mod 01/11/25
          LoadTypeID ,
          CreateID ,
          CreateTS
        )
VALUES  ( 'Migration Account Load' ,
-- Begin Mod 01/11/25
          @EntityID,
-- End Mod 01/11/25
          0 ,
          1 ,
          GETDATE()
        )


SELECT  @LoadID = SCOPE_IDENTITY()


PRINT 'LoadID'

PRINT @LoadID


INSERT  INTO tblSession
        ( ContactID ,
          UserName ,
          LoginTime ,
          StatusID
        )
        SELECT  1 ,
                'admin' ,
                GETDATE() ,
                1

SELECT  @CurrentSessionID = SCOPE_IDENTITY()
PRINT 'SessionID'
PRINT @currentSessionID

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Starting Migration',
          @LoadID
        );

-- Set up Lookup Translation Mappings --


PRINT SYSDATETIME()
PRINT 'Setting up Lookup Mappings'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Setting up Lookup Mappings',
          @LoadID
        );


DECLARE @AccountStatusMappings TABLE
    (
      SourceValue NVARCHAR(500) ,
      DebtrakAccountStatusID INT
    )

DECLARE @ProductMappings TABLE
    (
      SourceValue NVARCHAR(500) ,
      DebtrakProductID INT
    )

DECLARE @ClosureReasonMappings TABLE
    (
      SourceValue NVARCHAR(500) ,
      DebtrakClosureReasonID INT
    )

DECLARE @CostTypeMappings TABLE
    (
      SourceValue NVARCHAR(500) ,
      DebtrakCostTypeID INT,
	  DebtrakMasterCostID INT
    )

DECLARE @OperatorContactMappings TABLE
    (
      SourceValue NVARCHAR(500) ,
      DebtrakContactID INT
    )


INSERT  INTO @AccountStatusMappings
        ( SourceValue ,
          DebtrakAccountStatusID
        )
        SELECT DISTINCT
                ReferenceCode ,
                ReferenceIDDestination
        FROM    dbo.fnGetMappingIDsForMigration('CSRC_AccountStatusMapping')



INSERT  INTO @ProductMappings
        ( SourceValue ,
          DebtrakProductID
        )
        SELECT DISTINCT
                ReferenceCode ,
                ReferenceIDDestination
        FROM    dbo.fnGetMappingIDsForMigration('CSRC_ProductMapping')


INSERT  INTO @ClosureReasonMappings
        ( SourceValue ,
          DebtrakClosureReasonID
        )
        SELECT DISTINCT
                ReferenceCode ,
                ReferenceIDDestination
        FROM    dbo.fnGetMappingIDsForMigration('CSRC_ClosureReasonMapping')

INSERT  INTO @CostTypeMappings
        ( SourceValue ,
          DebtrakCostTypeID
        )
        SELECT DISTINCT
                ReferenceCode ,
                ReferenceIDDestination
        FROM    dbo.fnGetMappingIDsForMigration('CSRC_CostTypeMapping')

INSERT  INTO @OperatorContactMappings
        ( SourceValue ,
          DebtrakContactID
        )
        SELECT DISTINCT
                ReferenceCode ,
                ReferenceIDDestination
        FROM    dbo.fnGetMappingIDsForMigration('CSRC_OperatorContactMapping')



PRINT SYSDATETIME()
PRINT 'Starting INSERT into tblAccount'

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
          Z_DB
        )
        SELECT 
                @LoadID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                @EntityID ,
                1 ,
                ISNULL(ASMap.AccountStatusID, @AccountStatusID_Creation) ,
                P.ProductID ,
                LEFT(RC.Debtor_Code, 250) ,
                rc.Account_No ,
                RC.Full_Debt_Code ,
                RC.Short_Debt_Code ,
                NULL ,
                ISNULL(OM.DebtrakContactID, 1) ,
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
                ISNULL(CRMap.DebtrakClosureReasonID, 1) ,
                LEFT(RC.Score_Colour_DB, 30) ,
                RC.Date_of_Debt ,
                NULL ,
                RC.SystemID
        FROM    [RC_ACCOUNT_EXTRACT] RC
                CROSS APPLY ( SELECT TOP 1
                                        AccountStatusID
                              FROM      tblAccountStatus
                              WHERE     AccountStatus = RC.MA_Status
                            ) AsMap
                LEFT JOIN tblProduct P ON P.Product = RC.WorkType
                LEFT JOIN @ClosureReasonMappings CRMap ON RC.Reason_Closed = CRMap.SourceValue
                LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = RC.Operator
        ORDER BY 
                RC.Last_Pay DESC

PRINT SYSDATETIME()
PRINT 'Finished INSERT into tblAccount.'


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished INSERT into tblAccount.',
          @LoadID
        );

PRINT SYSDATETIME()
PRINT 'Creating Worflow Lines.'



INSERT  INTO tblWorkflowLine WITH ( ROWLOCK )
        ( AccountID ,
          AccountStatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          MasterWorkflowID ,
          LoadID
        )
        SELECT  A.AccountID ,
                A.AccountStatusID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 AS StatusID ,
                E.DefautMasterWorkflowID AS MasterWorkflowID ,
                @LoadID
        FROM    tblAccount A WITH ( NOLOCK )
                INNER JOIN tblEntity E WITH ( NOLOCK ) ON A.EntityID = E.EntityID
        WHERE   A.LoadID = @LoadID
 

 
PRINT SYSDATETIME()
PRINT 'Creating Principals from DRDBINVOICE.'


INSERT  INTO tblPrincipal WITH ( ROWLOCK )
        ( AccountID ,
          TransactionDate ,
          TransactionAmount ,
          TransactionDesc ,
          ClientTransactionReference ,
		  LUPAllocatedAmount,
          LUPBalance ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID,
		  Z_REF
        )
        SELECT  A.AccountID ,
                PR.Invoice_Date ,
                PR.Invoice_Amount ,
                PR.Description ,
                PR.Account_No ,
	            ISNULL(PR.Total_Paid_Amount, 0) ,
                ISNULL(PR.Outstanding, 0) ,
                1 ,
                @CurrentSessionID ,
                PR.Entry_Date , --CreateTS,
                1 ,
                @LoadID,
                REPLACE(REPLACE(REPLACE(PR.Invoice_Number, CHAR(13), ''), CHAR(10), ''), ' ', '')

        FROM    [RC_DRDBINVOICE] PR
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = PR.Full_Debt_Code
        WHERE   A.LoadID = @LoadID


PRINT SYSDATETIME()
PRINT 'Creating Principals from DRMEDINV.'

DECLARE @InvoiceDates VARCHAR(MAX)
DECLARE @InvoiceAmounts VARCHAR(MAX)
DECLARE @InvoicePaid VARCHAR(MAX)
DECLARE @InvoiceBalance VARCHAR(MAX)
DECLARE @InvoiceNumber VARCHAR(MAX)
DECLARE @InvoiceAccountID INT
DECLARE @InvoiceAccountNo VARCHAR(100)
DECLARE @InvoiceDescription VARCHAR(500)
DECLARE @InvoicefullDebtCode VARCHAR(20)
----------------------------------
DECLARE @MedInvoice TABLE 
(     
    ID INT IDENTITY(1,1),
	FullDebtCode NVARCHAR(20)

)
INSERT INTO @MedInvoice (FullDebtCode) SELECT Full_Debt_Code FROM RC_DRMEDINV

IF EXISTS (SELECT 1 FROM @MedInvoice)
BEGIN
   DECLARE @invLoopIndex INT = 1
   DECLARE @invMaxIndex INT;
   SELECT  @invMaxIndex = MAX(ID)
   FROM    @MedInvoice
   WHILE ( @invLoopIndex <= @invMaxIndex )
   BEGIN
        SELECT  @InvoicefullDebtCode = FullDebtCode
        FROM    @MedInvoice
        WHERE   ID = @invLoopIndex

    BEGIN

        SELECT  @InvoiceDates = Invoice_Date ,
                @InvoiceAmounts = Invoice_Amount,
				@InvoicePaid = Invoice_Paid,
				@InvoiceBalance = Invoice_Balance,
				@InvoiceAccountID = A.AccountID,
				@InvoiceAccountNo = Account_No,
				@InvoiceNumber = REPLACE(REPLACE(REPLACE(Invoice_Number, CHAR(13), ''), CHAR(10), ''), ' ', ''),
				@InvoiceDescription = Invoice_Description

        FROM    [RC_DRMEDINV] MI
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = MI.Full_Debt_Code
        WHERE   A.AccountNumberClient = @InvoicefullDebtCode

        IF ( @InvoiceDates IS NOT NULL
             AND @InvoiceAmounts IS NOT NULL
           )
            BEGIN

				INSERT  INTO tblPrincipal WITH ( ROWLOCK )
						( AccountID ,
						  TransactionDate ,
						  TransactionAmount ,
						  TransactionDesc ,
						  ClientTransactionReference ,
						  LUPAllocatedAmount,
						  LUPBalance ,
						  CreateID ,
						  CreateSessionID ,
						  CreateTS ,
						  StatusID ,
						  LoadID,
						  Z_REF
						)
                        SELECT  
						        @InvoiceAccountID,
                                CONVERT(DATE, REPLACE(invoiceDate.Line,'''',''), 120) ,
                                CONVERT(DECIMAL(18, 2), REPLACE(invoiceAmount.Line,'''','')),
								@InvoiceDescription,
								@InvoiceAccountNo,
					            CONVERT(DECIMAL(18, 2), REPLACE(invoicePaid.Line,'''','')),
					            CONVERT(DECIMAL(18, 2), REPLACE(invoiceBalance.Line,'''','')),
								1,
								@CurrentSessionID,
				                CONVERT(DATE, REPLACE(invoiceDate.Line,'''',''), 120), 
								1,
								@LoadID,
								REPLACE(invoiceNumber.Line,'''','')

                        FROM    dbo.fnSplitTextIntoTable(@InvoiceAmounts, '|') invoiceAmount
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoiceDates, '|') invoiceDate ON invoiceAmount.[LineNo] = invoiceDate.[LineNo]
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoicePaid, '|') invoicePaid ON invoiceAmount.[LineNo] = invoicePaid.[LineNo]
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoiceBalance, '|') invoiceBalance ON invoiceAmount.[LineNo] = invoiceBalance.[LineNo]
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoiceNumber, '|') invoiceNumber ON invoiceAmount.[LineNo] = invoiceNumber.[LineNo]
                 --

            END

END

		SET @invLoopIndex +=1 

   END
END



INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished Creating Principals in tblPrincipal.',
          @LoadID
        );

--Account Specifics Permissions

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating Account Specifics Permissions.',
          @LoadID
        );

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_DebtReferenceNumbers )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_DebtReferenceNumbers ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END


IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_DrDebtInfo )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_DrDebtInfo ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END


IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_MIMO )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_MIMO ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_MTTP )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_MTTP ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_INOU )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_INOU ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_LEAK )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_LEAK ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_NEWA )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_NEWA ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_EOCH )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_EOCH ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_COPY )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_COPY ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_METQ )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_METQ ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_MISS )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_MISS ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_DLO )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_DLO ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END

IF NOT EXISTS ( SELECT  1
                FROM    tblEntity_AccountSpecifics
                WHERE   EntityID = @EntityID
                        AND AccountSpecifics_MetaFieldGroupID = @AccountSpecificsGroupID_BILL )
    BEGIN
        INSERT  INTO tblEntity_AccountSpecifics
                ( EntityID ,
                  AccountSpecifics_MetaFieldGroupID ,
                  CreateID ,
                  CreateSessionID ,
                  CreateTS ,
                  StatusID ,
                  IsOpenOnAccountLoad
                )
        VALUES  ( @EntityID ,
                  @AccountSpecificsGroupID_BILL ,
                  1 ,
                  @CurrentSessionID ,
                  GETDATE() ,
                  1 ,
                  1
                );
    END


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished Account Specifics Permissions.',
          @LoadID
        );


PRINT SYSDATETIME()
PRINT 'Creating account specifics Debt Reference Numbers.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating account specifics Debt Reference Numbers.',
          @LoadID
        );

--DebtReference  Numbers

--MetaValue Group
INSERT  INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_DebtReferenceNumbers ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_DebtReferenceNumbers
                                        AND Z_AccountID = A.AccountID )


INSERT  INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_DebtReferenceNumbers ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_DebtReferenceNumbers;


        
DECLARE @DebtRefNoMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT  INTO @DebtRefNoMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_DebtReferenceNumbers;
WITH    CTE_DebtRefData
          AS ( SELECT DISTINCT
                        Full_Debt_Code ,
                        A.MFID ,
                        A.Name ,
                        Debt_Ref_No AS Value
               FROM     RC_ACCOUNT_EXTRACT
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtRefNoMFields
                                      WHERE     [Name] = 'DebtRefNo'
                                    ) AS A
               UNION ALL
               SELECT DISTINCT
                        Full_Debt_Code ,
                        A.MFID ,
                        A.Name ,
                        Debt_Ref_No2 AS Value
               FROM     RC_ACCOUNT_EXTRACT
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtRefNoMFields
                                      WHERE     [Name] = 'DebtRefNo2'
                                    ) AS A
               UNION ALL
               SELECT DISTINCT
                        Full_Debt_Code ,
                        A.MFID ,
                        A.Name ,
                        Debt_Ref_No3 AS Value
               FROM     RC_ACCOUNT_EXTRACT
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtRefNoMFields
                                      WHERE     [Name] = 'DebtRefNo3'
                                    ) AS A
               UNION ALL
               SELECT DISTINCT
                        Full_Debt_Code ,
                        A.MFID ,
                        A.Name ,
                        Debt_Ref_No_4 AS Value
               FROM     RC_ACCOUNT_EXTRACT
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtRefNoMFields
                                      WHERE     [Name] = 'DebtRefNo4'
                                    ) AS A
             )
    INSERT  INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
            ( MetaField_AccountSpecificsID ,
              MetaValue_AccountSpecificsGroupID ,
              ValueString ,
              CreateID ,
              CreateSessionID ,
              CreateTS ,
              StatusID
            )
            SELECT  MF.MetaField_AccountSpecificsID ,
                    MVG.MetaValue_AccountSpecificsGroupID ,
                    ISNULL(CTE_DebtRefData.Value, '') ,
                    1 ,
                    @CurrentSessionID ,
                    GETDATE() ,
                    1
            FROM    CTE_DebtRefData
                    INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_DebtRefData.Full_Debt_Code
                    INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_DebtRefData.MFID
                    INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                         AND MVG.Z_AccountID = A.AccountID
            WHERE   A.LoadID = @LoadID 
            AND (Value IS NOT NULL)


--END DebtReference  Numbers


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished account specifics Debt Reference Numbers.',
          @LoadID
        );




--DR Debt Info

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating DR Debt Info.',
          @LoadID
        );

INSERT  INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_DrDebtInfo ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_DrDebtInfo
                                        AND Z_AccountID = A.AccountID )

INSERT  INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_DrDebtInfo ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_DrDebtInfo;




DECLARE @DebtInfoMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT  INTO @DebtInfoMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_DrDebtInfo;
WITH    CTE_DrDbInfoData
          AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Property_Address_Line_1 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Property_Address_Line_1'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Property_Address_Line_2 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Property_Address_Line_2'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Property_Address_Line_3 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Property_Address_Line_3'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Property_Suburb AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Property_Suburb'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Property_State AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Property_State'
                                    ) AS A
               UNION ALL
                SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Property_Post_Code AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Property_Post_Code'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Account_Type_Additional_Worktype AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Account_Type_Additional_Worktype'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Overdue_Amount AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Overdue_Amount'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        Cycle_Days AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Cycle_Days'
                                    ) AS A
               UNION ALL

               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Over_Limit AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Over_Limit'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Credit_Limit AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Credit_Limit'
                                    ) AS A
               UNION ALL

               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Credit_Listing AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Credit_Listing'
                                    ) AS A
               UNION ALL

               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        S88_Date_DN_Expiry_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'S88_Date_DN_Expiry_Date'
                                    ) AS A
               UNION ALL



               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        _3rd_Party_Auth AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = '3rd_Party_Auth'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        BPAY_reference AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'BPAY_reference'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Last_Monetary_Amount_Last_Pay_Amount AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Last_Monetary_Amount_Last_Pay_Amount'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Last_Monetary_Type_Last_Payment_Type AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Last_Monetary_Type_Last_Payment_Type'
                                    ) AS A
               UNION ALL

               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Last_Monetary_Date_Last_Pay_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Last_Monetary_Date_Last_Pay_Date'
                                    ) AS A
               UNION ALL 

               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Concession_Concession_Type AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Concession_Concession_Type'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Arrears_Past_Due_Upd AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Arrears_Past_Due_Upd'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Risk_Client_Risk_Code AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Risk_Client_Risk_Code'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Property_Reference_Di_Proptype AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Property_Reference_Di_Proptype'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Barcode_Data_Unique_Key AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Barcode_Data_Unique_Key'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Ocr_Line AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Ocr_Line'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Dhs_Tenant AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Dhs_Tenant'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Account_Authorisation AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Account_Authorisation'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Payplan_Status_Receipt_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Payplan_Status_Receipt_Details'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Expected_Payment_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Expected_Payment_Date'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Score_Colour_On_Load AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Score_Colour_On_Load'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Contact AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Solicitor_Contact'
                                    ) AS A

               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Tdx_Closure_Reason_Code AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Tdx_Closure_Reason_Code'
                                    ) AS A



               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Date_Account_Opened AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Date_Account_Opened'
                                    ) AS A

               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Total_Paid AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Total_Paid'
                                    ) AS A

               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Amount_Deposited AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Amount_Deposited'
                                    ) AS A
               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Original_Debt_Amount AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Original_Debt_Amount'
                                    ) AS A

               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Amount_Outstanding AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Amount_Outstanding'
                                    ) AS A


               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Fee_Amount AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Fee_Amount'
                                    ) AS A


               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Amount_Outstanding_Update AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Amount_Outstanding_Update'
                                    ) AS A


               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Contact_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Contact_Details'
                                    ) AS A




               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Id_Type AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Id_Type'
                                    ) AS A




               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Id_Number AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Id_Number'
                                    ) AS A


               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Client_Advice AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Client_Advice'
                                    ) AS A


               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Account_Status AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Account_Status'
                                    ) AS A


               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Due_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Due_Date'
                                    ) AS A



               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Last_Invoice_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Last_Invoice_Date'
                                    ) AS A

               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        End_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'End_Date'
                                    ) AS A

		       UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        _6Q_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = '_6Q_Date'
                                    ) AS A

		       UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        _21D_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = '_21D_Date'
                                    ) AS A

-----




               UNION ALL
               SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Date_Payment_Made AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DebtInfoMFields
                                      WHERE     [Name] = 'Date_Payment_Made'
                                    ) AS A
             )
    --SELECT * FROM CTE_DrDbInfoData 
INSERT  INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_DrDbInfoData.ValueString ,
                CTE_DrDbInfoData.ValueInteger ,
                CTE_DrDbInfoData.ValueDecimal ,
                CTE_DrDbInfoData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_DrDbInfoData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_DrDbInfoData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_DrDbInfoData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)




--END DR Debt Info
INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished DR Debt Info.',
          @LoadID
        );

--MIMO
INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating MIMO.',
          @LoadID
        );

INSERT  INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_MIMO ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_MIMO
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_MIMO ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_MIMO;

DECLARE @MIMOMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT  INTO @MIMOMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_MIMO;

;WITH    CTE_MIMOData
          AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Move_in_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Move_in_Date'
                                    ) AS A             
             UNION ALL
             SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Move_out_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Move_out_Date'
                                    ) AS A
             UNION ALL
             SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Agent_Name AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Agent_Name'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Agent_Address_1 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Agent_Address_1'
                                    ) AS A
             UNION ALL
             SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Agent_Address_2 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Agent_Address_2'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Agent_Suburb AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Agent_Suburb'
                                    ) AS A
             UNION ALL
             SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Agent_State AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Agent_State'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Agent_Postcode AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Agent_Postcode'
                                    ) AS A
             UNION ALL
             SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Agent_Phone_No AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'Agent_Phone_No'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Addr1 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'New_Postal_Addr1'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Addr2 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'New_Postal_Addr2'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Addr3 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'New_Postal_Addr3'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Sub AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'New_Postal_Sub'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_State AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'New_Postal_State'
                                    ) AS A
            UNION ALL
            SELECT  Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Pcode AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MIMOMFields
                                      WHERE     [Name] = 'New_Postal_Pcode'
                                    ) AS A



    )
    INSERT  INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
            ( MetaField_AccountSpecificsID ,
              MetaValue_AccountSpecificsGroupID ,
              ValueString ,
              ValueInt ,
              ValueDecimal ,
              ValueDateTime ,
              CreateID ,
              CreateSessionID ,
              CreateTS ,
              StatusID
            )
            SELECT  MF.MetaField_AccountSpecificsID ,
                    MVG.MetaValue_AccountSpecificsGroupID ,
                    CTE_MIMOData.ValueString ,
                    CTE_MIMOData.ValueInteger ,
                    CTE_MIMOData.ValueDecimal ,
                    CTE_MIMOData.ValueDateTime ,
                    1 ,
                    @CurrentSessionID ,
                    GETDATE() ,
                    1
            FROM    CTE_MIMOData
                    INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_MIMOData.Full_Debt_Code
                    INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_MIMOData.MFID
                    INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                         AND MVG.Z_AccountID = A.AccountID
            WHERE   A.LoadID = @LoadID
            AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished MIMO.',
          @LoadID
        );

--END OF MIMO


--MTTP
INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating MTTP.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_MTTP ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_MTTP
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_MTTP ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_MTTP;

DECLARE @MTTPMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT  INTO @MTTPMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_MTTP;


;WITH   CTE_MTTPData
          AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Expected_Payment_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MTTPMFields
                                      WHERE     [Name] = 'Expected_Payment_Date'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Payment_Method AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MTTPMFields
                                      WHERE     [Name] = 'Payment_Method'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Next_Payment_Amount AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MTTPMFields
                                      WHERE     [Name] = 'Next_Payment_Amount'
                                    ) AS A

             )
    INSERT  INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
            ( MetaField_AccountSpecificsID ,
              MetaValue_AccountSpecificsGroupID ,
              ValueString ,
              ValueInt ,
              ValueDecimal ,
              ValueDateTime ,
              CreateID ,
              CreateSessionID ,
              CreateTS ,
              StatusID
            )
            SELECT  MF.MetaField_AccountSpecificsID ,
                    MVG.MetaValue_AccountSpecificsGroupID ,
                    CTE_MTTPData.ValueString ,
                    CTE_MTTPData.ValueInteger ,
                    CTE_MTTPData.ValueDecimal ,
                    CTE_MTTPData.ValueDateTime ,
                    1 ,
                    @CurrentSessionID ,
                    GETDATE() ,
                    1
            FROM    CTE_MTTPData
                    INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_MTTPData.Full_Debt_Code
                    INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_MTTPData.MFID
                    INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                         AND MVG.Z_AccountID = A.AccountID
            WHERE   A.LoadID = @LoadID
            AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished MTTP.',
          @LoadID
        );
--END OF MTTP


--INOU

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating INOU.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_INOU ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_INOU
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_INOU ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_INOU;

DECLARE @INOUMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @INOUMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_INOU;

;WITH CTE_INOUData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        Settled_Date AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Settled_Date'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Name AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Name'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Address_1 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Address_1'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Address_2 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Address_2'
                                    ) AS A
            UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Address_3 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Address_3'
                                    ) AS A
            UNION ALL
            SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Address_Sub AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Address_Sub'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Address_State AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Address_State'
                                    ) AS A
            UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Address_Pcode AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Address_Pcode'
                                    ) AS A
             UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Solicitor_Contact AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @INOUMFields
                                      WHERE     [Name] = 'Solicitor_Contact'
                                    ) AS A

             )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_INOUData.ValueString ,
                CTE_INOUData.ValueInteger ,
                CTE_INOUData.ValueDecimal ,
                CTE_INOUData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_INOUData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_INOUData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_INOUData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'FINISHED INOU.',
          @LoadID
        );

--END OF INOU

--LEAK

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating LEAK.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_LEAK ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_LEAK
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_LEAK ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_LEAK;

DECLARE @LEAKMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @LEAKMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_LEAK;

;WITH CTE_LEAKData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Contact_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @LEAKMFields
                                      WHERE     [Name] = 'Contact_Details'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Leak_Fixed AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @LEAKMFields
                                      WHERE     [Name] = 'Leak_Fixed'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Leak_Issue AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDatetime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @LEAKMFields
                                      WHERE     [Name] = 'Leak_Issue'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Leak_Meter_Reading AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDatetime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @LEAKMFields
                                      WHERE     [Name] = 'Leak_Meter_Reading'
                                    ) AS A
             )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_LEAKData.ValueString ,
                CTE_LEAKData.ValueInteger ,
                CTE_LEAKData.ValueDecimal ,
                CTE_LEAKData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_LEAKData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_LEAKData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_LEAKData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished LEAK.',
          @LoadID
        );


--END OF LEAK

--NEWA

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating NEWA.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_NEWA ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_NEWA
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_NEWA ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_NEWA;

DECLARE @NEWAMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @NEWAMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_NEWA;

;WITH CTE_NEWAData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Addr1 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @NEWAMFields
                                      WHERE     [Name] = 'New_Postal_Addr1'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Addr2 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @NEWAMFields
                                      WHERE     [Name] = 'New_Postal_Addr2'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Addr3 AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @NEWAMFields
                                      WHERE     [Name] = 'New_Postal_Addr3'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Sub AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @NEWAMFields
                                      WHERE     [Name] = 'New_Postal_Sub'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_State AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @NEWAMFields
                                      WHERE     [Name] = 'New_Postal_State'
                                    ) AS A
              UNION ALL
                SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        New_Postal_Pcode AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @NEWAMFields
                                      WHERE     [Name] = 'New_Postal_Pcode'
                                    ) AS A
        )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_NEWAData.ValueString ,
                CTE_NEWAData.ValueInteger ,
                CTE_NEWAData.ValueDecimal ,
                CTE_NEWAData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_NEWAData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_NEWAData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_NEWAData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished NEWA.',
          @LoadID
        );

--END OF NEWA

--EOCH

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating EOCH.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_EOCH ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_EOCH
                                        AND Z_AccountID = A.AccountID )

insert into tblAccountSpecifics
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_EOCH ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_EOCH;

DECLARE @EOCHMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @EOCHMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_EOCH;


;WITH CTE_EOCHData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Charges_Required_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @EOCHMFields
                                      WHERE     [Name] = 'Charges_Required_Details'
                                    ) AS A
              )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_EOCHData.ValueString ,
                CTE_EOCHData.ValueInteger ,
                CTE_EOCHData.ValueDecimal ,
                CTE_EOCHData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_EOCHData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_EOCHData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_EOCHData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished EOCH.',
          @LoadID
        );


--END OF EOCH


--COPY

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating COPY.',
          @LoadID
        );


INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_COPY ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_COPY
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_COPY ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_COPY;

DECLARE @COPYMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @COPYMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_COPY;

;WITH CTE_COPYData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Requested_Copy_Of_Account AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @COPYMFields
                                      WHERE     [Name] = 'Requested_Copy_Of_Account'
                                    ) AS A
              )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_COPYData.ValueString ,
                CTE_COPYData.ValueInteger ,
                CTE_COPYData.ValueDecimal ,
                CTE_COPYData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_COPYData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_COPYData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_COPYData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished COPY.',
          @LoadID
        );

--END OF COPY


--METQ

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating METQ.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_METQ ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_METQ
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_METQ ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_METQ;

DECLARE @METQMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @METQMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_METQ;

;WITH CTE_METQData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Details_of_meter_reading AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @METQMFields
                                      WHERE     [Name] = 'Details_of_meter_reading'
                                    ) AS A
        UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Disputed_Reading AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @METQMFields
                                      WHERE     [Name] = 'Disputed_Reading'
                                    ) AS A
        UNION ALL   
        SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Estimated_Reading AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @METQMFields
                                      WHERE     [Name] = 'Estimated_Reading'
                                    ) AS A
              )
    INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( 
            MetaField_AccountSpecificsID ,
            MetaValue_AccountSpecificsGroupID ,
            ValueString ,
            ValueInt ,
            ValueDecimal ,
            ValueDateTime ,
            CreateID ,
            CreateSessionID ,
            CreateTS ,
            StatusID)
              SELECT  MF.MetaField_AccountSpecificsID ,
                      MVG.MetaValue_AccountSpecificsGroupID ,
                      CTE_METQData.ValueString ,
                      CTE_METQData.ValueInteger ,
                      CTE_METQData.ValueDecimal ,
                      CTE_METQData.ValueDateTime ,
                      1 ,
                      @CurrentSessionID ,
                      GETDATE() ,
                      1
                      FROM    CTE_METQData
                      INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_METQData.Full_Debt_Code
                      INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_METQData.MFID
                      INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                      AND MVG.Z_AccountID = A.AccountID
                      WHERE   A.LoadID = @LoadID
                      AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished METQ.',
          @LoadID
        );

--END OF METQ


--MISS

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating MISS.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_MISS ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_MISS
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_MISS ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_MISS;

DECLARE @MISSMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );


INSERT INTO @MISSMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_MISS;

;WITH CTE_MISSData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        Amount_Paid_Total_Payments AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MISSMFields
                                      WHERE     [Name] = 'Amount_Paid_Total_Payments'
                                    ) AS A
              
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        NULL AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,                        
                        Date_Payment_Made AS ValueDateTime                         
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MISSMFields
                                      WHERE     [Name] = 'Date_Payment_Made'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Receipt_No AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime                                                                         
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MISSMFields
                                      WHERE     [Name] = 'Receipt_No'
                                    ) AS A
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        DI_Payment_Method AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime                                                 
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MISSMFields
                                      WHERE     [Name] = 'DI_Payment_Method'
                                    ) AS A     
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Payplan_Status_Receipt_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime                                                                         
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MISSMFields
                                      WHERE     [Name] = 'Payplan_Status_Receipt_Details'
                                    ) AS A      
              UNION ALL
              SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Customer_Contact_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime                                                                         
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @MISSMFields
                                      WHERE     [Name] = 'Customer_Contact_Details'
                                    ) AS A                                          


              )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_MISSData.ValueString ,
                CTE_MISSData.ValueInteger ,
                CTE_MISSData.ValueDecimal ,
                CTE_MISSData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_MISSData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_MISSData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_MISSData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished MISS.',
          @LoadID
        );

--END OF MISS

--DLO

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating DLO.',
          @LoadID
        );


INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_DLO ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_DLO
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_DLO ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_DLO;

DECLARE @DLOMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @DLOMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_DLO;

;WITH CTE_DLOData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Mail_Returned AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @DLOMFields
                                      WHERE     [Name] = 'Mail_Returned'
                                    ) AS A
              )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_DLOData.ValueString ,
                CTE_DLOData.ValueInteger ,
                CTE_DLOData.ValueDecimal ,
                CTE_DLOData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_DLOData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_DLOData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_DLOData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished DLO.',
          @LoadID
        );

--END OF DLO


--BILL

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating Bill.',
          @LoadID
        );

INSERT INTO tblMetaValue_AccountSpecificsGroup WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_AccountID ,
          Z_LoadID
        )
        SELECT  @AccountSpecificsGroupID_BILL ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.AccountID ,
                @LoadID
        FROM    tblAccount A
        WHERE   LoadID = @LoadID
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblMetaValue_AccountSpecificsGroup
                                 WHERE  MetaValue_AccountSpecificsGroupID = @AccountSpecificsGroupID_BILL
                                        AND Z_AccountID = A.AccountID )

INSERT INTO tblAccountSpecifics WITH ( ROWLOCK )
        ( AccountID ,
          MetaField_AccountSpecificsGroupID ,
          MetaValue_AccountSpecificsGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  Z_AccountID ,
                @AccountSpecificsGroupID_BILL ,
                MetaValue_AccountSpecificsGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    tblMetaValue_AccountSpecificsGroup
        WHERE   Z_LoadID = @LoadID
                AND MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_BILL;

DECLARE @BILLMFields TABLE
    (
      [ID] INT IDENTITY(1, 1) ,
      [Name] VARCHAR(255) ,
      [MFID] INT
    );

INSERT INTO @BILLMFields
        ( [Name] ,
          [MFID]
        )
        SELECT  MetaField_AccountSpecifics ,
                MetaField_AccountSpecificsID
        FROM    tblMetaField_AccountSpecifics
        WHERE   MetaField_AccountSpecificsGroupID = @AccountSpecificsGroupID_BILL;

;WITH CTE_BILLData
    AS ( SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Billing_Disput_Issue AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @BILLMFields
                                      WHERE     [Name] = 'Billing_Disput_Issue'
                                    ) AS A
        UNION ALL
        SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Customer_Contact_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @BILLMFields
                                      WHERE     [Name] = 'Customer_Contact_Details'
                                    ) AS A
        UNION ALL
        SELECT   Full_Debt_Code ,
                        A.MFID ,
                        A.Name AS Name ,
                        Billling_Dispue_Details AS ValueString ,
                        NULL AS ValueInteger ,
                        NULL AS ValueDecimal ,
                        NULL AS ValueDateTime
               FROM     RC_DRDEBTINFO
                        OUTER APPLY ( SELECT    MFID ,
                                                Name
                                      FROM      @BILLMFields
                                      WHERE     [Name] = 'Billling_Dispue_Details'
                                    ) AS A
        )
INSERT INTO tblMetaValue_AccountSpecifics WITH ( ROWLOCK )
        ( MetaField_AccountSpecificsID ,
          MetaValue_AccountSpecificsGroupID ,
          ValueString ,
          ValueInt ,
          ValueDecimal ,
          ValueDateTime ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID
        )
        SELECT  MF.MetaField_AccountSpecificsID ,
                MVG.MetaValue_AccountSpecificsGroupID ,
                CTE_BILLData.ValueString ,
                CTE_BILLData.ValueInteger ,
                CTE_BILLData.ValueDecimal ,
                CTE_BILLData.ValueDateTime ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    CTE_BILLData
                INNER JOIN tblAccount A ON A.AccountNumberClient = CTE_BILLData.Full_Debt_Code
                INNER JOIN tblMetaField_AccountSpecifics MF ON MF.MetaField_AccountSpecificsID = CTE_BILLData.MFID
                INNER JOIN tblMetaValue_AccountSpecificsGroup MVG ON mvg.MetaField_AccountSpecificsGroupID = MF.MetaField_AccountSpecificsGroupID
                                                                     AND MVG.Z_AccountID = A.AccountID
        WHERE   A.LoadID = @LoadID
        AND (ValueString IS NOT NULL OR ValueInteger IS NOT NULL OR ValueDecimal IS NOT NULL OR ValueDateTime IS NOT NULL)


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished Bill.',
          @LoadID
        );

--END OF BILL


-- Inserting into tblContact

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting to tblContact.',
          @LoadID
        );

INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,
          Title ,
          FirstName ,
          MiddleName ,
          LastName ,
          DOB ,
          EntityName ,
          TradingAs ,
          BusinessNumber ,
          CorporationNumber,
          IsTemporaryPassword ,
          DriversLicenceNumber ,
          ContactReference ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2
        )
        SELECT DISTINCT
                @LoadID ,
                0 , --IsUser
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, 1, 0) ,	--IsPerson
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, @ContactTypeID_Individual, @ContactTypeID_Entity) ,	--ContactTypeID 
                C.Title ,
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, C.First_Name, NULL) , -- FirstName
                NULL ,	--Middle Name
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, C.Company_Surname, NULL) , -- LastName,
                C.Birth_Date ,
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, NULL, C.Company_Surname) , -- EntityName,
                C.Trading_Name ,
                C.A_B_N ,
                C.A_C_N ,
                1 ,
                C.Drivers_Licence ,
                C.Person_Id ,    -- Pulse ID
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.Full_Debt_Code ,
                C.Debtor_Code
        FROM    RC_DEBTOR C
                INNER JOIN RC_ACCOUNT_EXTRACT A ON C.Debt_Code = A.Full_Debt_Code
                INNER JOIN tblAccount ON tblAccount.AccountNumberClient = A.Full_Debt_Code
                                         AND tblAccount.LoadID = @LoadID
        ORDER BY C.Debtor_Code ASC ,
                A.Full_Debt_Code ASC


INSERT  INTO tblContactAudit
        ( ContactID ,
          AuditTS ,
          LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,
          Title ,
          FirstName ,
          LastName ,
          DOB ,
          EntityName ,
          TradingAs ,
          BusinessNumber ,
          CorporationNumber ,
          DriversLicenceNumber ,
          ContactReference ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2
        )
        SELECT DISTINCT
                tblContact.ContactID ,
                GETDATE() ,
                @LoadID ,
                0 , --IsUser
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, 1, 0) ,	--IsPerson
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, @ContactTypeID_Individual, @ContactTypeID_Entity) ,	--ContactTypeID 
                C.Title ,
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, C.First_Name, NULL) , -- FirstName
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, C.Company_Surname, NULL) , -- LastName,
                C.Birth_Date ,
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, NULL, C.Company_Surname) , -- EntityName,
                C.Trading_Name ,
                C.A_B_N ,
                C.A_C_N ,
                C.Drivers_Licence ,
                C.Person_Id ,    -- Pulse ID
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.Full_Debt_Code ,
                C.Debtor_Code
        FROM    RC_DEBTOR C
                INNER JOIN tblContact ON tblContact.Z_REF2 = C.Debtor_Code
                INNER JOIN RC_ACCOUNT_EXTRACT A ON C.Debt_Code = A.Full_Debt_Code
                INNER JOIN tblAccount ON tblAccount.AccountNumberClient = A.Full_Debt_Code
                                         AND tblAccount.LoadID = @LoadID
        ORDER BY C.Debtor_Code ASC ,
                A.Full_Debt_Code ASC
 



PRINT SYSDATETIME()
PRINT 'Finished INSERT into tblContact. Creating relationships (tblAccount_Contact).'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished INSERT into tblContact. Creating relationships (tblAccount_Contact).',
          @LoadID
        );

INSERT  INTO tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS
        )
        SELECT  a.AccountID ,
                c.ContactID ,
                1--RelationshipID, 1 - Primary Debtor
                ,
                1 ,
                1 ,
                @CurrentSessionID ,
                GETDATE()
        FROM    tblAccount A WITH ( NOLOCK )
                INNER JOIN tblContact C WITH ( NOLOCK ) ON ( A.AccountNumberClient = C.Z_REF
                                                             AND C.StatusID = 1
                                                           )
        WHERE   A.LoadID = @LoadID
                AND C.LoadID = @LoadID
        ORDER BY C.ContactID ASC

-- INSERT 3PDM Contact

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting 3PDM Contact',
          @LoadID
        );

DECLARE @ThirdPartyContacts TABLE
    (
      ID INT IDENTITY(1, 1) ,
      DNumber VARCHAR(50) ,
      DebtrakContactID INT ,
      Contact_Rep_First NVARCHAR(10) ,
      Rep NVARCHAR(100) ,
      Rep_Start_Dte DATETIME ,
      Rep_End_Dte DATETIME ,
      Representative_Name NVARCHAR(300) ,
      Rep_Home_Ph NVARCHAR(100) ,
      Rep_Other_Info NVARCHAR(100) ,
      Representative_Date_Of_Birth DATETIME ,
      Representative_Block_Email NVARCHAR(10) ,
      Representative_Block_Letter NVARCHAR(10) ,
      Representative_Block_SMS NVARCHAR(10) ,
      InsertedAsContactID INT
    )

INSERT  INTO @ThirdPartyContacts
        SELECT  Debtor_Code ,
                NULL ,
                Contact_Rep_First ,
                Rep ,
                Rep_Start_Dte ,
                Rep_End_Dte ,
                Representative_Name ,
                Rep_Home_Ph ,
                Rep_Other_Info ,
                Representative_Date_Of_Birth ,
                Representative_Block_Email ,
                Representative_Block_Letter ,
                Representative_Block_SMS ,
                NULL
        FROM    RC_DEBTOR
            INNER JOIN tblAccount ON tblAccount.AccountNumberClient = RC_DEBTOR.Debt_Code
        WHERE   Contact_Rep_First = 'Yes' and tblAccount.Loadid = @LoadID
                

UPDATE  TPC
SET     DebtrakContactID = C.ContactID
FROM    @ThirdPartyContacts TPC
        INNER JOIN tblContact C ON TPC.DNumber = C.Z_REF2 and C.LoadID = @LoadID




INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,          
          LastName ,
          DOB ,          
          IsTemporaryPassword ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2 ,
          Z_REF3
        )
        SELECT DISTINCT
                @LoadID ,
                0 , --IsUser
                NULL ,    --IsPerson
                ISNULL(@ContactTypeID_3PDM, 5) ,    --ContactTypeID
                TPC.Representative_Name ,
                TPC.Representative_Date_Of_Birth ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                A.Full_Debt_Code ,
                NULL ,
                TPC.DebtrakContactID -- Link to Primary Contact
        FROM    @ThirdPartyContacts TPC
                INNER JOIN tblContact C ON TPC.DebtrakContactID = C.ContactID
                INNER JOIN RC_ACCOUNT_EXTRACT A ON C.Z_REF = A.Full_Debt_Code
                INNER JOIN tblAccount ON tblAccount.AccountNumberClient = A.Full_Debt_Code
                                         AND tblAccount.LoadID = @LoadID        

INSERT  INTO  tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          Related_ContactID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS
        )
SELECT 
    A.AccountID ,
    RepContact.ContactID ,
    ISNULL(@RelationshipID_3PDM, 11),
    DebtorContact.ContactID ,
    1 ,
    1,
    @CurrentSessionID , 
    GETDATE()
FROM 
    tblContact RepContact WITH ( NOLOCK )
    INNER JOIN tblContact DebtorContact WITH(NOLOCK) ON RepContact.Z_REF3 = DebtorContact.ContactID
    INNER JOIN tblAccount_Contact AC WITH ( NOLOCK ) ON AC.ContactID = DebtorContact.ContactID
    INNER JOIN tblAccount A WITH ( NOLOCK ) ON AC.AccountID = A.AccountID
WHERE 
    RepContact.LoadID = @LoadID 
    AND DebtorContact.LoadID = @LoadID
    AND RepContact.ContactTypeID = @ContactTypeID_3PDM
    AND RepContact.StatusID = 1 
    AND DebtorContact.StatusID = 1

UPDATE AC
    SET AC.Primary_Related_ContactID = RepContact.ContactID,
    AC.Primary_Related_Contact_ActiveTS = TPC.Rep_Start_Dte
FROM 
    tblAccount_Contact AC WITH ( NOLOCK )
    INNER JOIN @ThirdPartyContacts TPC ON AC.ContactID = TPC.DebtrakContactID
    INNER JOIN tblContact RepContact WITH ( NOLOCK ) ON RepContact.Z_REF3 = AC.ContactID        
WHERE 
    RepContact.LoadID = @LoadID 
    AND RepContact.LoadID = @LoadID
    AND RepContact.ContactTypeID = @ContactTypeID_3PDM
    AND AC.RelationshipID = 1 -- PrimaryDebtor
    AND RepContact.StatusID = 1     

-- Insert phone numbers for 3PDM contacts

--INSERT INTO tblMigrationLog
--        ( MigrationLogTS ,
--          MigrationLogMessage,
--          LoadID
--        )
--VALUES  ( SYSDATETIME() ,
--          'Insert phone numbers for 3PDM contacts',
--          @LoadID
--        );

--INSERT INTO tblContactDetail WITH ( ROWLOCK )
--        ( ContactID ,
--          ContactDetailTypeID ,
--          ContactDetail ,
--          StatusID ,
--          CreateID ,
--          CreateSessionID ,
--          CreateTS ,
--          LoadID
--        )
--        SELECT
--            RepContact.ContactID ,
--            @ContactDetailTypeID_Mobile ,
--            X.Value ,
--            1 ,
--            1 ,
--            @CurrentSessionID ,
--            GETDATE() ,
--            @LoadID
--        FROM
--            @ThirdPartyContacts TPC
--            INNER JOIN tblContact C WITH ( NOLOCK ) ON TPC.DebtrakContactID = C.ContactID
--            INNER JOIN tblContact RepContact WITH ( NOLOCK ) ON RepContact.Z_REF3 = C.ContactID
--            CROSS APPLY dbo.fnPipeDelimitedStringIntoTable(TPC.Rep_Home_Ph) X
--        WHERE
--            C.LoadID = @LoadID

---------------------- begin related party ----------------------------

-- Insert related party contacts
INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Related Party Contacts',
          @LoadID
        );

-- Begin Mod 01/11/25 (Moved RPA.ZID from REF3 to REF2)
INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,  
		  FirstName,
          LastName ,
          DOB ,          
          IsTemporaryPassword ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2 ,
          Z_REF3
        )
        SELECT DISTINCT
                @LoadID ,
                0 , --IsUser
                IIF(A_B_N IS NULL, 1, 0) ,	--IsPerson
			    IIF(A_B_N IS NULL, @ContactTypeID_Individual, @ContactTypeID_Entity) ,	--ContactTypeID 
				First_Name,
                Last_Name ,
                Date_Of_Birth ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                Extended_Debt_Code ,
                ZID ,
                NULL
        FROM    RC_RELATEDPARTY
      
INSERT  INTO  tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS
        )
SELECT 
    A.AccountID ,
    C.ContactID ,
	CASE 
		WHEN (RPA.Related_Party_Type_Code = 'GTR') THEN @RelationshipID_Guarantor
		WHEN (RPA.Related_Party_Type_Code = 'ACH') THEN @RelationshipID_AdditionalCardHolder
		WHEN (RPA.Related_Party_Type_Code = 'SPO') THEN @RelationshipID_Spouse
		WHEN (RPA.Related_Party_Type_Code = 'REF') THEN @RelationshipID_Reference
		WHEN (RPA.Related_Party_Type_Code = 'SOL') THEN @RelationshipID_Solicitor
		WHEN (RPA.Related_Party_Type_Code = 'WIT') THEN @RelationshipID_Witness 

		ELSE @RelationshipID_Other -- Other                 
	END ,
    1 ,
    1,
    @CurrentSessionID , 
    GETDATE()
FROM 
    tblContact C WITH ( NOLOCK )
	INNER JOIN RC_RELATEDPARTY RPA ON C.Z_REF2 = RPA.ZID
    INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = RPA.Extended_Debt_Code
        WHERE
            A.LoadID = @LoadID

-- End Mod 01/11/25


-- Insert phone numbers for related party contacts

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Insert phone numbers for related party contacts',
          @LoadID
        );

INSERT INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Mobile ,
            X.Value ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_RELATEDPARTY RPA
-- Begin mod 01/11/25
--           INNER JOIN tblContact C WITH ( NOLOCK ) ON RPA.ZID = C.Z_REF3
            INNER JOIN tblContact C WITH ( NOLOCK ) ON RPA.ZID = C.Z_REF2
-- End mod 01/11/25
            CROSS APPLY dbo.fnPipeDelimitedStringIntoTable(RPA.Phone_No) X
        WHERE
            LEN(RPA.Phone_No) > 0 and C.LoadID = @LoadID
---------------------- end related party ------------------------------

-- Begin Mod 01/11/25
PRINT 'Inserting Insurance Contacts'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Insurance Contacts',
          @LoadID
        );

INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,  
		  FirstName,
          LastName ,
          DOB ,          
          IsTemporaryPassword ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2 ,
          Z_REF3
        )
		-- Insured Party
        SELECT DISTINCT
                @LoadID ,
                0 , --IsUser
                1 ,	--IsPerson
			    @ContactTypeID_Insured,	--ContactTypeID 
				Insureds_First_Name,
                Insureds_Company_Surname ,
                NULL ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                Full_Debt_Code ,
                CAST(Short_Debt_Code AS NVARCHAR) + '*INS' ,
                NULL
        FROM    RC_ACCOUNT_EXTRACT 
		WHERE   Insureds_Company_Surname IS NOT NULL
 
UNION ALL
        -- Insured Driver
        SELECT
                @LoadID ,
                0 , --IsUser
                1 ,	--IsPerson
			    @ContactTypeID_InsuredDriver,	--ContactTypeID 
				NULL,
                I.InsuredDriverName ,
                NULL ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*IPD' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.InsuredDriverName IS NOT NULL

UNION ALL
        -- Third Party Driver
        SELECT
                @LoadID ,
                0 , --IsUser
                1 ,	--IsPerson
			    @ContactTypeID_ThirdPartyDriver,	--ContactTypeID 
				NULL,
                I.TPD_Name ,
                NULL ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*TPD' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.TPD_Name IS NOT NULL

UNION ALL

        -- Third Party Owner
        SELECT
                @LoadID ,
                0 , --IsUser
                1 ,	--IsPerson
			    @ContactTypeID_ThirdPartyOwner,	--ContactTypeID 
				I.TPO_Firstname,
                I.TPO_Surname ,
                NULL ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*TPO' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.TPO_Surname IS NOT NULL

UNION ALL
		-- Third Party Insurer
        SELECT
                @LoadID ,
                0 , --IsUser
                1 ,	--IsPerson
			    @ContactTypeID_ThirdPartyInsurer,	--ContactTypeID 
				NULL,
                ISNULL(I.InsurerNameonDocument,I.InsurerCode) ,
                NULL ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*TPI' ,
                NULL
        FROM    RC_DRINSURANCE I
		WHERE   I.InsurerCode IS NOT NULL or I.InsurerNameOnDocument IS NOT NULL


-- create insured representative (after insured contact was created)
INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,  
		  FirstName,
          LastName ,
          DOB ,          
          IsTemporaryPassword ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2 ,
          Z_REF3
        )

        SELECT
                @LoadID ,
                0 , --IsUser
                1 ,	--IsPerson
			    @ContactTypeID_InsuredRep,	--ContactTypeID 
				NULL,
                I.RepName ,
                NULL ,                
                1 ,                                
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1 ,
                FullDebtCode ,
                CAST(ShortDebtCode AS NVARCHAR) + '*IPR' ,
                C.ContactID -- link to insured party
        FROM    RC_DRINSURANCE I
		JOIN TBLCONTACT C ON C.Z_REF2 = CAST(ShortDebtCode AS NVARCHAR) + '*INS'
		WHERE   I.RepName IS NOT NULL
		AND I.RepContactFirstYN = 'Y'

-- account/contact relationship

INSERT  INTO  tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS
        )
		-- Insured Party
		SELECT 
			A.AccountID ,
			C.ContactID ,
			@RelationshipID_Insured ,
			1 ,
			1,
			@CurrentSessionID , 
			GETDATE()
			FROM 
				tblContact C WITH ( NOLOCK )
				INNER JOIN RC_ACCOUNT_EXTRACT RCA ON C.Z_REF = RCA.Full_Debt_Code
				INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = RCA.Full_Debt_Code
			WHERE
				A.LoadID = @LoadID
			AND RCA.Insureds_Company_Surname IS NOT NULL AND C.Z_REF2 = CAST(RCA.Short_Debt_Code as nvarchar) + '*INS'

UNION ALL
		-- Insured Representative
		SELECT 
			A.AccountID ,
			C.ContactID ,
			@RelationshipID_InsuredRep,
			1 ,
			1,
			@CurrentSessionID , 
			GETDATE()
			FROM 
				tblContact C WITH ( NOLOCK )
				INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = C.Z_REF
				INNER JOIN RC_DRINSURANCE I ON I.FullDebtCode = C.Z_REF
			WHERE
				A.LoadID = @LoadID
			AND C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar) + '*IPR'

UNION ALL
		-- Insured Driver
		SELECT 
			A.AccountID ,
			C.ContactID ,
			@RelationshipID_InsuredDriver , 
			1 ,
			1,
			@CurrentSessionID , 
			GETDATE()
			FROM 
				tblContact C WITH ( NOLOCK )
				INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = C.Z_REF
				INNER JOIN RC_DRINSURANCE I ON I.FullDebtCode = C.Z_REF
			WHERE
				A.LoadID = @LoadID
			AND C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar) + '*IPD'


UNION ALL

		-- Third Party Driver
		SELECT 
			A.AccountID ,
			C.ContactID ,
			@RelationshipID_ThirdPartyDriver, 
			1 ,
			1,
			@CurrentSessionID , 
			GETDATE()
			FROM 
				tblContact C WITH ( NOLOCK )
				INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = C.Z_REF
				INNER JOIN RC_DRINSURANCE I ON I.FullDebtCode = C.Z_REF
			WHERE
				A.LoadID = @LoadID
			AND C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar) + '*TPD'

UNION ALL

		-- Third Party Owner
		SELECT 
			A.AccountID ,
			C.ContactID ,
			@RelationshipID_ThirdPartyOwner,
			1 ,
			1,
			@CurrentSessionID , 
			GETDATE()
			FROM 
				tblContact C WITH ( NOLOCK )
				INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = C.Z_REF
				INNER JOIN RC_DRINSURANCE I ON I.FullDebtCode = C.Z_REF
			WHERE
				A.LoadID = @LoadID
			AND C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar) + '*TPO'

UNION ALL

		-- Third Party Insurer
		SELECT 
			A.AccountID ,
			C.ContactID ,
			@RelationshipID_ThirdPartyInsurer,
			1 ,
			1,
			@CurrentSessionID , 
			GETDATE()
			FROM 
				tblContact C WITH ( NOLOCK )
				INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = C.Z_REF
				INNER JOIN RC_DRINSURANCE I ON I.FullDebtCode = C.Z_REF
			WHERE
				A.LoadID = @LoadID
			AND C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar) + '*TPI'


PRINT 'Insert phone numbers for Insurance contacts'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Insert phone numbers for Insurance contacts',
          @LoadID
        );

INSERT INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
		-- Insured party (mobile)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Mobile ,
            RCA.Plaint_Ph_M ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_ACCOUNT_EXTRACT RCA
            INNER JOIN tblContact C WITH ( NOLOCK ) ON RCA.Full_Debt_Code = C.Z_REF
        WHERE
            LEN(RCA.Plaint_Ph_M) > 0 and C.LoadID = @LoadID
			AND RCA.Insureds_Company_Surname IS NOT NULL AND C.Z_REF2 = CAST(RCA.Short_Debt_Code AS nvarchar) + '*INS'

UNION ALL
        -- Insured party (home ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Home ,
            RCA.Plaint_Phone_H ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_ACCOUNT_EXTRACT RCA
            INNER JOIN tblContact C WITH ( NOLOCK ) ON RCA.Full_Debt_Code = C.Z_REF
        WHERE
            LEN(RCA.Plaint_Phone_H) > 0 and C.LoadID = @LoadID
			AND RCA.Insureds_Company_Surname IS NOT NULL AND C.Z_REF2 = CAST(RCA.Short_Debt_Code AS nvarchar) + '*INS'

UNION ALL

        -- Insured party (work ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Work ,
            RCA.Pl_Phone_W ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_ACCOUNT_EXTRACT RCA
            INNER JOIN tblContact C WITH ( NOLOCK ) ON RCA.Full_Debt_Code = C.Z_REF
        WHERE
            LEN(RCA.Pl_Phone_W) > 0 and C.LoadID = @LoadID
			AND RCA.Insureds_Company_Surname IS NOT NULL AND C.Z_REF2 = CAST(RCA.Short_Debt_Code AS nvarchar) + '*INS'

UNION ALL
        -- Insured Representative (all phone nos)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Mobile ,
            X.Value ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
            CROSS APPLY dbo.fnPipeDelimitedStringIntoTable(I.RepPhoneNo) X
        WHERE
            LEN(I.RepPhoneNo) > 0 and C.LoadID = @LoadID
			AND I.RepName IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*IPR'

UNION ALL
        -- Insured Driver (Home ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Home ,
            I.InsuredDriverHomePhome ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.InsuredDriverHomePhome) > 0 and C.LoadID = @LoadID
			AND I.InsuredDriverName IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*IPD'

UNION ALL

        -- Insured Driver (work ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Work ,
            I.InsuredDriverWorkPhone ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.InsuredDriverWorkPhone) > 0 and C.LoadID = @LoadID
			AND I.InsuredDriverName IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*IPD'

UNION ALL
        -- Third Party Driver (Home ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Home ,
            I.TPD_HomePhone ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPD_HomePhone) > 0 and C.LoadID = @LoadID
			AND I.TPD_Name IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPD'

UNION ALL

        -- Third Party Driver (work ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Work ,
            I.TPD_WorkPhone ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPD_WorkPhone) > 0 and C.LoadID = @LoadID
			AND I.TPD_Name IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPD'

UNION ALL

        -- Third Party Driver (mobile)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Work ,
            I.TPD_Mobile ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPD_Mobile) > 0 and C.LoadID = @LoadID
			AND I.TPD_Name IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPD'


UNION ALL
        -- Third Party Owner (Home ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Home ,
            I.TPO_HomePhone ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPO_HomePhone) > 0 and C.LoadID = @LoadID
			AND I.TPO_Surname IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPO'

UNION ALL

        -- Third Party Owner (work ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Work ,
            I.TPO_WorkPhone ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.TPO_WorkPhone) > 0 and C.LoadID = @LoadID
			AND I.TPO_Surname IS NOT NULL AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPO'

UNION ALL
        -- Third Party Insurer (Home ph)
        SELECT
            C.ContactID ,
            @ContactDetailTypeID_Home ,
            I.InsurerPhoneNo ,
            1 ,
            1 ,
            @CurrentSessionID ,
            GETDATE() ,
            @LoadID
        FROM
            RC_DRINSURANCE I
            INNER JOIN tblContact C WITH ( NOLOCK ) ON I.FullDebtCode = C.Z_REF
          WHERE
            LEN(I.InsurerPhoneNo) > 0 and C.LoadID = @LoadID
			AND (I.InsurerNameOnDocument IS NOT NULL OR I.InsurerCode IS NOT NULL) AND C.Z_REF2 = CAST(I.ShortDebtCode AS nvarchar) + '*TPI'

-- End Mod 01/11/25


-- Update Account Name to be the name of the first contact

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Update Account Name to be the name of the first contact',
          @LoadID
        );

UPDATE  A
SET     A.AccountName = X.Name
FROM    tblAccount A
        CROSS APPLY ( SELECT TOP 1
                                ISNULL(C.FirstName + ' ', '') + ISNULL(C.LastName, '') AS [Name]
                      FROM      tblAccount_Contact AC
                                INNER JOIN tblContact C ON AC.ContactID = C.ContactID
                      WHERE     AC.AccountID = A.AccountID
                      ORDER BY  C.ContactID ASC
                    ) X
WHERE   LoadID = @LoadID


PRINT SYSDATETIME()
PRINT 'Finished INSERT into tblAccount_Contact. Creating contact details (phone).'

INSERT  INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Mobile ,
                X.Value ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_DEBTOR RCC
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = RCC.Debtor_Code
                CROSS APPLY dbo.fnPipeDelimitedStringIntoTable(RCC.Phone_Number) X
        WHERE   C.LoadID = @LoadID
    

PRINT SYSDATETIME()
PRINT 'Finished INSERT into tblAccount_Contact. Creating contact details (email).'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished INSERT into tblAccount_Contact. Creating contact details (email).',
          @LoadID
        );

INSERT  INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                X.Value ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_DEBTOR RCC
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = RCC.Debtor_Code
                CROSS APPLY dbo.fnPipeDelimitedStringIntoTable(RCC.Email_Addr) X
        WHERE   C.LoadID = @LoadID
----------------------------- begin related party -----------------------------------------------------
PRINT 'Creating contact details from related party (email).'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating contact details from related party (email).',
          @LoadID
        );

INSERT  INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                RPA.Email_Address ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_RELATEDPARTY RPA
-- Begin mod 01/11/25
--                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF3 = RPA.ZID
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = RPA.ZID
-- End mod 01/11/25
        WHERE   LEN(RPA.Email_Address) > 0 AND C.LoadID = @LoadID
------------------------------end related party -------------------------------------------------------
-- Begin Mod 01/11/25
PRINT 'Creating contact details from Insurance parties (email).'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating contact details from Insurance parties (email).',
          @LoadID
        );

INSERT  INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
		-- Insured party
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                RCA.Plaintiff_Email_Address ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_ACCOUNT_EXTRACT RCA
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(RCA.Short_Debt_Code as nvarchar(10)) + '*INS'
        WHERE   LEN(RCA.Plaintiff_Email_Address) > 0 AND C.LoadID = @LoadID

UNION ALL
        -- Insured rep
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                I.RepEmail ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*IPR'
        WHERE   (LEN(I.RepEmail) > 0 and I.RepContactFirstYN = 'Y') AND C.LoadID = @LoadID


UNION ALL

        -- Insured Driver
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                I.InsuredDriverEmail ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*IPD'
        WHERE   LEN(I.InsuredDriverEmail) > 0 AND C.LoadID = @LoadID


UNION ALL

        -- Third Party Driver
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                I.TPD_Email ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*TPD'
        WHERE   LEN(I.TPD_Email) > 0 AND C.LoadID = @LoadID


UNION ALL

        -- Third Party Owner
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                I.TPO_Email ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*TPO'
        WHERE   LEN(I.TPO_Email) > 0 AND C.LoadID = @LoadID

UNION ALL

        -- Third Party Insurer
        SELECT
	DISTINCT    C.ContactID ,
                @ContactDetailTypeID_Email ,
                I.InsurerEmail ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    RC_DRINSURANCE I
                INNER JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = CAST(I.ShortDebtCode as nvarchar(10)) + '*TPI'
        WHERE   LEN(I.InsurerEmail) > 0 AND C.LoadID = @LoadID


-- End Mod 01/11/25

--INSERT ContactDetailAudit records

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'INSERT ContactDetailAudit records.',
          @LoadID
        );


INSERT  INTO tblContactDetailAudit WITH ( ROWLOCK )
        ( ContactDetailID ,
          AuditTS ,
          ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    CD.ContactDetailID ,
                GETDATE() ,
                CD.ContactID ,
                CD.ContactDetailTypeID ,
                CD.ContactDetail ,
                1 ,
                1 ,
                @CurrentSessionID ,
                CD.CreateTS ,
                @LoadID
        FROM    tblContactDetail CD
        WHERE   CD.LoadID = @LoadID
                AND CD.StatusID = 1



PRINT SYSDATETIME()
PRINT 'Finished INSERT Phone Numbers. Creating address.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished INSERT Phone Numbers. Creating address.',
          @LoadID
        );

INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @AddressTypeID_Home ,
                1 ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Street_Address, 1) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RCC.Street_Address, 2) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RCC.Street_Address, 3) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Street_Address, 5) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Street_Address, 4) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Street_Address, 6) ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DEBTOR RCC ON RCC.Debtor_Code = C.Z_REF2
        WHERE   C.LoadID = @LoadID




INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @AddressTypeID_Mail ,
                1 ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Mailing_Address, 1) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RCC.Mailing_Address, 2) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RCC.Mailing_Address, 3) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Mailing_Address, 5) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Mailing_Address, 4) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Mailing_Address, 6) ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DEBTOR RCC ON RCC.Debtor_Code = C.Z_REF2
        WHERE   C.LoadID = @LoadID

INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @AddressTypeID_Legal ,
                1 ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Legal_Address, 1) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RCC.Legal_Address, 2) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RCC.Legal_Address, 3) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Legal_Address, 5) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Legal_Address, 4) ,
                dbo.fnGetValueByIndexFromPipeString(RCC.Legal_Address, 6) ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DEBTOR RCC ON RCC.Debtor_Code = C.Z_REF2
        WHERE   C.LoadID = @LoadID

--------------------------------- begin related party -----------------------------------------
PRINT 'Creating address from related parties.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating address from related parties.',
          @LoadID
        );

INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @AddressTypeID_Home ,
                1 ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Street_Address, 1) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RPA.Street_Address, 2) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RPA.Street_Address, 3) ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Street_Address, 5) ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Street_Address, 4) ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Street_Address, 6) ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
-- Begin mod 01/11/25
--                INNER JOIN RC_RELATEDPARTY RPA ON RPA.ZID = C.Z_REF3
                INNER JOIN RC_RELATEDPARTY RPA ON RPA.ZID = C.Z_REF2
-- End mod 01/11/25
        WHERE   LEN(RPA.Street_Address) > 0 AND C.LoadID = @LoadID


INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    C.ContactID ,
                @AddressTypeID_Mail ,
                1 ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Mailing_Address, 1) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RPA.Mailing_Address, 2) + CHAR(10) + CHAR(13)
                + dbo.fnGetValueByIndexFromPipeString(RPA.Mailing_Address, 3) ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Mailing_Address, 5) ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Mailing_Address, 4) ,
                dbo.fnGetValueByIndexFromPipeString(RPA.Mailing_Address, 6) ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
-- Begin mod 01/11/25
--                INNER JOIN RC_RELATEDPARTY RPA ON RPA.ZID = C.Z_REF3
                INNER JOIN RC_RELATEDPARTY RPA ON RPA.ZID = C.Z_REF2
-- End mod 01/11/25
        WHERE   LEN(RPA.Mailing_Address) > 0 AND C.LoadID = @LoadID
--------------------------------- end related party -------------------------------------------
-- Begin Mod 01/11/25
PRINT 'Creating addresses from Insurance parties'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating addresses from Insurance parties',
          @LoadID
        );

INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
		-- Insured party
        SELECT DISTINCT 
		        C.ContactID ,
                @AddressTypeID_Mail ,
                1 ,
                ISNULL(RCA.Address_Line1, '') + CHAR(13) + CHAR(10) + ISNULL(RCA.Address_Line2, ''),
                RCA.Pl_State ,
                RCA.Plaint_Suburb ,
                Pl_PCode ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_ACCOUNT_EXTRACT RCA ON CAST(RCA.Short_Debt_Code AS VARCHAR) + '*INS' = C.Z_REF2
        WHERE   LEN(RCA.Address_Line1) > 0 AND C.LoadID = @LoadID

UNION ALL
        -- Insured representative
        SELECT DISTINCT 
		        C.ContactID ,
                @AddressTypeID_Mail ,
                1 ,
                ISNULL(I.REPAddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.RepAddressLine2, ''),
                I.RepState ,
                I.RepSuburb ,
                I.RepPcode ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*IPR' = C.Z_REF2
        WHERE   (LEN(I.RepAddressLine1) > 0 AND I.RepContactFirstYN = 'Y' )AND C.LoadID = @LoadID

UNION ALL
        -- Insured driver
        SELECT DISTINCT 
		        C.ContactID ,
                @AddressTypeID_Mail ,
                1 ,
                ISNULL(I.InsuredDriverAddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.InsuredDriverAddressLine2, ''),
                I.InsuredDriverState ,
                I.InsuredDriverSuburb ,
                I.InsuredDriverPCode ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*IPD' = C.Z_REF2
        WHERE   LEN(I.InsuredDriverAddressLine1) > 0 AND C.LoadID = @LoadID


UNION ALL
        -- Third party driver
        SELECT DISTINCT 
		        C.ContactID ,
                @AddressTypeID_Mail ,
                1 ,
                ISNULL(I.TPD_AddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.TPD_AddressLine2, ''),
                I.TPD_State ,
                I.TPD_Suburb ,
                I.TPD_PCode ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*TPD' = C.Z_REF2
        WHERE   LEN(I.TPD_AddressLine1) > 0 AND C.LoadID = @LoadID


UNION ALL
        -- Third Party owner
        SELECT DISTINCT 
		        C.ContactID ,
                @AddressTypeID_Mail ,
                1 ,
                ISNULL(I.TPO_AddressLine1, '') + CHAR(13) + CHAR(10) + ISNULL(I.TPO_AddressLine2, ''),
                I.TPO_State ,
                I.TPO_Suburb ,
                I.TPO_PCode ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*TPO' = C.Z_REF2
        WHERE   LEN(I.TPO_AddressLine1) > 0 AND C.LoadID = @LoadID

-- End Mod 01/11/25

--Assign StateID

UPDATE  ADR
SET     StateID = S.StateID
FROM    tblAddress ADR WITH ( ROWLOCK )
        LEFT JOIN tblState S WITH ( ROWLOCK ) ON ADR.State = S.StateShort
WHERE   ADR.LoadID = @LoadID
        AND ADR.StateID IS NULL


INSERT  INTO tblAddressAudit WITH ( ROWLOCK )
        ( AddressID ,
          AuditTS ,
          ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          StateID ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT
	DISTINCT    AddressID ,
                GETDATE() ,
                ContactID ,
                AddressTypeID ,
                AddressStatusID ,
                Address ,
                State ,
                StateID ,
                Suburb ,
                Postcode ,
                CountryID ,
                StatusID ,
                CreateID ,
                CreateSessionID ,
                CreateTS ,
                @LoadID
        FROM    tblAddress ADR WITH ( NOLOCK )
        WHERE   ADR.LoadID = @LoadID
                AND ADR.StatusID = 1



--CTE with ContactID and first contact detail
;
WITH    CTE_ContactData
          AS ( SELECT   C.ContactID ,
                        CD_EMAIL.ContactDetailID AS Email_ContactDetailID ,
                        CD_PHONE.ContactDetailID AS Phone_ContactDetailID ,
                        ADR.AddressID AS Address_AddressID
               FROM     tblContact C
                        CROSS APPLY ( SELECT TOP 1
                                                CD.ContactDetailID
                                      FROM      tblContactDetail CD WITH ( NOLOCK )
                                                INNER JOIN tblContactDetailType CDT WITH ( NOLOCK ) ON CD.ContactDetailTypeID = CDT.ContactDetailTypeID
                                      WHERE     CD.ContactID = C.ContactID
                                                AND CDT.SystemContactDetailTypeID = 0 --Email
                                      ORDER BY  CD.ContactDetailID ASC
                                    ) CD_EMAIL
                        CROSS APPLY ( SELECT TOP 1
                                                CD.ContactDetailID
                                      FROM      tblContactDetail CD WITH ( NOLOCK )
                                                INNER JOIN tblContactDetailType CDT WITH ( NOLOCK ) ON CD.ContactDetailTypeID = CDT.ContactDetailTypeID
                                      WHERE     CD.ContactID = C.ContactID
                                                AND CDT.SystemContactDetailTypeID = 1 --Phone
                                      ORDER BY  CD.ContactDetailID ASC
                                    ) CD_PHONE
                        CROSS APPLY ( SELECT TOP 1
                                                ADR.AddressID
                                      FROM      tblAddress ADR WITH ( NOLOCK )
                                      WHERE     ADR.ContactID = C.ContactID
                                                AND ADR.StatusID = 1
                                      ORDER BY  ADR.AddressID ASC
                                    ) ADR
               WHERE    C.LoadID = @LoadID
             )
    UPDATE  C
    SET     C.PrimaryEmail_ContactDetailID = CCD.Email_ContactDetailID ,
            C.PrimaryPhone_ContactDetailID = CCD.Phone_ContactDetailID ,
            C.Primary_AddressID = CCD.Address_AddressID
    FROM    tblContact C WITH ( ROWLOCK )
            INNER JOIN CTE_ContactData CCD ON CCD.ContactID = C.ContactID

DECLARE @OneSecAgo DATETIME = DATEADD(S, -1, GETDATE())
DECLARE @Now DATETIME = GETDATE()

PRINT SYSDATETIME()
PRINT 'Adding Result Code (Time on Account Outcome)'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Adding Result Code (Time on Account Outcome)',
          @LoadID
        );

INSERT  INTO tblTimeOnAccount
        ( ContactID ,
          AccountID ,
          SessionID ,
          TimeOnAccount ,
          AccountOpened ,
          AccountClosed
        )
        SELECT  1 ,
                A.AccountID ,
                @CurrentSessionID ,
                '1900-01-01 00:00:1.000' ,   -- 1 sec counting from 1900-01-01 00:00:00.000
                @OneSecAgo ,
                @Now
        FROM    tblAccount A WITH ( NOLOCK )
                INNER JOIN RC_ACCOUNT_EXTRACT RC WITH ( NOLOCK ) ON A.AccountNumberClient = RC.Full_Debt_Code
        WHERE   A.LoadID = @LoadID
                AND A.StatusID = 1

INSERT  INTO tblTimeOnAccount_Outcome
        ( TimeOnAccountID ,
          OutcomeID
        )
        SELECT  TOA.TimeOnAccountID ,
                O.OutcomeID
        FROM    tblTimeOnAccount TOA WITH ( NOLOCK )
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON TOA.AccountID = A.AccountID
                INNER JOIN RC_ACCOUNT_EXTRACT RC WITH ( NOLOCK ) ON A.AccountNumberClient = RC.Full_Debt_Code
                INNER JOIN tblOutcome O WITH ( NOLOCK ) ON O.OutcomeCode = RC.Result_Code
        WHERE   A.LoadID = @LoadID
                AND ISNULL(RC.Result_Code, '') <> ''
                AND A.StatusID = 1




PRINT SYSDATETIME()
PRINT 'Inserting payments and bank transactions.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting payments and bank transactions.',
          @LoadID
        );

INSERT  INTO tblBankTransaction WITH ( ROWLOCK )
        ( BankTransaction ,
          BankTransactionDescription ,
          BankTransactionReference ,
          BankTransactionDate ,
          BankTransactionMethodID ,
          BankedTo_BankAccountID ,
          CurrencyID ,
          ChequeNumber ,
          FromBSB ,
          ChequeClearanceDate ,
          CurrencyRate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID ,
          Z_REF
        )
        SELECT DISTINCT
                ISNULL(P.Payment_Amount, 0) ,
                P.Payment_Description ,
                P.Full_Reference_Details ,
                P.Effective_Date ,
                1 , --BankTransactionMethodID, to run via mapping table
                @BankAccountID_DefaultHost ,
                1 , -- AUD, to run via mapping table
                P.Cheque_No ,
                P.BSB_Code ,
                P.Date_Cleared ,
                1.0 ,
                1 ,
                @CurrentSessionID ,
                P.Date_Time_Entered , --GETDATE() ,
                1 ,
                @LoadID ,
                P.Transaction_No
        FROM    RC_PAYMENTS P
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON P.Debt_Code = A.AccountNumberClient
        WHERE   A.LoadID = @LoadID

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
                P.Comm_Amt ,
                NULL ,
                NULL ,
                NULL ,
                ISNULL(OM.DebtrakContactID, 1) ,
                @CurrentSessionID ,
                P.Date_Time_Entered , -- GETDATE() ,
                1 ,
                @LoadID ,
                IIF(P.Rev_Code IS NULL, 0, 1),
				P.AllocatedPrincipal,
				P.AllocatedOverpayment,
				P.AllocatedCost,
                P.ZID, -- Payment Key
                REPLACE(REPLACE(REPLACE(P.Z_REF, CHAR(13), ''), CHAR(10), ''), ' ', '') -- Invoice No

        FROM    RC_PAYMENTS P
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON P.Debt_Code = A.AccountNumberClient
                INNER JOIN tblBankTransaction BT WITH ( NOLOCK ) ON bt.Z_REF = P.Transaction_No
                LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = P.Payment_Operator
        WHERE   A.LoadID = @LoadID
                AND BT.StatusID = 1
                AND BT.LoadID = @LoadID
			

PRINT SYSDATETIME()
PRINT 'Inserting costs.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting costs.',
          @LoadID
        );


DECLARE @CostsToInsert TABLE
    (
      ID INT IDENTITY(1, 1) ,
      AccountNumberClient NVARCHAR(50) ,
      CostTypeID INT ,
      RCField NVARCHAR(50) ,
      Amount DECIMAL(18, 2)
    );
WITH    CTE_COSTS
          AS ( SELECT   [Debtor_Code] ,
                        ISNULL([Chg_ADM], 0) AS ADM ,
                        ISNULL([Chg_IBS], 0) AS IBS ,
                        ISNULL([Chg_IAJ], 0) AS IAJ ,
                        ISNULL([Chg_LET], 0) AS LET ,
                        ISNULL([Chg_POR], 0) AS POR ,
                        ISNULL([Chg_MPL], 0) AS MPL ,
                        ISNULL([Chg_BNK], 0) AS BNK ,
                        ISNULL([Chg_SHR], 0) AS SHR ,
                        ISNULL([Chg_SHN], 0) AS SHN ,
                        ISNULL([Chg_LOC], 0) AS LOC ,
                        ISNULL([Chg_FCA], 0) AS FCA ,
                        ISNULL([Chg_REP], 0) AS REP ,
                        ISNULL([Chg_SEC], 0) AS SEC ,
                        ISNULL([Chg_COU], 0) AS COU ,
                        ISNULL([Chg_PRE], 0) AS PRE ,
                        ISNULL([Chg_SSC], 0) AS SSC ,
                        ISNULL([Chg_ESC], 0) AS ESC ,
                        ISNULL([Chg_BAR], 0) AS BAR ,
                        ISNULL([Chg_CRT], 0) AS CRT ,
                        ISNULL([Chg_SRV], 0) AS SRV ,
                        ISNULL([Chg_ATS], 0) AS ATS ,
                        ISNULL([Chg_ADS], 0) AS ADS ,
                        ISNULL([Chg_KIL], 0) AS KIL ,
                        ISNULL([Chg_CMO], 0) AS CMO ,
                        ISNULL([Chg_HEA], 0) AS HEA ,
                        ISNULL([Chg_AFF], 0) AS AFF ,
                        ISNULL([Chg_OTH], 0) AS OTH ,
                        ISNULL([Chg_COJ], 0) AS COJ ,
                        ISNULL([Chg_ADR], 0) AS ADR ,
                        ISNULL([Chg_ADN], 0) AS ADN ,
                        ISNULL([Chg_BAI], 0) AS BAI ,
                        ISNULL([Chg_REG], 0) AS REG ,
                        ISNULL([Chg_DEBR], 0) AS DEBR ,
                        ISNULL([Chg_DEBW], 0) AS DEBW ,
                        ISNULL([Chg_SERV], 0) AS SERV ,
                        ISNULL([Chg_SUND], 0) AS SUND ,
                        ISNULL([Chg_UIL], 0) AS UIL ,
                        ISNULL([Chg_SCN], 0) AS SCN ,
                        ISNULL([Chg_VLC], 0) AS VLC ,
                        ISNULL([Chg_ILD], 0) AS ILD ,
                        ISNULL([Chg_VLD], 0) AS VLD ,
                        ISNULL([Chg_ILC], 0) AS ILC ,
                        ISNULL([Chg_PHC], 0) AS PHC ,
                        ISNULL([Chg_AHF], 0) AS AHF ,
                        ISNULL([Chg_ICS], 0) AS ICS ,
                        ISNULL([Chg_LIST], 0) AS LIST ,
                        ISNULL([Chg_SHRF], 0) AS SHRF ,
                        ISNULL([Chg_SHRC], 0) AS SHRC ,
                        ISNULL([Chg_SRVI], 0) AS SRVI ,
                        ISNULL([Chg_SRVC], 0) AS SRVC ,
                        ISNULL([Chg_CLC], 0) AS CLC ,
                        ISNULL([Chg_STB], 0) AS STB ,
                        ISNULL([Chg_SEB], 0) AS SEB ,
                        ISNULL([Chg_AUD], 0) AS AUD ,
                        ISNULL([Chg_SCOS], 0) AS SCOS ,
                        ISNULL([Chg_ARC], 0) AS ARC ,
                        ISNULL([Chg_ICL], 0) AS ICL ,
                        ISNULL([Chg_SAP], 0) AS SAP,
						ISNULL([Chg_COL],0) AS COL
               FROM     [dbo].[RC_COSTS_EXTRACT]
                        INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = RC_COSTS_EXTRACT.Debtor_Code
               WHERE    A.LoadID = @LoadID
             )
    INSERT  INTO @CostsToInsert
            ( AccountNumberClient ,
              RCField ,
              Amount
            )
            SELECT  Debtor_Code ,
                    'ADM' AS Field ,
                    ADM AS Value
            FROM    CTE_COSTS
            WHERE   ADM <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'LET' AS Field ,
                    LET AS Value
            FROM    CTE_COSTS
            WHERE   LET <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'POR' AS Field ,
                    POR AS Value
            FROM    CTE_COSTS
            WHERE   POR <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'MPL' AS Field ,
                    MPL AS Value
            FROM    CTE_COSTS
            WHERE   MPL <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'BNK' AS Field ,
                    BNK AS Value
            FROM    CTE_COSTS
            WHERE   BNK <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SHR' AS Field ,
                    SHR AS Value
            FROM    CTE_COSTS
            WHERE   SHR <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SHN' AS Field ,
                    SHN AS Value
            FROM    CTE_COSTS
            WHERE   SHN <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'LOC' AS Field ,
                    LOC AS Value
            FROM    CTE_COSTS
            WHERE   LOC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'FCA' AS Field ,
                    FCA AS Value
            FROM    CTE_COSTS
            WHERE   FCA <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'REP' AS Field ,
                    REP AS Value
            FROM    CTE_COSTS
            WHERE   REP <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SEC' AS Field ,
                    SEC AS Value
            FROM    CTE_COSTS
            WHERE   SEC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'COU' AS Field ,
                    COU AS Value
            FROM    CTE_COSTS
            WHERE   COU <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'PRE' AS Field ,
                    PRE AS Value
            FROM    CTE_COSTS
            WHERE   PRE <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SSC' AS Field ,
                    SSC AS Value
            FROM    CTE_COSTS
            WHERE   SSC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ESC' AS Field ,
                    ESC AS Value
            FROM    CTE_COSTS
            WHERE   ESC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'BAR' AS Field ,
                    BAR AS Value
            FROM    CTE_COSTS
            WHERE   BAR <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'CRT' AS Field ,
                    CRT AS Value
            FROM    CTE_COSTS
            WHERE   CRT <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SRV' AS Field ,
                    SRV AS Value
            FROM    CTE_COSTS
            WHERE   SRV <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ATS' AS Field ,
                    ATS AS Value
            FROM    CTE_COSTS
            WHERE   ATS <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ADS' AS Field ,
                    ADS AS Value
            FROM    CTE_COSTS
            WHERE   ADS <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'KIL' AS Field ,
                    KIL AS Value
            FROM    CTE_COSTS
            WHERE   KIL <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'CMO' AS Field ,
                    CMO AS Value
            FROM    CTE_COSTS
            WHERE   CMO <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'HEA' AS Field ,
                    HEA AS Value
            FROM    CTE_COSTS
            WHERE   HEA <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'AFF' AS Field ,
                    AFF AS Value
            FROM    CTE_COSTS
            WHERE   AFF <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'OTH' AS Field ,
                    OTH AS Value
            FROM    CTE_COSTS
            WHERE   OTH <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'COJ' AS Field ,
                    COJ AS Value
            FROM    CTE_COSTS
            WHERE   COJ <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ADR' AS Field ,
                    ADR AS Value
            FROM    CTE_COSTS
            WHERE   ADR <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ADN' AS Field ,
                    ADN AS Value
            FROM    CTE_COSTS
            WHERE   ADN <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'BAI' AS Field ,
                    BAI AS Value
            FROM    CTE_COSTS
            WHERE   BAI <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'REG' AS Field ,
                    REG AS Value
            FROM    CTE_COSTS
            WHERE   REG <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'DEBR' AS Field ,
                    DEBR AS Value
            FROM    CTE_COSTS
            WHERE   DEBR <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'DEBW' AS Field ,
                    DEBW AS Value
            FROM    CTE_COSTS
            WHERE   DEBW <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SERV' AS Field ,
                    SERV AS Value
            FROM    CTE_COSTS
            WHERE   SERV <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SUND' AS Field ,
                    SUND AS Value
            FROM    CTE_COSTS
            WHERE   SUND <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'UIL' AS Field ,
                    UIL AS Value
            FROM    CTE_COSTS
            WHERE   UIL <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SCN' AS Field ,
                    SCN AS Value
            FROM    CTE_COSTS
            WHERE   SCN <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'VLC' AS Field ,
                    VLC AS Value
            FROM    CTE_COSTS
            WHERE   VLC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ILD' AS Field ,
                    ILD AS Value
            FROM    CTE_COSTS
            WHERE   ILD <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'VLD' AS Field ,
                    VLD AS Value
            FROM    CTE_COSTS
            WHERE   VLD <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ILC' AS Field ,
                    ILC AS Value
            FROM    CTE_COSTS
            WHERE   ILC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'PHC' AS Field ,
                    PHC AS Value
            FROM    CTE_COSTS
            WHERE   PHC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'AHF' AS Field ,
                    AHF AS Value
            FROM    CTE_COSTS
            WHERE   AHF <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ICS' AS Field ,
                    ICS AS Value
            FROM    CTE_COSTS
            WHERE   ICS <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'LIST' AS Field ,
                    LIST AS Value
            FROM    CTE_COSTS
            WHERE   LIST <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SHRF' AS Field ,
                    SHRF AS Value
            FROM    CTE_COSTS
            WHERE   SHRF <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SHRC' AS Field ,
                    SHRC AS Value
            FROM    CTE_COSTS
            WHERE   SHRC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SRVI' AS Field ,
                    SRVI AS Value
            FROM    CTE_COSTS
            WHERE   SRVI <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SRVC' AS Field ,
                    SRVC AS Value
            FROM    CTE_COSTS
            WHERE   SRVC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'CLC' AS Field ,
                    CLC AS Value
            FROM    CTE_COSTS
            WHERE   CLC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'STB' AS Field ,
                    STB AS Value
            FROM    CTE_COSTS
            WHERE   STB <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SEB' AS Field ,
                    SEB AS Value
            FROM    CTE_COSTS
            WHERE   SEB <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'AUD' AS Field ,
                    AUD AS Value
            FROM    CTE_COSTS
            WHERE   AUD <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SCOS' AS Field ,
                    SCOS AS Value
            FROM    CTE_COSTS
            WHERE   SCOS <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ARC' AS Field ,
                    ARC AS Value
            FROM    CTE_COSTS
            WHERE   ARC <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'ICL' AS Field ,
                    ICL AS Value
            FROM    CTE_COSTS
            WHERE   ICL <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'SAP' AS Field ,
                    SAP AS Value
            FROM    CTE_COSTS
            WHERE   SAP <> 0
            UNION ALL
            SELECT  Debtor_Code ,
                    'COL' AS Field ,
                    COL AS Value
            FROM    CTE_COSTS
            WHERE   COL <> 0;

INSERT  INTO tblCost WITH ( ROWLOCK )
        ( AccountID , 
		  CostTypeID,
		  MasterCostID,
          AccountCost ,                    
          CurrencyID ,
          CurrencyRate ,          
          Reversed ,
          ReverseReason ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )

SELECT 
	A.AccountID,
	[@CostTypeMappings].DebtrakCostTypeID,
                CASE
				   WHEN [RCField] = 'COL' THEN 12 
				   ELSE 2
				END,
	[@CostsToInsert].Amount,
	1,
	1.0,
	NULL,
	NULL,
	1,
	1,
	GETDATE(),
	1,
	@LoadID
from @CostsToInsert
INNER JOIN @CostTypeMappings on RCField = SourceValue
INNER JOIN tblAccount A WITH(NOLOCK) ON A.AccountNumberClient = [@CostsToInsert].AccountNumberClient
WHERE A.LoadID = @LoadID


PRINT SYSDATETIME()
PRINT 'Creating allocation records for Principal'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating allocation records for Principal',
          @LoadID
        );

INSERT INTO tblallocation
        (AccountID ,
		PaymentID,
		PrincipalID,
		CostID,
		AllocationTypeID,
		Allocation,
        CreateID ,
        CreateSessionID ,
        CreateTS ,
        StatusID
        )
SELECT
		a.AccountID,
		p.PaymentID,
		pr.PrincipalID,
		NULL,
		1, -- alloc type 'principal'
		p.LUPAllocatedPrincipal,
		1,
		@CurrentSessionID,
		GETDATE(),
		1

FROM tblpayment p
INNER join tblaccount a on a.accountid = p.AccountID
INNER JOIN tblprincipal pr on a.accountid = pr.AccountID
where a.loadid = @LoadID
AND p.LUPAllocatedPrincipal != 0
AND CAST(pr.Z_REF AS NVARCHAR) = CAST(p.Z_REF AS NVARCHAR)

PRINT SYSDATETIME()
PRINT 'Creating allocation records for Overpayments'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating allocation records for Overpayments',
          @LoadID
        );

INSERT INTO tblallocation
        (AccountID ,
		PaymentID,
		PrincipalID,
		CostID,
		AllocationTypeID,
		Allocation,
        CreateID ,
        CreateSessionID ,
        CreateTS ,
        StatusID
        )
SELECT
		a.AccountID,
		p.PaymentID,
		NULL,
		NULL,
		4, -- alloc type 'overpayment'
		p.LUPAllocatedOverpayment,
		1,
		@CurrentSessionID,
		GETDATE(),
		1

FROM tblpayment p
INNER join tblaccount a on a.accountid = p.AccountID
where a.loadid = @LoadID
AND p.LUPAllocatedOverpayment != 0


PRINT SYSDATETIME()
PRINT 'Creating allocation records for Costs'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating allocation records for Costs',
          @LoadID
        );

INSERT INTO tblallocation
        (AccountID ,
		PaymentID,
		PrincipalID,
		CostID,
		AllocationTypeID,
		Allocation,
        CreateID ,
        CreateSessionID ,
        CreateTS ,
        StatusID
        )
SELECT
		a.AccountID,
		p.PaymentID,
		NULL,
		c.CostID,
		2, -- alloc type 'cost'
		p.LUPAllocatedCost,
		1,
		@CurrentSessionID,
		GETDATE(),
		1

from tblpayment p
INNER join tblaccount a on a.accountid = p.AccountID
INNER JOIN tblCost c on a.accountid = c.AccountID
where a.loadid = @LoadID
and p.LUPAllocatedCost != 0


PRINT SYSDATETIME()
PRINT 'Inserting SMS.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting SMS.',
          @LoadID
        );
-- Begin Mod 01/11/25 Contact Counters mods
INSERT  INTO tblSMSOutput WITH ( ROWLOCK )
        ( AccountID ,
          SMSOutputStatusID ,
          Mobile ,
          MessageFrom ,
          MessageContent ,
          DateForSending ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS,
          Z_ID,
		  Z_REF
        )
        SELECT  A.AccountID ,
                IIF(S.Error_Message IS NULL, 2, 5) , --Successful or Error
                S.Mobile_Phone ,
                REPLACE(S.Sms_Source_Tag, ',', '') ,
                S.Message_Text ,
                S.Date_to_Send ,
                1 ,
                ISNULL(OM.DebtrakContactID, 1) ,
                @CurrentSessionID ,
                S.Date_Queued,
			    S.ZID,
				S.Contact_Ref

        FROM    RC_SMS S
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON S.Extended_Debt_Code = A.AccountNumberClient
                LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = S.Operator_Code

        WHERE   A.LoadID = @LoadID

-- Update CorrespondenceHistory

INSERT INTO tblCorrespondenceHistory  WITH ( ROWLOCK )
	(   CorrespondenceId,
		CorrespondenceType,
		CorrespondenceSolicited,
		CorrespondenceTS,
		CorrespondenceStatusID,
		AccountID,
		ContactID,
		StatusID,
		CreateID,
		CreateSessionID,
		CreateTS
	)

		select 
		so.SMSOutputID ,                   -- CorrespondenceID
		'SMS',                             -- CorrespondenceTtype
		IIF(S.Solicited = 'Y',1,0),        -- CorrespondenceSolicited
		so.CreateTS,                       -- CorrespondenceTS
		IIF(S.Error_Message IS NULL, 2, 1),-- CorrespondenceStatusID (2=delivered)
		A.ACCOUNTID,                       -- AccountID
		C.CONTACTID,                       -- ContactID
		so.StatusID,                       -- StatusID
		1,                                 -- CreateID
		@CurrentSessionID,                 -- CreateSessionID
		so.CreateTS                        -- CreateTS

		from RC_SMS S
		join tblaccount A on A.AccountNumberClient = S.Extended_Debt_Code
                join tblcontact C on C.Z_REF2 = S.Contact_Ref
                                                and C.Z_REF = S.Extended_Debt_Code
                                                and C.LoadID = @LoadID
                join tblSMSOutput SO on SO.Z_ID = S.ZID
                                         and SO.AccountID = A.AccountID
                                         and SO.Z_REF = S.Contact_Ref
                                         and SO.CreateSessionID = @CurrentSessionID
		where A.LoadID = @LoadID
                  AND NOT EXISTS (
                                SELECT 1
                                FROM tblCorrespondenceHistory CH WITH ( NOLOCK )
                                WHERE CH.AccountID = A.AccountID
                                  AND CH.CorrespondenceType = 'SMS'
                                  AND CH.CorrespondenceId = SO.SMSOutputID
                  )

-- End Mod 01/11/25


PRINT SYSDATETIME()
PRINT 'Inserting Emails.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Emails.',
          @LoadID
        );

INSERT  INTO tblCommunication
        ( CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID ,
          Z_REF
        )
        SELECT  1 ,
                @CurrentSessionID ,
                E.Queue_Date , --GETDATE(),
                1 ,
                @LoadID ,
                E.Doc_Hist_Code
        FROM    RC_EMAIL_EXTRACT E
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON E.Extended_Debt_Code = A.AccountNumberClient
        WHERE   A.LoadID = @LoadID



-- Begin Mod 01/11/25 Contact Counters mods   
INSERT  INTO tblEmail WITH ( ROWLOCK )
        ( AccountID ,
          CommunicationID ,
          Subject ,
          Email ,
          ToEmailAddress ,
          FromEmailAddress ,
          Attachments_MediaAndDocumentGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID,
		  Z_REF,
		  Z_IDSTR
        )
        SELECT  A.AccountID ,
                Comm.CommunicationID ,
                'Document' ,
                E.Document_Code ,
                E.Email_Addr ,
                '' ,
                NULL ,
                ISNULL(OM.DebtrakContactID, 1) ,
                @CurrentSessionID ,
                E.Queue_Date , 
                IIF(E.Fail_Date IS NULL,1,0),
				E.ZID,
				E.Recip_Key
        FROM    RC_EMAIL_EXTRACT E
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON E.Extended_Debt_Code = A.AccountNumberClient
                INNER JOIN tblCommunication Comm WITH ( NOLOCK ) ON Comm.Z_REF = E.Doc_Hist_Code
                                                           AND Comm.LoadID = @LoadID
                LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = E.Op_code
        WHERE   A.LoadID = @LoadID


-- Update CorrespondenceHistory

INSERT INTO tblCorrespondenceHistory  WITH ( ROWLOCK )
	(   CorrespondenceId,
		CorrespondenceType,
		CorrespondenceSolicited,
		CorrespondenceTS,
		CorrespondenceStatusID,
		AccountID,
		ContactID,
		StatusID,
		CreateID,
		CreateSessionID,
		CreateTS
	)

	SELECT E.EmailID ,                 -- CorrespondenceID
		'Email',                       -- CorrespondenceTtype
		IIF(DH.Solicited = 'Y',1,0),   -- CorrespondenceSolicited
		E.CreateTS,                    -- CorrespondenceTS
		IIF(RCE.Fail_Date IS NULL,2,1),-- CorrespondenceStatusID (2=delivered)
		A.ACCOUNTID,                   -- AccountID
		C.CONTACTID,                   -- ContactID
		E.StatusID,                    -- StatusID
		1,                             -- CreateID
		@CurrentSessionID,             -- SessionID
		E.CreateTS                     -- CreateTS

	FROM RC_EMAIL_EXTRACT RCE
                join tblaccount A on A.AccountNumberClient = RCE.Extended_Debt_Code
                join tblcontact C on C.Z_REF2 = RCE.Recip_Key
                                                and C.Z_REF = RCE.Extended_Debt_Code
                                                and C.LoadID = @LoadID
                join tblEmail E on E.Z_REF = RCE.ZID
                                         and E.AccountID = A.AccountID
                                         and E.Z_IDSTR = RCE.Recip_Key
                                         and E.CreateSessionID = @CurrentSessionID
		JOIN RC_DOCHIST_EXTRACT DH ON RCE.DOC_HIST_CODE = DH.ZID
    WHERE A.LoadID = @LoadID
          AND NOT EXISTS (
                        SELECT 1
                        FROM tblCorrespondenceHistory CH WITH ( NOLOCK )
                        WHERE CH.AccountID = A.AccountID
                          AND CH.CorrespondenceType = 'Email'
                          AND CH.CorrespondenceId = E.EmailID
          )

-- End Mod 01/11/25


PRINT SYSDATETIME()
PRINT 'Inserting Documents.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Documents.',
          @LoadID
        );

INSERT  INTO tblCommunication
        ( CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID ,
          Z_REF ,  --NoteKey
          Z_REF2 --DebtCode
        )
-- Begin Mod 01/11/25 Contact Counters mods		
        SELECT  1 ,
                @CurrentSessionID ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                @LoadID ,
                D.Note_Key ,
                A.AccountNumberClient
        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON D.Extended_Debt_Code = A.AccountNumberClient
        WHERE   A.LoadID = @LoadID
                AND A.StatusID = 1
                AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')

-- End Mod 01/11/25


INSERT  INTO tblCommunication_Contact
        ( CommunicationID ,
          ContactID ,
          CommunicationMethodID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
-- Begin Mod 01/11/25 Contact Counters mods
        SELECT  Comm.CommunicationID ,
                C.ContactID ,
                1 ,  --LETTER
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                @LoadID
        FROM    RC_DOCHIST_EXTRACT D WITH ( NOLOCK )
                INNER JOIN tblCommunication Comm WITH ( NOLOCK ) ON ( Comm.Z_REF = D.Note_Key
                                                                      AND Comm.LoadID = @LoadID
                                                                    )
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON Comm.Z_REF2 = A.AccountNumberClient
                INNER JOIN tblContact C with ( NOLOCK ) ON C.Z_REF2 = D.Multi_Letter_Keys
        WHERE   A.LoadID = @LoadID
                AND Comm.LoadID = @LoadID
                AND A.StatusID = 1
				AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')
-- End Mod 01/11/25


INSERT  INTO tblMetaValue_DocumentGroup
        ( MetaField_DocumentGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_IDSTR
        )
-- Begin Mod 01/11/25 Contact Counters mods
        SELECT  LatestVersion.MetaField_DocumentGroupID ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                D.Note_Key
        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON D.Extended_Debt_Code = A.AccountNumberClient
                INNER JOIN tblDocumentTemplate DT WITH ( NOLOCK ) ON DT.DocumentTemplateCode = D.Document_Code
                CROSS APPLY ( SELECT TOP 1
                                        DocumentTemplateVersionID ,
                                        MetaField_DocumentGroupID
                              FROM      tblDocumentTemplateVersion WITH ( NOLOCK )
                              WHERE     DocumentTemplateID = DT.DocumentTemplateID
                                        AND StatusID = 1
                              ORDER BY  DocumentTemplateVersionID DESC
                            ) LatestVersion
        WHERE   A.LoadID = @LoadID
                AND A.StatusID = 1
				AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')

-- End Mod 01/11/25



INSERT  INTO tblDocument WITH ( ROWLOCK )
        ( AccountID ,
          Document ,
          DocumentTemplateID ,
          DocumentTemplateVersionID ,
          MetaValue_DocumentGroupID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_IDSTR
        )
-- Begin Mod 01/11/25 Contact Counters mods
        SELECT  A.AccountID ,
                D.Document_Code ,
                DT.DocumentTemplateID,
                LatestVersion.DocumentTemplateVersionID ,
                MVG.MetaValue_DocumentGroupID ,
                ISNULL(OM.DebtrakContactID, 1) ,
                @CurrentSessionID ,
                GETDATE() ,
                IIF(D.Date_De_Queued is null,1,0) ,
                D.Note_Key

        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON D.Extended_Debt_Code = A.AccountNumberClient
                INNER JOIN tblDocumentTemplate DT WITH ( NOLOCK ) ON DT.DocumentTemplateCode = D.Document_Code
                CROSS APPLY ( SELECT TOP 1
                                        DocumentTemplateVersionID ,
                                        MetaField_DocumentGroupID
                              FROM      tblDocumentTemplateVersion WITH ( NOLOCK )
                              WHERE     DocumentTemplateID = DT.DocumentTemplateID
                                        AND StatusID = 1
                              ORDER BY  DocumentTemplateVersionID DESC
                            ) LatestVersion
                INNER JOIN tblMetaValue_DocumentGroup MVG WITH ( NOLOCK ) ON MVG.Z_IDSTR = D.Note_Key
                LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = D.Operator_Code
        WHERE   A.LoadID = @LoadID
                AND A.StatusID = 1
				AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')



INSERT  INTO tblLetter WITH ( ROWLOCK )
        ( AccountID ,
          CommunicationID ,
          DocumentID ,
          Letter ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          PrintedSuccess ,
          PrintedTS ,
          PrintStatusID,
		  ErrorReason,
		  Z_REF
        )
        SELECT  A.AccountID ,
                Comm.CommunicationID ,
                Doc.DocumentID ,
                D.Document_Code ,
                ISNULL(OM.DebtrakContactID, 1) ,
                @CurrentSessionID ,
                D.Date_Queued ,
                IIF(D.Date_De_Queued is null,1,0) ,
                IIF(D.Date_De_Queued is null,1,0) ,
                D.Date_Printed ,
                IIF(D.Date_De_Queued is null,3,0), --3=Success
				D.Skip_Reason,
				D.ZID
        FROM    RC_DOCHIST_EXTRACT D
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON D.Extended_Debt_Code = A.AccountNumberClient
                INNER JOIN tblCommunication Comm WITH ( NOLOCK ) ON Comm.Z_REF = D.Note_Key
                INNER JOIN tblDocument Doc WITH ( NOLOCK ) ON Doc.Z_IDSTR = D.Note_Key
                LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = D.Operator_Code
        WHERE   A.LoadID = @LoadID
				AND (D.Doc_Link_Via IS NULL OR D.Doc_Link_Via!= 'H')


-- Update CorrespondenceHistory

INSERT INTO tblCorrespondenceHistory  WITH ( ROWLOCK )
		(   CorrespondenceId,
			CorrespondenceType,
			CorrespondenceSolicited,
			CorrespondenceTS,
			CorrespondenceStatusID,
			AccountID,
			ContactID,
			StatusID,
			CreateID,
			CreateSessionID,
			CreateTS
		)

		SELECT 
				L.LetterID ,                       -- CorrespondenceID
				'Letter',                          -- CorrespondenceTtype
				IIF(DH.Solicited = 'Y',1,0),       -- CorrespondenceSolicited
				L.CreateTS,                        --CorrespondenceTS
				IIF(DH.Date_De_Queued is null,2,1),-- CorrespondenceStatusID (2=delivered)
				A.ACCOUNTID,                       -- AccountID
				C.CONTACTID,                       -- ContactID
				L.StatusID,                        -- StatusID
				1,                                 -- CreateID
				@CurrentSessionID,                 -- SessionID
				L.CreateTS                         -- CreateTS

		FROM RC_DOCHIST_EXTRACT DH
				join tblaccount A on A.AccountNumberClient = DH.Extended_Debt_Code
				join tblcontact C on C.Z_REF2 = DH.Multi_Letter_keys
				join tblLetter L on L.Z_REF = DH.ZID

        WHERE   A.LoadID = @LoadID
				AND (DH.Doc_Link_Via IS NULL OR DH.Doc_Link_Via!= 'H')

-- End Mod 01/11/25

PRINT SYSDATETIME()
PRINT 'Inserting notes.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Notes.',
          @LoadID
        );

INSERT  INTO tblEntry WITH ( ROWLOCK )
        ( EntryTypeID ,
          EntryStatusID ,
          AccountID ,
          [Entry] ,
          EntryDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  -1 ,
                1 ,
                A.AccountID ,
                N.Text ,
                N.Date_Entered ,
                ISNULL(OM.DebtrakContactID, 1) ,
                @CurrentSessionID ,
                N.Date_Entered ,  --GETDATE() ,
                1 ,
                @LoadID
        FROM    RC_NOTES_EXTRACT N
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = N.Extended_Debt_Code
                LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = N.Operator
        WHERE   A.LoadID = @LoadID



PRINT SYSDATETIME()
PRINT 'Inserting Treatment (as Notes).'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Treatment.',
          @LoadID
        );

INSERT  INTO tblEntry WITH ( ROWLOCK )
        ( EntryTypeID ,
          EntryStatusID ,
          AccountID ,
          [Entry] ,
          EntryDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  ISNULL(@EntryTypeID_Treatment, -1) ,
                1 ,
                A.AccountID ,
                CONCAT(T.Treatment_Step, ' - ', T.Treatment_Type, ' - ', T.Treatment_Result_Code, ' - ',
                       T.Treatment_Result, ' - ', T.Treatment_Code, ' - ', T.Treatment_Description) ,
                T.Treatment_Date ,
                1 ,
                @CurrentSessionID ,
                T.Treatment_Date ,  --GETDATE() ,
                1 ,
                @LoadID
        FROM    RC_TREATMENT T
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = T.Full_Debt_Code
        WHERE   A.LoadID = @LoadID



PRINT SYSDATETIME()
PRINT 'Inserting Result Codes (as Notes).'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Result Codes (as Notes).',
          @LoadID
        );

INSERT  INTO tblEntry WITH ( ROWLOCK )
        ( EntryTypeID ,
          EntryStatusID ,
          AccountID ,
          [Entry] ,
          EntryDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  ISNULL(@EntryTypeID_Result, -1) ,
                1 ,
                A.AccountID ,
                CONCAT('Result: ', O.OutcomeCode, ' - ', O.Outcome) ,
                RC.Result_date ,
                1 ,
                @CurrentSessionID ,
                RC.Result_date ,
                1 ,
                @LoadID
        FROM    RC_ACCOUNT_EXTRACT RC
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = RC.Full_Debt_Code
                INNER JOIN tblOutcome O WITH ( NOLOCK ) ON O.OutcomeCode = RC.Result_Code
        WHERE   A.LoadID = @LoadID
                AND A.StatusID = 1
                AND ISNULL(RC.Result_Code, '') <> ''
                


PRINT SYSDATETIME()
PRINT 'Inserting POI.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting POI.',
          @LoadID
        );

INSERT  INTO tblProofOfIdentity
        ( AccountID ,
          ProofOfIdentityTS ,
          Type ,
          POICompleted ,
          NoAnswerBusy ,
          LeftMessage ,
          WrongNumber ,
          DisconnectedNumber ,
          LeftNumberOnVoicemail ,
          NoMessageLeft ,
          CustomerTerminatedCall ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  A.AccountID ,
                POI.POI_Date ,
                POI.Type ,
                POI.POI_Completed ,
                POI.No_Answer_Busy ,
                POI.Left_Message ,
                POI.Wrong_Number ,
                POI.Disconnected_Number ,
                POI.Left_Number_On_Voicemail ,
                POI.No_Message_Left ,
                POI.Customer_Terminated_Call ,
                1 ,
                @CurrentSessionID ,
                POI.POI_Date , --GETDATE(),
                1 ,
                @LoadID
        FROM    RC_POI POI WITH ( NOLOCK )
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = POI.Extended_Debt_Code
        WHERE   A.LoadID = @LoadID


PRINT SYSDATETIME()
PRINT 'Inserting DebtContacts.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting DebtContacts.',
          @LoadID
        );

-- Begin mod 01/11/25 contact counters
INSERT  INTO tblDebtContact WITH ( ROWLOCK )
        ( [AccountID] ,
          [ContactID] ,
          [DebtContactsTS] ,
          [Type] ,
          [Phone] ,
          [Outcome] ,
          [LetterAddress] ,
          [DocumentRefNo] ,
          [DatePrinted] ,
          [PaymentCode] ,
          [DateSenttoClient] ,
          [SmsOutcome] ,
          [PoiKey] ,
          [LetterName] ,
          [DateDequeued] ,
          [DateReturned] ,
          [MultiRecipientKey] ,
          [LetterTotalOutstanding] ,
          [SMSKey] ,
          [RequestCallDeletionDate] ,
          [RequestCallDeletionOperator] ,
          [EmailAddress] ,
          --[Solicited] ,
          [SenttoClient] ,
          [WorkdeskEmailKey] ,
          [AkEmailKey] ,
          [ActivityReportSent] ,
          [CreateID] ,
          [CreateSessionID] ,
          [CreateTS] ,
          [StatusID]
        )
        SELECT  A.AccountID ,
                C.ContactID ,
                DC.[Date] ,
                DC.[Type] ,
                DC.[Phone] ,
                DC.[Outcome] ,
                DC.[Letter_Address] ,
                DC.[Document_Ref_No] ,
                DC.[Date_Printed] ,
                DC.[Payment_Code] ,
                DC.[Date_Sent_to_Client] ,
                DC.[Sms_Outcome] ,
                DC.[Poi_Key] ,
                DC.[Letter_Name] ,
                DC.[Date_De_queued] ,
                DC.[Date_Returned] ,
                DC.[Multi_Recipient_Key] ,
                DC.[Letter_Total_Outstanding] ,
                DC.[SMS_Key] [int] ,
                DC.[Request_Call_Deletion_Date] ,
                DC.[Request_Call_Deletion_Operator] ,
                DC.[Email_Address] ,
               -- DC.[Solicited] ,
                DC.[Sent_to_Client] ,
                DC.[Workdesk_Email_Key] ,
                DC.[Ak_Email_Key] ,
                DC.[Activity_Report_Sent] ,
                1 ,
                @CurrentSessionID ,
                GETDATE() ,
                1
        FROM    RC_DEBT_CONTACTS DC
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = DC.Extended_Debt_Code
                LEFT JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = DC.Multi_Recipient_Key
        WHERE   A.LoadID = @LoadID

INSERT  INTO tblCallHistory
        ( CallDataSourceID ,
          SequenceNumber ,
          DebtrakAccountID ,
          DiallerLogin ,
          CallStartDateTime ,
          CallEndDateTime ,
          CallWrapDateTime ,
          AgentDisposition ,
          SwitchDisposition ,
          CallTypeId ,
          CreateTS ,
          StatusID ,
          AgentDispositionDesc ,
          SwitchDispositionDesc ,
          CommunicationID,
		  Z_REF
        )
        SELECT  1 , --CallDataSourceID	
                NULL , --,SequenceNumber	
                A.AccountID ,--,DebtrakAccountID	
                NULL , --,DiallerLogin	
                DC.Date ,--,CallStartDateTime	
                NULL ,--,CallEndDateTime	
                NULL ,--,CallWrapDateTime	
                NULL , --,AgentDisposition	
                NULL , --,SwitchDisposition	
                NULL ,--,CallTypeId	    
                DC.Date ,--,CreateTS	
                1 ,--,StatusID	
                NULL ,--,AgentDispositionDesc	
                NULL ,--,SwitchDispositionDesc	
                NULL,--,CommunicationID	
				DC.DebtContactID -- Z_REF
        FROM    RC_DEBT_CONTACTS DC
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = DC.Extended_Debt_Code
                LEFT JOIN tblContact C WITH ( NOLOCK ) ON C.Z_REF2 = DC.Multi_Recipient_Key
        WHERE   A.LoadID = @LoadID
		AND		DC.Type IN ('I','O','V') -- Only inbound/outboun calls and IVR

-- Update CorrespondenceHistory

INSERT INTO tblCorrespondenceHistory  WITH ( ROWLOCK )
			(   CorrespondenceId,
				CorrespondenceType,
				CorrespondenceSolicited,
				CorrespondenceTS,
				CorrespondenceStatusID,
				AccountID,
				ContactID,
				StatusID,
				CreateID,
				CreateSessionID,
				CreateTS
			)

			SELECT CH.CallHistoryID ,             -- CorrespondenceID
				IIF(DC.Type = 'V','IVR','Phone'), -- CorrespondenceTtype
				IIF(DC.Solicited = 'Y',1,0),      -- CorrespondenceSolicited
				CH.CreateTS,                      -- CorrespondenceTS
				1,                                -- CorrespondenceStatusID
				A.ACCOUNTID,                      -- AccountID
				C.CONTACTID,                      -- ContactID
				CH.statusid,                      -- StatusID
				1,                                -- CreateID
				@CurrentSessionID,                -- SessionID
				CH.CreateTS                       -- CreateTS

				from RC_DEBT_CONTACTS DC
					join tblaccount A on A.AccountNumberClient = DC.Extended_Debt_Code
                                        join tblcontact C on C.Z_REF2 = DC.Multi_Recipient_Key
                                                                        and C.Z_REF = DC.Extended_Debt_Code
                                                                        and C.LoadID = @LoadID
                                        join tblCallHistory CH on CH.Z_REF = DC.DebtContactID
                                                                        and CH.DebtrakAccountID = A.AccountID
				WHERE A.LOADID = @LoadID 
                                AND DC.Type in ('O','I','V')
                                AND NOT EXISTS (
                                        SELECT 1
                                        FROM tblCorrespondenceHistory CHIST WITH ( NOLOCK )
                                        WHERE CHIST.AccountID = A.AccountID
                                          AND CHIST.CorrespondenceType = IIF(DC.Type = 'V','IVR','Phone')
                                          AND CHIST.CorrespondenceId = CH.CallHistoryID
                                )

-- End Mod 01/11/25

UPDATE  A
SET     LUPLastPhoneContactDate = DC.DebtContactsTS ,
        LUPLastPhoneDebtorDate = DC.DebtContactsTS
FROM    tblAccount A
        INNER JOIN tblDebtContact DC ON A.AccountID = DC.AccountID
WHERE   DC.StatusID = 1
        AND A.StatusID = 1
--  AND DC.Phone IS NOT NULL            -- any contact, not just phone, client requirement
        AND A.LoadID = @LoadID


PRINT SYSDATETIME()
PRINT 'Inserting Statements (as historic Invoices).'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Statements (as historic Invoices).',
          @LoadID
        );

INSERT  INTO tblInvoice WITH ( ROWLOCK )
        ( EntityID ,
          AccountID ,
          InvoiceDesc ,
          IssueDate ,
          InvoiceFromDate ,
          InvoiceToDate ,
          PaymentToSelection ,
          InvoiceTotal ,
          CreateTS ,
          CreateID ,
          CreateSessionID ,
          StatusID ,
          InvoiceRef ,
          Reversed
        )
        SELECT  @EntityID ,
                A.AccountID ,
                S.Particulars ,
                S.[Date] ,
                NULL ,
                NULL ,
                '2' , --Direct
                NULL , --RC TO Provide Field
                S.[Date] , --GETDATE(),
                1 ,
                @CurrentSessionID ,
                1 ,
                S.Tran_Key ,
                0
        FROM    RC_STATEMENT S
                LEFT JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = S.Extended_Debt_Code
        WHERE   A.LoadID = @LoadID







PRINT SYSDATETIME()
PRINT 'Creating Arrangement from DEALS'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating Arrangement from DEALS',
          @LoadID
        );


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
          LoadID
        )
        SELECT  A.AccountID ,		
                DL.Deal_Amount ,
                1 ,
                @CurrentSessionID ,
                ISNULL(@ArrangementTypeID_Deal, 1) ,
                DL.No_Instalments ,
                DL.First_Instalment ,
                DL.Last_Instal_Date ,
                1 ,--BankTransactionMethodID, to run via mapping table
                DL.Total_Paid ,
                DL.Total_Outstanding ,
                DL.Bal_At_Tme_Of_Offer ,
                DL.Date_of_Deal , --GETDATE(),
                1 ,
                CASE 
                    WHEN (DL.Deal_Amount - ISNULL(DL.Total_Paid,0) <= 0) THEN 2 --Successful
                    WHEN ((DL.Deal_Amount - ISNULL(DL.Total_Paid,0) > 0) AND DATEDIFF(DAY, DL.Due_Date, GETDATE()) < 0) THEN 4 -- Failed
                    ELSE 1 -- In Progress                    
                END ,  
                NULL ,  --Deal is an Ad-hoc arrangement, no frequency4
                @LoadID
        FROM    [RC_DEAL] DL
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = DL.Extended_Debt_Code
        WHERE   A.LoadID = @LoadID



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
        WHERE   LoadID = @LoadID
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

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating ArrangementSchedule from Inserted Deals',
          @LoadID
        );





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
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = DL.Extended_Debt_Code
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


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating Arrangement from Arrangements',
          @LoadID
        );


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
          LoadID
        )
        SELECT  A.AccountID ,		
                AR.Agreed_Amount ,
                1 ,
                @CurrentSessionID ,
                0,
                AR.No_Instalments ,
                AR.First_Instal_Date ,
                AR.Last_Instal_Date ,
                1 ,--BankTransactionMethodID, to run via mapping table
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
                CASE
				   WHEN AR.Frequency = 'W' THEN 2
				   WHEN AR.Frequency = 'F' THEN 3
				   WHEN AR.Frequency = 'M' THEN 4
				   WHEN AR.Frequency = 'BM' THEN 7
				   WHEN AR.Frequency = 'Q' THEN 12
				   WHEN AR.Frequency = 'Y' THEN 5
				   ELSE 0
				END, 
                @LoadID
        FROM    [RC_ARRANGEMENT] AR
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = AR.Extended_Debt_Code
        WHERE   A.LoadID = @LoadID


	PRINT SYSDATETIME()
PRINT 'Creating ArrangementSchedule from Inserted Arrangements'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Creating ArrangementSchedule from Inserted Arrangements',
          @LoadID
        );


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
        WHERE   LoadID = @LoadID
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

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Updating ArrangementSchedule table',
          @LoadID
        );


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
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberClient = AR.Extended_Debt_Code
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

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          ' Insert Account Status History (tblWorkflowLineAudit)',
          @LoadID
        );

PRINT SYSDATETIME()
PRINT 'Inserting Account Status History.'


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
        WHERE   LoadID = @LoadID
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
        WHERE Full_Debt_Code = (SELECT TOP 1 AccountNumberClient FROM tblAccount WHERE AccountID = @currAccountID)

        
        INSERT INTO tblWorkflowLineAudit(AccountID, WorkflowLineID, AccountStatusID, AuditTS, CreateID, CreateSessionID, StatusID, LoadID)        
        SELECT 
            @currAccountID, 
            @currWorkflowLineID,
            AsMap.AccountStatusID,
            X.TimeStamp,      -- Default conversion
            1,
            @CurrentSessionID,
            1,
            @LoadID
        FROM dbo.fnGetAccountStatusHistoryFromPipeData(@currAccountStatusHistoryString, @currAccountStatusTimestameString, @currOperatorString) X 
        CROSS APPLY ( SELECT TOP 1
                                        AccountStatusID
                              FROM      tblAccountStatus
                              WHERE     AccountStatus = X.AccountStatus
                            ) AsMap
        LEFT JOIN @OperatorContactMappings OM ON OM.SourceValue = X.Operator

        SET @currAccountID = NULL
        SET @currWorkflowLineID = NULL
        SET @currAccountStatusHistoryString = NULL
        SET @currAccountStatusTimestameString = NULL
        SET @currOperatorString = NULL


        SET @loopIndex = @loopIndex + 1

    END


PRINT SYSDATETIME()
PRINT 'Finished Account Status History.'


INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished Account Status History',
          @LoadID
        );
-- Begin Mod 01/11/25
PRINT SYSDATETIME()
PRINT 'Inserting Insurance Details.'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Inserting Insurance Details',
          @LoadID
        );

-- Incident Address
INSERT  INTO tblAddress WITH ( ROWLOCK )
        ( ContactID ,
          AddressTypeID ,
          AddressStatusID ,
          Address ,
          State ,
          Suburb ,
          Postcode ,
          CountryID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID,
		  Z_REF
        )
		
        SELECT  
		        C.ContactID ,
                @AddressTypeID_Home ,
                1 ,
                I.IncidentPlace,
                I.IncidentState ,
                I.IncidentSuburb ,
                I.IncidentPCode ,
                @DefaultCountryID ,
                1 ,
                1 ,
                @CurrentSessionID ,
                C.CreateTS ,
                @LoadID,
				CAST(I.ShortDebtCode AS VARCHAR) + '*INC' -- flag address as 'incident' to distinguish it from the insured's
        FROM    tblContact C WITH ( NOLOCK )
                INNER JOIN RC_DRINSURANCE I ON CAST(I.ShortDebtCode AS VARCHAR) + '*INS' = C.Z_REF2
        WHERE   LEN(I.IncidentPlace) > 0 AND C.LoadID = @LoadID


-- Incident Details
INSERT  INTO tblAccountIncident WITH ( ROWLOCK )
        ( AccountID ,
          IncidentTypeID ,
          IncidentDate ,
          IncidentDescription ,
          AddressID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID,
          Z_DB
        )
		SELECT
	        A.AccountID,
	        CASE 
	           WHEN AE.Cause_Description LIKE '%THEFT%' THEN 2  -- Theft
	           WHEN AE.Cause_Description LIKE '%FIRE%' THEN 3   -- Fire
	           WHEN AE.Cause_Description LIKE '%WATER%' THEN 4  -- Flood
	           WHEN AE.Cause_Description LIKE '%DAMAGE%' THEN 8 -- Damage
	        ELSE 9 -- Property
	        END,
	        I.IncidentDate,
	        LEFT(I.IncidentDescription, 500),
	        Addr.AddressID,
	        1,
	        @CurrentSessionID,
	        GETDATE(),
	        1,
	        @LoadID,
			I.FullDebtCode

        FROM tblAccount A
	        JOIN RC_ACCOUNT_EXTRACT AE ON AE.Full_Debt_Code = A.AccountNumberClient
	        JOIN RC_DRINSURANCE I ON I.FullDebtCode = A.AccountNumberClient 
	        JOIN tblAddress Addr ON Addr.z_ref = CAST(AE.Short_Debt_Code AS VARCHAR) + '*INC' 
        WHERE A.loadid = @LoadID
        AND Addr.loadid = @LoadID
        

-- Account Insurance Details
INSERT  INTO tblAccountInsurance WITH ( ROWLOCK )
        ( AccountIncidentID ,
		  InsuranceRefTypeID,
          InsurantContactID,
          PolicyNumber,
          ReferenceToRego,
          InsuredItems,
          ClaimNumber,
		  LiabilityAdmitted,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID,
          Z_ID
        )
	SELECT 
		AI.AccountIncidentID,
		2, -- Client Insurant
		C.ContactID,
		I.InsuredPropertyPolicyNo,
		I.InsuredPropertyRegistration,
		I.InsuredPropertyDescription,
		I.InsurerClaimNo,
		0, -- Liability admitted (no)
		1,
		@CurrentSessionID,
		GETDATE(),
		1,
		@LoadID,
      I.FullDebtCode
	FROM tblaccount A
		JOIN tblAccountIncident AI ON AI.AccountID = A.AccountID
		JOIN RC_DRINSURANCE I ON A.AccountNumberClient = I.FullDebtCode
		JOIN tblContact C ON C.Z_REF2 = CAST(I.ShortDebtCode AS VARCHAR) + '*INS'
	WHERE A.loadID = @loadID
	AND C.LoadID = @LoadID

-- Incident Witness details
INSERT  INTO tblIncidentWitness WITH ( ROWLOCK )
        ( AccountIncidentID ,
          ContactID,
          Remark,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )

	SELECT 
		AI.AccountIncidentID,
		C.ContactID,
		LEFT(RP.Witness_Statement, 500),
		1,
		@CurrentSessionID,
		GETDATE(),
		1,
		@LoadID

	FROM tblaccount A
		JOIN tblAccountIncident AI ON AI.AccountID = A.AccountID
		JOIN RC_RELATEDPARTY RP ON RP.Extended_Debt_Code = A.AccountNumberClient 
		JOIN tblContact C ON C.Z_REF2 = RP.ZID
	WHERE A.loadID = @loadID
	AND C.LoadID = @LoadID


-- Incident Police details
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
    AI.AccountIncidentID,
    0, 
    DR.Police_Report,
    DR.Police_Station,
    1,
    @CurrentSessionID,
    GETDATE(),
    1,
    @LoadID
FROM tblaccount A
    JOIN tblAccountIncident AI ON AI.AccountID = A.AccountID
    JOIN RC_DEBTOR DR ON DR.Debt_Code = A.AccountNumberClient
WHERE A.loadID = @loadID
  AND LEN(DR.Police_Report) > 0

-- Incident Police Details (pipe separated police reports/stations)

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
    JOIN RC_DEBTOR DR ON DR.Debt_Code = A.AccountNumberClient
WHERE A.LoadID = @LoadID
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
                @CurrentSessionID,
                GETDATE(),
                1,
                @LoadID
            FROM dbo.fnSplitTextIntoTable(@PoliceReports, '|') policeReport
                LEFT JOIN dbo.fnSplitTextIntoTable(@PoliceStations, '|') policeStation ON policeReport.[LineNo] = policeStation.[LineNo]
        END

        SET @OPR_LoopIndex += 1
    END
END

PRINT SYSDATETIME()
PRINT 'Calculating contact counters'

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Calculating contact counters',
          @LoadID
        );

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
WHERE A.LoadID = @loadID;

SET @loopIndex = 1
SELECT  @maxIndex = MAX(ID) FROM @InsertedAccountContacts

WHILE ( @loopIndex <= @maxIndex )
    BEGIN
        SELECT  @currAccountID = AccountID, @currContactID = ContactID
        FROM    @InsertedAccountContacts
        WHERE   ID = @loopIndex

        EXEC dbo.spAccount_Contact_CorrespondenceRecalculate
            @User_ContactID = 1,
            @User_SessionID = @CurrentSessionID,
            @AccountID = @currAccountID,
            @ContactID = @currContactID;

        SET @loopIndex = @loopIndex + 1

        -- Print message every 1000 iterations
        IF @loopIndex % 1000 = 0
        BEGIN
            PRINT CAST(SYSDATETIME() AS VARCHAR(19)) + ' Processing ' + CAST(@loopIndex AS VARCHAR(10))
        END

    END


-- End Mod 01/11/25


PRINT SYSDATETIME()
PRINT 'Calculating account totals.'


SET @loopIndex = 1
SELECT  @maxIndex = MAX(ID)
FROM    @InsertedAccounts

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Calculating account totals (' + CAST(@maxIndex as VARCHAR(10)) + ' accounts)',
          @LoadID
        );


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

INSERT INTO tblMigrationLog
        ( MigrationLogTS ,
          MigrationLogMessage,
          LoadID
        )
VALUES  ( SYSDATETIME() ,
          'Finished account totals',
          @LoadID
        );


--PRINT 'Calculating Payment allocations'


--DECLARE @InsertedPayments TABLE
--    (
--      ID INT IDENTITY(1, 1) ,
--      PaymentID INT ,
--      PaymentAmount DECIMAL(18, 2)
--    )

--INSERT  INTO @InsertedPayments
--        ( PaymentID ,
--          PaymentAmount
--        )
--        SELECT  PaymentID ,
--                ISNULL(Payment, 0)
--        FROM    tblPayment WITH ( NOLOCK )
--        WHERE   LoadID = @LoadID
--                AND StatusID = 1
--				order by PaymentID



--SET @loopIndex = 1
--SELECT  @maxIndex = MAX(ID)
--FROM    @InsertedPayments


--INSERT INTO tblMigrationLog
--        ( MigrationLogTS ,
--          MigrationLogMessage,
--          LoadID
--        )
--VALUES  ( SYSDATETIME() ,
--          'Calculating allocations (' + CAST(@maxIndex as VARCHAR(10)) + ' payments)',
--          @LoadID
--        );


--DECLARE @currPaymentID INT
--DECLARE @currPaymentAmt DECIMAL(18, 2)

--WHILE ( @loopIndex <= @maxIndex )
--    BEGIN
--        SELECT  @currPaymentID = PaymentID ,
--                @currPaymentAmt = PaymentAmount
--        FROM    @InsertedPayments
--        WHERE   ID = @loopIndex


--        EXEC [dbo].[spPaymentAllocationReallocateAuto] @User_ContactID = 1, @PaymentID = @currPaymentID,
--            @PaymentAmt = @currPaymentAmt, @DeletePrevious = 1, @CalculateAccountTotals = 0, @PayToPrincipalID = NULL,
--            @ExcludePrincipalID = NULL, @ApplyOverpayments = NULL, @ExcludeCost = NULL, @CostIDs = NULL,
--            @PrincipalIDs = NULL, @User_SessionID = 1

--        SET @loopIndex = @loopIndex + 1

--        -- Print message every 1000 iterations
--        IF @loopIndex % 1000 = 0
--        BEGIN
--            PRINT CAST(SYSDATETIME() AS NVARCHAR(19)) + ' Processing ' + CAST(@loopIndex AS NVARCHAR(10))
--        END

--    END


----EXEC spMaintenance_PaymentAllocationAndCommissionUpdate

--PRINT SYSDATETIME()
--PRINT 'Finished allocations.'

--INSERT INTO tblMigrationLog
--        ( MigrationLogTS ,
--          MigrationLogMessage,
--          LoadID
--        )
--VALUES  ( SYSDATETIME() ,
--          'Finished allocations',
--          @LoadID
--        );



--INSERT INTO tblMigrationLog
--        ( MigrationLogTS ,
--          MigrationLogMessage,
--          LoadID
--        )
--VALUES  ( SYSDATETIME() ,
--          'Finished Payment Allocations',
--          @LoadID
--        );



UPDATE  tblLoad
SET     ModifyTS = GETDATE()
WHERE   LoadID = @LoadID



