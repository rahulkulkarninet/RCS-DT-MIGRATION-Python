-- 02/0925 Contact Counters mods

USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_EMAIL_EXTRACT]    Script Date: 8/09/2025 11:11:29 AM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_EMAIL_EXTRACT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_EMAIL_EXTRACT]
GO

/****** Object:  Table [dbo].[RC_EMAIL_EXTRACT]    Script Date: 8/09/2025 11:11:29 AM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_EMAIL_EXTRACT](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](500) NULL,
	[Client_Group] [nvarchar](500) NULL,
	[Document_Code] [nvarchar](500) NULL,
	[Type] [nvarchar](500) NULL,
	[Queue_Date] [datetime] NULL,
	[Debtor_Code] [nvarchar](100) NULL,
	[Doc_Hist_Code] [int] NULL,
	[Op_code] [nvarchar](50) NULL,
	[Email_Addr] [nvarchar](50) NULL,
	[Sent_Date] [datetime] NULL,
	[Fail_Date] [datetime] NULL,
	[Fail_Reas] [nvarchar](100) NULL,
	[State] [nvarchar](500) NULL,
	[ZID] [int] NULL
) ON [PRIMARY]
GO


