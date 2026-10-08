
/****** Object:  Table [dbo].[RC_EMAIL_EXTRACT]    Script Date: 8/09/2025 11:11:29 AM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_EMAIL_EXTRACT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_EMAIL_EXTRACT]
GO

/****** Object:  Table [dbo].[RC_EMAIL_EXTRACT]    Script Date: 8/09/2025 11:11:29 AM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_EMAIL_EXTRACT](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](500) NULL,
	[Client_Group] [nvarchar](500) NULL,
	[Document_Code] [nvarchar](500) NULL,
	[Type] [nvarchar](500) NULL,
	[Queue_Date] [datetime] NULL,
	[Debtor_Code] [nvarchar](100) NULL,
	[Doc_Hist_Code] [int] NULL,
	[Op_code] [nvarchar](50) NULL,
	[Email_Addr] [nvarchar](50) NULL,
	[Sent_Date] [datetime] NULL,
	[Fail_Date] [datetime] NULL,
	[Fail_Reas] [nvarchar](100) NULL,
	[State] [nvarchar](500) NULL,
	[ZID] [int] NULL
) ON [PRIMARY]
GO

-- 60.tblemail.sql joins tblEmail back to this table per row, the same shape as
-- 58.tblsmsoutput.sql. ZID is int here against tblEmail.Z_REF nvarchar, but the
-- conversion lands on the tblEmail side, so this index is still seekable.
CREATE NONCLUSTERED INDEX [IX_RC_EMAIL_EXTRACT_ZID_Debtor_Code]
    ON [dbo].[RC_EMAIL_EXTRACT] ([ZID], [Debtor_Code])
    INCLUDE ([Extended_Debt_Code], [Doc_Hist_Code], [Fail_Date])
GO



-- Join-key indexes for the migration queries. The staging tables are bulk
-- loaded and then joined per row by the Direct/*.sql steps; without these the
-- optimiser has only a heap to work with and falls back to rescanning the whole
-- table once per outer row. TRUNCATE preserves indexes, so these only need to be
-- recreated when this script rebuilds the table.
CREATE NONCLUSTERED INDEX [IX_RC_EMAIL_EXTRACT_Debtor_Code]
    ON [dbo].[RC_EMAIL_EXTRACT] ([Debtor_Code])
GO
CREATE NONCLUSTERED INDEX [IX_RC_EMAIL_EXTRACT_Extended_Debt_Code]
    ON [dbo].[RC_EMAIL_EXTRACT] ([Extended_Debt_Code])
GO
