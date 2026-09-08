USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_DOCHIST_EXTRACT]    Script Date: 8/04/2025 12:35:34 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_DOCHIST_EXTRACT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_DOCHIST_EXTRACT]
GO

/****** Object:  Table [dbo].[RC_DOCHIST_EXTRACT]    Script Date: 8/04/2025 12:35:34 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_DOCHIST_EXTRACT](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](1000) NULL,
	[Client_Group] [nvarchar](1000) NULL,
	[Document_Code] [nvarchar](1000) NULL,
	[Date_Queued] [datetime] NULL,
	[Date_Printed] [datetime] NULL,
	[No_Of_Reprints] [nvarchar](100) NULL,
	[Note_Key] [int] NULL,
	[Date_De_Queued] [datetime] NULL,
	[No_Of_Copies] [nvarchar](100) NULL,
	[Doc_Link_Via] [nvarchar](1000) NULL,
	[Document_Description] [nvarchar](max) NULL,
	[Dh_Status] [nvarchar](1000) NULL,
	[Skip_Reason] [nvarchar](1000) NULL,
	[Multi_Letter_Keys] [nvarchar](100) NULL,
	[Document_Link_Mobile_No] [nvarchar](1000) NULL,
	[Document_Link_Email] [nvarchar](1000) NULL,
	[Doc_Link_Lock_Flag] [nvarchar](1000) NULL,
	[Doc_Link_Date] [datetime] NULL,
	[File_Only_Doc] [nvarchar](1000) NULL,
	[Email_Key] [int] NULL,
	[Sms_Key] [int] NULL,
	[Operator_Code] [nvarchar](1000) NULL,
	[Delivery_Method_Manually_Selected] [nvarchar](1000) NULL,
	[Solicited] [nvarchar](1000) NULL,
	[Rep_Flag] [nvarchar](1000) NULL,
	[Charge_Code] [nvarchar](1000) NULL,
	[ZID] [nvarchar] (100) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


