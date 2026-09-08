
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_RELATEDPARTY]') AND type in (N'U'))
DROP TABLE [dbo].[RC_RELATEDPARTY]
GO

/****** Object:  Table [dbo].[RC_RELATEDPARTY] ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_RELATEDPARTY](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](100) NULL,
	[Client_Group_Code] [nvarchar](100) NULL,
	[Account_No] [nvarchar](100) NULL,
	[Last_Name] [nvarchar](1000) NULL,
	[First_Name] [nvarchar](1000) NULL,
	[Email_Address] [nvarchar](1000) NULL,
	[Contact_Name] [nvarchar](1000) NULL,
	[Salutation] [nvarchar](1000) NULL,
	[Dx_Number] [nvarchar](1000) NULL,
	[Related_Party_Type_Code] [nvarchar](100) NULL,
	[Start_Date] [datetime] NULL,
	[Date_Of_Birth] [datetime] NULL,
	[Reference] [nvarchar](1000) NULL,
	[Position] [nvarchar](1000) NULL,
	[Block_Letter] [nvarchar](1000) NULL,
	[Nationality] [nvarchar](1000) NULL,
	[Person_Id] [nvarchar](1000) NULL,
	[Witness_Statement] [nvarchar](max) NULL,
	[Title] [nvarchar](1000) NULL,
	[Bankruptcy] [nvarchar](1000) NULL,
	[Customer_Reference] [nvarchar](1000) NULL,
	[Phone_Type] [nvarchar](max) NULL,
	[Phone_No] [nvarchar](max) NULL,
	[Phone_Validity] [nvarchar](max) NULL,
	[Phone_Start] [nvarchar](max) NULL,
	[Phone_End] [nvarchar](max) NULL,
	[Phone_Preferred_Flag] [nvarchar](2000) NULL,
	[Phone_Last_Contact_Date_Time] [nvarchar](max) NULL,
	[Phone_Score] [nvarchar](max) NULL,
	[Phone_No_Changed_By] [nvarchar](max) NULL,
	[Phone_No_Changed_Date_Time] [nvarchar](max) NULL,
	[Block_SMS] [nvarchar](1000) NULL,
	[Block_Email] [nvarchar](1000) NULL,
	[A_B_N] [nvarchar](1000) NULL,
	[Other_Email] [nvarchar](1000) NULL,
	[Street_Address] [nvarchar](1000) NULL,
	[Mailing_Address] [nvarchar](1000) NULL,
	[ZID] [nvarchar](1000) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
