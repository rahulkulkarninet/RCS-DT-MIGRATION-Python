USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_DEAL]    Script Date: 7/04/2025 2:08:47 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_DEAL]') AND type in (N'U'))
DROP TABLE [dbo].[RC_DEAL]
GO

/****** Object:  Table [dbo].[RC_DEAL]    Script Date: 7/04/2025 2:08:47 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_DEAL](
	[Extended_Debt_Code] [int] NOT NULL,
	[Client_Code] [nvarchar](500) NOT NULL,
	[Client_Group] [nvarchar](500) NOT NULL,
	[Date_of_Deal] [datetime] NOT NULL,
	[Due_Date] [datetime] NOT NULL,
	[Deal_Amount] [decimal](18, 2) NOT NULL,
	[Op_Code] [nvarchar](50) NOT NULL,
	[Deal_Type] [nvarchar](50) NOT NULL,
	[No_Instalments] [int] NOT NULL,
	[First_Instalment] [datetime] NOT NULL,
	[Last_Instal_Date] [datetime] NOT NULL,
	[Payment_Dates] [nvarchar](1000) NULL,
	[Payment_Amounts] [nvarchar](1000) NULL,
	[Payment_Method] [nvarchar](10) NOT NULL,
	[SMS_Reminder] [nvarchar](1) NOT NULL,
	[SMS_Mobile] [nvarchar](100) NULL,
	[Total_Paid] [decimal](18, 2) NOT NULL,
	[Total_Outstanding] [decimal](18, 2) NOT NULL,
	[DD_BSB_Code] [nvarchar](100) NULL,
	[DD_Account_Number] [nvarchar](100) NULL,
	[DD_Account_Name] [nvarchar](500) NULL,
	[CC_Card_Number] [nvarchar](100) NULL,
	[CC_Expiry_Month] [nvarchar](100) NULL,
	[CC_Expiry_Year] [nvarchar](100) NULL,
	[CC_Card_Name] [nvarchar](100) NULL,
	[CC_Token] [nvarchar](100) NULL,
	[Bal_At_Tme_Of_Offer] [float] NOT NULL,
	[Instalment_Date] [nvarchar](max) NOT NULL,
	[Instalment_Amt] [nvarchar](max) NOT NULL,
	[Payment_Date] [nvarchar](max) NULL,
	[Payment_Amount] [nvarchar](max) NULL,
	[Payment_Number] [nvarchar](max) NULL,
	[Email_Address] [nvarchar](500) NULL,
	[Email_Reminder_Flag] [nvarchar](1) NULL,
	[Status] [nvarchar](50) NOT NULL,
	[Direct_Debit_Selected] [nvarchar](1000) NULL,
	[Direct_Deposit_Selected] [nvarchar](1000) NULL,
	[Transferred_To_Client_Date] [datetime] NULL,
	[Payment_Allocation_Amt] [nvarchar](max) NULL,
	[Payment_Date_Cleared] [nvarchar](max) NULL,
	[No_Of_Time_End_Date_Extended] [int] NULL,
	[De_Inckpi] [nvarchar](500) NULL,
	[SMS_Sent_History] [nvarchar](max) NULL,
	[Ccpay] [nvarchar](500) NULL,
	[Confirmation_Letter] [nvarchar](500) NULL,
	[Client_Status] [nvarchar](100) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


