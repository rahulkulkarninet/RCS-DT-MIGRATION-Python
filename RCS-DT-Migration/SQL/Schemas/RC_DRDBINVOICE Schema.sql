USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_DRDBINVOICE]    Script Date: 19/03/2025 12:26:55 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_DRDBINVOICE]') AND type in (N'U'))
DROP TABLE [dbo].[RC_DRDBINVOICE]
GO

/****** Object:  Table [dbo].[RC_DRDBINVOICE]    Script Date: 19/03/2025 12:26:55 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_DRDBINVOICE](
	[Full_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](500) NULL,
	[Client_Group] [nvarchar](500) NULL,
	[Short_Debt_Code] [int] NULL,
	[Account_No] [nvarchar](100) NULL,
	[DRDBINVOICE_Key] [nvarchar](500) NULL,
	[Invoice_Number] [nvarchar](1000) NULL,
	[Invoice_Date] [date] NULL,
	[Entry_Date] [date] NULL,
	[Invoice_Amount] [decimal](18, 2) NULL,
	[Invoice_Costs] [nvarchar](100) NULL,
	[Total_Paid_Amount] [decimal](18, 2) NULL,
	[Outstanding] [decimal](18, 2) NULL,
	[Description] [nvarchar](500) NULL,
	[Date_Paid] [nvarchar](max) NULL,
	[Paid_Amount] [nvarchar](max) NULL,
	[Pay_Tran_Key] [nvarchar](max) NULL,
	[Paid_Status] [nvarchar](max) NULL,
	[Operator_Id] [nvarchar](max) NULL,
	[Control_Flag] [nvarchar](max) NULL,
	[Recall_Date] [nvarchar](max) NULL,
	[Sequence_No] [nvarchar](max) NULL,
	[Inv_Recalled_By] [nvarchar](max) NULL,
	[Inv_Policyno] [nvarchar](max) NULL,
	[Operator_Id2] [nvarchar](max) NULL,
	[Orig_Outstanding_Inv_Bal] [nvarchar](max) NULL
) ON [PRIMARY]
GO


