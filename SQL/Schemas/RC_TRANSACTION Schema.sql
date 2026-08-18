/****** Object:  Table [dbo].[RC_TRANSACTION]    Script Date: 17/08/2026 ******/

IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_TRANSACTION]') AND type in (N'U'))
DROP TABLE [dbo].[RC_TRANSACTION]
GO

/****** Object:  Table [dbo].[RC_TRANSACTION]    Script Date: 17/08/2026 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_TRANSACTION](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](1000) NULL,
	[Client_Group_Code] [nvarchar](1000) NULL,
	[Account_No] [nvarchar](100) NULL,
	[Type] [nvarchar](100) NULL,
	[Eff_Date] [datetime] NULL,
	[Note_Key] [nvarchar](500) NULL,
	[Dtr_Amount] [decimal](18, 2) NULL,
	[Debt_Code] [int] NULL,
	[Payment_No] [int] NULL,
	[Cl_Amount] [decimal](18, 2) NULL,
	[Cl_Code] [nvarchar](1000) NULL,
	[Pay_Tran_No] [nvarchar](500) NULL,
	[Comm_Tran] [nvarchar](500) NULL,
	[Rev_By_Tr] [nvarchar](500) NULL,
	[Rev_Of_Tr] [nvarchar](500) NULL,
	[Nft_Amt] [nvarchar](1000) NULL,
	[Ass_Cl_Tr] [nvarchar](500) NULL,
	[Ass_Ag_Tr] [nvarchar](500) NULL,
	[Cl_GST_Amt] [decimal](18, 2) NULL,
	[Dr_GST_Amt] [decimal](18, 2) NULL,
	[Show_Rev_On_Stmt] [nvarchar](100) NULL,
	[Date_Posted] [datetime] NULL,
	[Debt_Outstanding] [decimal](18, 2) NULL,
	[Orig_Op] [nvarchar](1000) NULL,
	[Team_Code] [nvarchar](1000) NULL,
	[Rev_Code] [nvarchar](100) NULL,
	[Reverse_Other_Info] [nvarchar](1000) NULL,
	[Comm_Code] [nvarchar](1000) NULL,
	[Pay_Source] [nvarchar](1000) NULL,
	[Statement_Flag] [nvarchar](100) NULL,
	[Nft_Client_Code] [nvarchar](1000) NULL,
	[Orig_Op_code_Was] [nvarchar](1000) NULL,
	[PAYT_Key] [nvarchar](max) NULL,
	[Invoice_Number] [nvarchar](1000) NULL,
	[Eft_Transfer_Process_Flag] [nvarchar](100) NULL,
	[ZID] [integer] NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


