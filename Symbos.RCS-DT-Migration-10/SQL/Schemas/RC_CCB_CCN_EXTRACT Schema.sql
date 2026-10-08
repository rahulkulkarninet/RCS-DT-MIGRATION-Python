
/****** Object:  Table [dbo].[RC_CCB_CCN_EXTRACT] ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_CCB_CCN_EXTRACT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_CCB_CCN_EXTRACT]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

-- Credit bureau listings, one row per account. Every listing column carries the
-- CCB_ prefix whatever the listing is: Type (COMMERCIAL / CONSUMER) is what says
-- whether the row is a commercial (CCN) or consumer (CCB) listing, and
-- Direct/69 routes on it. ABN and ACN are carried as sent but not migrated -
-- the contact's numbers come from RC_DEBTOR (Direct/22).
CREATE TABLE [dbo].[RC_CCB_CCN_EXTRACT](
	[Extended_Debt_Code] [int] NOT NULL,
	[Client_Code] [nvarchar](100) NULL,
	[Client_Group] [nvarchar](100) NULL,
	[Debtor_Code] [nvarchar](100) NULL,
	[Debtor_Name] [nvarchar](500) NULL,
	[Provider] [nvarchar](40) NULL,
	[Type] [nvarchar](50) NULL,
	[ABN] [nvarchar](100) NULL,
	[ACN] [nvarchar](100) NULL,
	[CCB_Orig_Sent_date] [datetime] NULL,
	[CCB_Bureau_Unique_Key] [nvarchar](200) NULL,
	[CCB_Last_Sent_Date] [datetime] NULL,
	[CCB_Closed_Date] [datetime] NULL,
	[CCB_Listing_Balance] [decimal](18, 2) NULL,
	[CCB_Balance_Outstanding] [decimal](18, 2) NULL,
	[APLAN_Status] [nvarchar](50) NULL,
	[APLAN_Status_Date] [datetime] NULL,
	[CCB_Product] [nvarchar](200) NULL,
	[CCB_Flag] [nvarchar](50) NULL,
	[CCB_MG_UniqueKey] [nvarchar](200) NULL,
	[CCB_Update_Received_Date] [datetime] NULL,
	[CCB_Warning_Codes] [nvarchar](max) NULL,
	[CCB_Warning_Description] [nvarchar](max) NULL,
	[CCB_Warning_Field] [nvarchar](max) NULL,
	[CCB_Warning_Value] [nvarchar](max) NULL,
	[CCB_Error_Code] [nvarchar](max) NULL,
	[CCB_Error_Description] [nvarchar](max) NULL,
	-- Earlier APLAN statuses and their dates. Kept for reference; tracking has
	-- nowhere to put a history, so Direct/69 does not migrate them.
	[APLAN_Status_Hist] [nvarchar](max) NULL,
	[APLAN_Status_Date_Hist] [nvarchar](max) NULL,
	[ZID] [nvarchar](100) NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO



-- Join-key index for the migration queries. The staging tables are bulk
-- loaded and then joined per row by the Direct/*.sql steps; without these the
-- optimiser has only a heap to work with and falls back to rescanning the whole
-- table once per outer row. TRUNCATE preserves indexes, so these only need to be
-- recreated when this script rebuilds the table.
CREATE NONCLUSTERED INDEX [IX_RC_CCB_CCN_EXTRACT_Extended_Debt_Code]
    ON [dbo].[RC_CCB_CCN_EXTRACT] ([Extended_Debt_Code])
GO
