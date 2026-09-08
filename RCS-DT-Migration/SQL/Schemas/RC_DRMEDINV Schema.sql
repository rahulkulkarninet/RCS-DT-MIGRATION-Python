USE [sqldb-glass-dev-rc]
GO

/****** Object:  Table [dbo].[RC_DRMEDINV]    Script Date: 22/05/2025 8:27:37 AM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_DRMEDINV]') AND type in (N'U'))
DROP TABLE [dbo].[RC_DRMEDINV]
GO

/****** Object:  Table [dbo].[RC_DRMEDINV]    Script Date: 22/05/2025 8:27:37 AM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_DRMEDINV](
	[Full_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](10) NULL,
	[Client_Group] [nvarchar](50) NULL,
	[Short_Debt_Code] [int] NULL,
	[Account_No] [nvarchar](100) NULL,
	[Invoice_Number] [nvarchar](max) NULL,
	[Invoice_Date] [nvarchar] (max) NULL,
	[Invoice_Amount] [nvarchar](max) NULL,
	[Invoice_Paid] [nvarchar](max) NULL,
	[Invoice_Balance] [nvarchar](max) NULL,
	[Invoice_Part_Paid] [nvarchar](max) NULL,
	[Invoice_Pay_Code] [nvarchar](max) NULL,
	[Invoice_Web_Ref_Number] [nvarchar](max) NULL,
	[Invoice_In_Patient] [nvarchar](max) NULL,
	[Invoice_Referral_Date] [nvarchar](max) NULL,
	[Invoice_Doctor_Name] [nvarchar](max) NULL,
	[Invoice_Collection_Centre] [nvarchar](max) NULL,
	[Invoice_Flag] [nvarchar](1000) NULL,
	[Next_Of_Kin_Name] [nvarchar](max) NULL,	
	[Next_Of_Kin_Address] [nvarchar](max) NULL,	
	[Next_Of_Kin_Phone] [nvarchar](max) NULL,	
	[Seqno] [nvarchar](max) NULL,	
	[Payment_Amount] [nvarchar](max) NULL,
	[Payment_Key_Of_Payment] [nvarchar](max) NULL,
	[Payment_Date] [nvarchar](max) NULL,
	[Recall_Operator] [nvarchar](max) NULL,
	[Recall_Date_Time] [nvarchar](max) NULL,
	[Invoice_Description] [nvarchar] (max) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO


