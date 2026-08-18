USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_TREATMENT]    Script Date: 26/03/2025 4:29:50 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_TREATMENT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_TREATMENT]
GO

/****** Object:  Table [dbo].[RC_TREATMENT]    Script Date: 26/03/2025 4:29:50 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_TREATMENT](
	[Full_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](50) NULL,
	[Client_Group] [nvarchar](50) NULL,
	[Short_Debt_Code] [int] NULL,
	[Account_No] [nvarchar](100) NULL,
	[Treatment_Date] [datetime] NULL,
	[Treatment_Code] [nvarchar](50) NULL,
	[Treatment_Description] [nvarchar](500) NULL,
	[Treatment_Step] [int] NULL,
	[Treatment_Type] [nvarchar](50) NULL,
	[Treatment_Result_Code] [nvarchar](50) NULL,
	[Treatment_Result] [nvarchar](50) NULL,
	[ZID] [nvarchar](100) NULL
) ON [PRIMARY]
GO


