USE [sqldb-glass-uat]
GO

/****** Object:  Table [dbo].[RC_NOTES_EXTRACT]    Script Date: 5/08/2025 4:43:26 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_NOTES_EXTRACT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_NOTES_EXTRACT]
GO

/****** Object:  Table [dbo].[RC_NOTES_EXTRACT]    Script Date: 5/08/2025 4:43:26 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_NOTES_EXTRACT](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](500) NULL,
	[Client_Group] [nvarchar](500) NULL,
	[Date_Entered] [datetime] NULL,
	[Operator] [nvarchar](500) NULL,
	[Text] [nvarchar](1000) NULL,
	[Action_Code] [nvarchar](500) NULL,
	[Tran_Key] [int] NULL,
	[Source_Id] [tinyint] NULL,
	[Doc_No] [int] NULL,
	[Private_Diary_Note] [nvarchar](1) NULL,
	[Effective_Client_Date] [datetime] NULL,
	[Client_Note] [tinyint] NULL,
	[Transferred_to_Client_Date] [datetime] NULL,
	[Transaction_Transferred_Date] [datetime] NULL,
	[Reconciliation_Transferred_to_Client_Date] [nvarchar](100) NULL,
	[SMS_Key] [int] NULL,
	[ATO_Liability_Flag] [nvarchar](100) NULL,
	[EMAIL_Key] [int] NULL,
	[Treatment_Code] [nvarchar](100) NULL,
	[Chat_ID] [nvarchar](100) NULL,
	[POI_Key] [int] NULL,
	[Date_Transferred_to_Evolve] [nvarchar](100) NULL,
	[ZID] [nvarchar] (100) NULL
) ON [PRIMARY]
GO


