
-- 02/09/25 Contact Counters mods

USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_DEBT_CONTACTS]    Script Date: 9/09/2025 10:50:20 AM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_DEBT_CONTACTS]') AND type in (N'U'))
DROP TABLE [dbo].[RC_DEBT_CONTACTS]
GO

/****** Object:  Table [dbo].[RC_DEBT_CONTACTS]    Script Date: 9/09/2025 10:50:20 AM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_DEBT_CONTACTS](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](50) NULL,
	[Client_Group] [nvarchar](50) NULL,
	[Date] [datetime] NULL,
	[Type] [nvarchar](50) NULL,
	[Phone] [nvarchar](50) NULL,
	[Outcome] [nvarchar](50) NULL,
	[Letter_Address] [nvarchar](500) NULL,
	[Document_Ref_No] [int] NULL,
	[Date_Printed] [datetime] NULL,
	[Payment_Code] [nvarchar](100) NULL,
	[Date_Sent_to_Client] [date] NULL,
	[Sms_Outcome] [nvarchar](500) NULL,
	[Poi_Key] [int] NULL,
	[Letter_Name] [nvarchar](500) NULL,
	[Date_De_queued] [datetime] NULL,
	[Date_Returned] [datetime] NULL,
	[Multi_Recipient_Key] [nvarchar](50) NULL,
	[Letter_Total_Outstanding] [decimal](18, 2) NULL,
	[Request_Call_Deletion_Date] [datetime] NULL,
	[Request_Call_Deletion_Time] [nvarchar](100) NULL,
	[Request_Call_Deletion_Operator] [nvarchar](100) NULL,
	[Email_Address] [nvarchar](50) NULL,
	[Sql_Upd] [nvarchar](100) NULL,
	[Solicited] [nvarchar](100) NULL,
	[Sent_to_Client] [datetime] NULL,
	[Workdesk_Email_Key] [nvarchar](100) NULL,
	[Ak_Email_Key] [nvarchar](100) NULL,
	[Activity_Report_Sent] [datetime] NULL,
	[DebtContactID] [nvarchar] (20) NULL
) ON [PRIMARY]
GO


