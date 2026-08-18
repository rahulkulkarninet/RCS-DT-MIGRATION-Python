USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_STATEMENT]    Script Date: 7/04/2025 1:55:54 PM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_STATEMENT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_STATEMENT]
GO

/****** Object:  Table [dbo].[RC_STATEMENT]    Script Date: 7/04/2025 1:55:54 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_STATEMENT](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](50) NULL,
	[Client_Group_Code] [nvarchar](50) NULL,
	[Account_No] [nvarchar](100) NULL,
	[Date] [datetime] NULL,
	[Particulars] [nvarchar](50) NULL,
	[Direct_Debt_Amount] [decimal](18, 2) NULL,
	[Direct_Interest_Amount] [decimal](18, 2) NULL,
	[Direct_Cost_Amount] [decimal](18, 2) NULL,
	[Direct_UIL_Amount] [decimal](18, 2) NULL,
	[Trust_Debt_Amount] [decimal](18, 2) NULL,
	[Trust_Interest_Amount] [decimal](18, 2) NULL,
	[Trust_Cost_Amount] [decimal](18, 2) NULL,
	[Trust_UIL_Amount] [decimal](18, 2) NULL,
	[Tran_Key] [int] NULL,
	[Range_Flag] [int] NULL,
	[Debt_Ref_No] [nvarchar](max) NULL,
	[Gst_Amount] [decimal](18, 2) NULL,
	[Type] [nvarchar](50) NULL,
	[Direct_Commission_Amount] [decimal](18, 2) NULL,
	[Trust_Commission_Amount] [decimal](18, 2) NULL,
	[Closed_Flag] [nvarchar](100) NULL,
	[Tp_Insurer_Code] [nvarchar](100) NULL,
	[Accounting_Month] [nvarchar](50) NULL,
	[Run_Name] [nvarchar](50) NULL,
	[Refund_Amount] [decimal](18, 2) NULL,
	[Transfer_Amount] [decimal](18, 2) NULL,
	[Refund_Date] [datetime] NULL,
	[Transfer_Date] [datetime] NULL,
	[Invoice_Number] [nvarchar](100) NULL,
	[Invoice_Date] [datetime] NULL,
	[Eft_Date] [datetime] NULL,
	[BPAY_Batch_Date] [datetime] NULL,
	[Trrf_Link] [nvarchar](100) NULL,
	[Client_Payment_Id] [nvarchar](100) NULL,
	[Client_Payment_Amount] [nvarchar](max) NULL,
	[Print_On_Statement_Flag] [nvarchar](100) NULL,
	[Cheque_Request_Date] [datetime] NULL,
	[Date_Statement_Record_Created] [datetime] NULL,
	[Invoice_No] [nvarchar](500) NULL,
	[Netsuite_Date] [datetime] NULL,
	[Unique_Transid] [nvarchar](1000) NULL,
	[column43] [nvarchar](100) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


