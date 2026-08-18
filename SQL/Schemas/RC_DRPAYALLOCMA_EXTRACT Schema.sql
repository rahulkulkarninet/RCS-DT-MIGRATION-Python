/****** Object:  Table [dbo].[RC_DRPAYALLOCMA_EXTRACT]    Script Date: 17/08/2026 ******/

IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_DRPAYALLOCMA_EXTRACT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_DRPAYALLOCMA_EXTRACT]
GO

/****** Object:  Table [dbo].[RC_DRPAYALLOCMA_EXTRACT]    Script Date: 17/08/2026 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_DRPAYALLOCMA_EXTRACT](
	[Full_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](1000) NULL,
	[Client_Group] [nvarchar](1000) NULL,
	[Short_Debt_Code] [int] NULL,
	[Account_No] [nvarchar](100) NULL,
	[DRPAYALLOCMD_Key] [nvarchar](500) NULL,
	[Transaction_No] [nvarchar](500) NULL,
	[Allocated_Amt] [nvarchar](max) NULL,
	[Man_Alloc_Amt] [nvarchar](1000) NULL,
	[Ident_Key] [nvarchar](max) NULL,
	[Ident_Amount] [nvarchar](1000) NULL,
	[Id_Comm] [decimal](18, 2) NULL,
	[Id_Grosspaid] [nvarchar](1000) NULL,
	[Id_Grosscomm] [decimal](18, 2) NULL,
	[Id_Tier] [nvarchar](1000) NULL,
	[Tier_1_Commission] [nvarchar](1000) NULL,
	[Tier_2_Commission] [nvarchar](1000) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


