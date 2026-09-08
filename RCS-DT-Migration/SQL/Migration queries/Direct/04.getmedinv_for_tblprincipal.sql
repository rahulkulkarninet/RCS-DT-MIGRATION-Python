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
                INNER JOIN tblAccount A WITH ( NOLOCK ) ON A.AccountNumberPrevious = MI.Full_Debt_Code
        WHERE   A.AccountNumberPrevious = @InvoicefullDebtCode

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
								{{CurrentSessionID}},
				                CONVERT(DATE, REPLACE(invoiceDate.Line,'''',''), 120), 
								1,
								{{LoadID}},
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
;
