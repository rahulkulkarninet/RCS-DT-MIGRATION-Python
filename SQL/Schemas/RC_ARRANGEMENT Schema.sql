USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_ARRANGEMENT]    Script Date: 7/05/2025 4:45:15 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_ARRANGEMENT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_ARRANGEMENT]
GO

/****** Object:  Table [dbo].[RC_ARRANGEMENT]    Script Date: 7/05/2025 4:45:15 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_ARRANGEMENT](
	[Extended_Debt_Code] [int] NOT NULL,
	[Client_Code] [nvarchar](10) NULL,
	[Client_Group] [nvarchar](100) NULL,
	[Arrangement_Date] [datetime] NOT NULL,
	[Agreed_Amount] [decimal](18, 2) NOT NULL,
	[Op_Code] [nvarchar](10) NULL,
	[Arrangement_Type] [nvarchar](10) NULL,
	[No_Instalments] [int] NOT NULL,
	[First_Instal_Date] [datetime] NOT NULL,
	[Last_Instal_Date] [datetime] NOT NULL,
	[Next_Instal_Date] [datetime] NULL,
	[Next_Instal_Amount] [decimal](18, 2) NULL,
	[Frequency] [nvarchar](10) NOT NULL,
	[SMS_Reminder_Flag] [nvarchar](1) NOT NULL,
	[SMS_Mobile] [nvarchar](100) NULL,
	[Total_Paid] [decimal](18, 2) NOT NULL,
	[Total_Outstanding] [decimal](18, 2) NOT NULL,
	[Payment_Method] [nvarchar](10) NULL,
	[DD_BSB_Code] [nvarchar](100) NULL,
	[DD_Account_Number] [nvarchar](20) NULL,
	[DD_Account_Name] [nvarchar](100) NULL,
	[CC_Card_Number] [nvarchar](10) NULL,
	[CC_Expiry_Month] [nvarchar](10) NULL,
	[CC_Expiry_Year] [nvarchar](10) NULL,
	[CC_Card_Name] [nvarchar](100) NULL,
	[CC_Token] [nvarchar](100) NULL,
	[Bal_At_Time_Of_Offer] [float] NOT NULL,
	[Instalment_Date] [nvarchar](max) NOT NULL,
	[Instalment_Amount] [nvarchar](max) NOT NULL,
	[Actual_Amount_Paid] [nvarchar](max) NULL,
	[Payment_Allocation] [nvarchar](max) NULL,
	[Amount_Deferred] [nvarchar](max) NULL,
	[Payment_Number] [nvarchar](max) NULL,
	[Amount_In_Arrears] [nvarchar](max) NULL,
	[Current_Instalment_Amount] [nvarchar](max) NULL,
	[Paid_In_Advance] [nvarchar](max) NULL,
	[Paid_Off_Next_Instalment] [nvarchar](max) NULL,
	[Number_Of_Defaults] [int] NULL,
	[Number_Of_Part_Payments] [int] NULL,
	[End_Of_Month_Offset] [int] NULL,
	[Paid_Off_Overdue] [decimal](18, 2) NULL,
	[Paid_Since_Previous_Instalment] [decimal](18, 2) NULL,
	[Downpayment_Amount] [decimal](18, 2) NULL,
	[Downpayment_Date] [datetime] NULL,
	[Grace_Period] [int] NULL,
	[Review_Date] [datetime] NULL,
	[Allow_Payment_In_Advance] [nvarchar](1) NULL,
	[Direct_Deposit_Set_Date] [datetime] NULL,
	[Direct_Debit_Selected] [nvarchar](100) NULL,
	[Direct_Deposit_Selected_History] [nvarchar](max) NULL,
	[DD_Payment_Dates] [nvarchar](max) NULL,
	[DD_Payment_Amounts] [nvarchar](max) NULL,
	[Status] [nvarchar](100) NULL,
	[Client_Status] [nvarchar](100) NULL,
	[Debtor_Code] [nvarchar](100) NULL,
	[Payment_Number_Since_Previous_Instalment] [nvarchar](2000) NULL,
	[Payment_Amount_Since_Previous_Instalment] [nvarchar](2000) NULL,
	[Rep_Bank_Details_Flag] [nvarchar](1) NULL,
	[Email_Reminder_Flag] [nvarchar](1) NULL,
	[Email_Address] [nvarchar](500) NULL,
	[Transferred_To_Client_Date] [datetime] NULL,
	[Last_SMS_Sent] [nvarchar](2000) NULL,
	[SMS_Sent_History] [nvarchar](max) NULL,
	[CCPAY_Done] [nvarchar](100) NULL,
	[Retry_Payment_Selected] [nvarchar](100) NULL,
	[Rebate_Instalment_Date] [nvarchar](2000) NULL,
	[Rebate_Date_Op] [nvarchar](2000) NULL,
	[Rebate_Change_Date] [nvarchar](2000) NULL,
	[Amend_Date] [nvarchar](2000) NULL,
	[Amend_Operator] [nvarchar](2000) NULL,
	[First_Payment_Manual_Flag] [nvarchar](1) NULL,
	[Confirmation_Letter] [nvarchar](1) NULL,
	[Confirmation_Letter_Type] [nvarchar](100) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


