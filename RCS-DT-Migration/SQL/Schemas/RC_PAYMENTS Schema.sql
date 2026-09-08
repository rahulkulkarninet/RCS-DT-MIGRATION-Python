USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_PAYMENTS]    Script Date: 5/08/2025 4:44:10 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_PAYMENTS]') AND type in (N'U'))
DROP TABLE [dbo].[RC_PAYMENTS]
GO

/****** Object:  Table [dbo].[RC_PAYMENTS]    Script Date: 5/08/2025 4:44:10 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_PAYMENTS](
	[Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](100) NULL,
	[Client_Group_Code] [nvarchar](100) NULL,
	[Account_No] [nvarchar](100) NULL,
	[Payment_Code] [nvarchar](500) NULL,
	[Date_Time_Entered] [datetime] NULL,
	[Effective_Date] [datetime] NULL,
	[Debt_Codes] [nvarchar](500) NULL,
	[Payment_Amount] [decimal](18, 2) NULL,
	[Paid_By_Name] [nvarchar](500) NULL,
	[Cheque_No] [nvarchar](500) NULL,
	[BSB_Code] [nvarchar](500) NULL,
	[Account_No_1] [nvarchar](500) NULL,
	[Payment_Method] [nvarchar](500) NULL,
	[Debtor] [nvarchar](500) NULL,
	[Payment_Amount_1] [decimal](18, 2) NULL,
	[Transaction_No] [nvarchar](500) NULL,
	[Receipt_Y_N] [nvarchar](100) NULL,
	[Receipt_Address] [nvarchar](1000) NULL,
	[Credit_Card_Expiry_Date] [nvarchar](100) NULL,
	[Bank_Code] [nvarchar](100) NULL,
	[Bank_Lodgement_No] [nvarchar](100) NULL,
	[Days_Clearance] [nvarchar](100) NULL,
	[Payment_Status] [nvarchar](1000) NULL,
	[Comm_Amt] [decimal](18, 2) NULL,
	[Payment_Type] [nvarchar](100) NULL,
	[Client] [nvarchar](1000) NULL,
	[Debt_Payment_Allocation] [decimal](18, 2) NULL,
	[Agency_Costs_Allocation] [decimal](18, 2) NULL,
	[Date_Cleared] [datetime] NULL,
	[Date_Dishonoured] [datetime] NULL,
	[Payment_Batch_Load_No] [nvarchar](100) NULL,
	[Agt_Chrg] [decimal](18, 2) NULL,
	[Cl_Trans] [nvarchar](100) NULL,
	[Transit_Register] [nvarchar](100) NULL,
	[Cash_Receipt_Number] [nvarchar](100) NULL,
	[Chrg_Code] [nvarchar](100) NULL,
	[Rev_Code] [nvarchar](100) NULL,
	[Reversal_Annotation] [nvarchar](1000) NULL,
	[Payment_Operator] [nvarchar](100) NULL,
	[Payment_deposit_date] [datetime] NULL,
	[Payment_Description] [nvarchar](1000) NULL,
	[Bill_Pay_Source] [nvarchar](100) NULL,
	[Clink_Debt_ID] [nvarchar](max) NULL,
	[Transaction_Keys] [nvarchar](1000) NULL,
	[Transaction_Amounts] [decimal](18, 2) NULL,
	[Settlement_Discount] [decimal](18, 2) NULL,
	[Quick_Books_Code] [nvarchar](100) NULL,
	[Orig_Pay_Ref] [nvarchar](100) NULL,
	[Cba_Reconciliation_File] [nvarchar](100) NULL,
	[Client_Reference_No] [nvarchar](100) NULL,
	[Dr_Method] [nvarchar](100) NULL,
	[Client_Transfer_Date] [datetime] NULL,
	[Overpayment_Unalloc] [nvarchar](100) NULL,
	[Possible_Debts] [nvarchar](1000) NULL,
	[Ovp_Db_Code] [nvarchar](100) NULL,
	[Orig_Amt] [decimal](18, 2) NULL,
	[Pa_Ovpunallocamt_Amounts] [decimal](18, 2) NULL,
	[Payment_App_Code] [nvarchar](100) NULL,
	[Full_Reference_Details] [nvarchar](1000) NULL,
	[Settlement_Date] [datetime] NULL,
	[NTID] [nvarchar](100) NULL,
	[Currency] [nvarchar](100) NULL,
	[PA_Amt] [decimal](18, 2) NULL,
	[EFT_Processed_Flag] [nvarchar](100) NULL,
	[AllocatedPrincipal] [decimal](18, 2) NULL,
	[AllocatedOverpayment] [decimal](18, 2) NULL,
    [AllocatedCost] [decimal](18, 2) NULL,
	[ZID] [integer] NULL,
	[Z_REF] [nvarchar](200) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


