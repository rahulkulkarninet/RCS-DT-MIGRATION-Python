-- 02/09/25 Contact Counters mods
USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_SMS]    Script Date: 8/09/2025 10:52:14 AM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_SMS]') AND type in (N'U'))
DROP TABLE [dbo].[RC_SMS]
GO

/****** Object:  Table [dbo].[RC_SMS]    Script Date: 8/09/2025 10:52:14 AM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_SMS](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](50) NULL,
	[Client_Group] [nvarchar](50) NULL,
	[Date_to_Send] [datetime] NULL,
	[Date_Queued] [datetime] NULL,
	[Date_Sent] [datetime] NULL,
	[Debtor_Code] [nvarchar](50) NULL,
	[Mobile_Phone] [nvarchar](50) NULL,
	[Message_Text] [nvarchar](500) NULL,
	[Type] [nvarchar](250) NULL,
	[Staggered] [nvarchar](250) NULL,
	[Operator_Code] [nvarchar](50) NULL,
	[Error_Message] [nvarchar](50) NULL,
	[Related_Party_Code] [nvarchar](20) NULL,
	[Solicited] [nvarchar](50) NULL,
	[Sms_Scheduled_Date] [datetime] NULL,
	[Req_ID] [nvarchar](50) NULL,
	[State] [nvarchar](50) NULL,
	[Doc_Hist_Code] [nvarchar](1) NULL,
	[Sms_Provider] [nvarchar](50) NULL,
	[Zone_Sent_Date] [datetime] NULL,
	[Sms_Sent_To_Representative] [nvarchar](1) NULL,
	[Contact_Ref] [nvarchar](20) NULL,
	[Sms_Source_Tag] [nvarchar](50) NULL,
	[ZID] [nvarchar](50) NULL
) ON [PRIMARY]
GO


