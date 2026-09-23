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
								{{LoadID}},
								REPLACE(invoiceNumber.Line,'''','')

                        FROM    dbo.fnSplitTextIntoTable(@InvoiceAmounts, '|') invoiceAmount
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoiceDates, '|') invoiceDate ON invoiceAmount.[LineNo] = invoiceDate.[LineNo]
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoicePaid, '|') invoicePaid ON invoiceAmount.[LineNo] = invoicePaid.[LineNo]
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoiceBalance, '|') invoiceBalance ON invoiceAmount.[LineNo] = invoiceBalance.[LineNo]
                                LEFT JOIN dbo.fnSplitTextIntoTable(@InvoiceNumber, '|') invoiceNumber ON invoiceAmount.[LineNo] = invoiceNumber.[LineNo]
                 --

            END
