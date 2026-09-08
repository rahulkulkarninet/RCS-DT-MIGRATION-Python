USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_POI]    Script Date: 24/03/2025 8:24:46 AM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_POI]') AND type in (N'U'))
DROP TABLE [dbo].[RC_POI]
GO

/****** Object:  Table [dbo].[RC_POI]    Script Date: 24/03/2025 8:24:46 AM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_POI](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](50) NULL,
	[Client_Group] [nvarchar](50) NULL,
	[POI_Date] [datetime] NULL,
	[User] [nvarchar](50) NULL,
	[Type] [int] NULL,
	[POI_Completed] [int] NULL,
	[No_Answer_busy] [int] NULL,
	[Left_Message] [int] NULL,
	[Wrong_Number] [int] NULL,
	[Disconnected_Number] [int] NULL,
	[Left_Number_On_Voicemail] [int] NULL,
	[No_Message_Left] [int] NULL,
	[Customer_Terminated_Call] [int] NULL,
	[Client_Revealed] [int] NULL,
	[Debtor_Code] [nvarchar] (100) NULL,
	[ZID] [nvarchar] (20) NULL
) ON [PRIMARY]
GO


