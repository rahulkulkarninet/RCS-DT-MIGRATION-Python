
/****** Object:  Table [dbo].[RC_SMS]    Script Date: 8/09/2025 10:52:14 AM ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_SMS]') AND type in (N'U'))
DROP TABLE [dbo].[RC_SMS]
GO

/****** Object:  Table [dbo].[RC_SMS]    Script Date: 8/09/2025 10:52:14 AM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_SMS](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](50) NULL,
	[Client_Group] [nvarchar](50) NULL,
	[Date_to_Send] [datetime] NULL,
	[Date_Queued] [datetime] NULL,
	[Date_Sent] [datetime] NULL,
	[Debtor_Code] [nvarchar](50) NULL,
	[Mobile_Phone] [nvarchar](50) NULL,
	[Message_Text] [nvarchar](500) NULL,
	[Type] [nvarchar](250) NULL,
	[Staggered] [nvarchar](250) NULL,
	[Operator_Code] [nvarchar](50) NULL,
	[Error_Message] [nvarchar](50) NULL,
	[Related_Party_Code] [nvarchar](20) NULL,
	[Solicited] [nvarchar](50) NULL,
	[Sms_Scheduled_Date] [datetime] NULL,
	[Req_ID] [nvarchar](50) NULL,
	[State] [nvarchar](50) NULL,
	[Doc_Hist_Code] [nvarchar](1) NULL,
	[Sms_Provider] [nvarchar](50) NULL,
	[Zone_Sent_Date] [datetime] NULL,
	[Sms_Sent_To_Representative] [nvarchar](1) NULL,
	[Contact_Ref] [nvarchar](20) NULL,
	[Sms_Source_Tag] [nvarchar](50) NULL,
	[ZID] [nvarchar](50) NULL
) ON [PRIMARY]
GO

-- 58.tblsmsoutput.sql joins tblSMSOutput back to this table per row. Without an
-- index the whole heap is rescanned for every tblSMSOutput row, which turned a
-- 15 second step into hours once tblSMSOutput had accumulated ~120k rows.
-- Contact_Ref leads, not ZID: ZID is nvarchar here but tblSMSOutput.Z_ID is int,
-- and int wins datatype precedence, so SQL Server converts this side and a
-- ZID-leading index can never be seeked. ZID rides along as a second key so the
-- residual is resolved without a lookup. TRUNCATE keeps indexes, so this only
-- needs recreating when the table itself is rebuilt by this script.
CREATE NONCLUSTERED INDEX [IX_RC_SMS_Contact_Ref_ZID]
    ON [dbo].[RC_SMS] ([Contact_Ref], [ZID])
    INCLUDE ([Extended_Debt_Code], [Solicited], [Error_Message])
GO



-- Join-key indexes for the migration queries. The staging tables are bulk
-- loaded and then joined per row by the Direct/*.sql steps; without these the
-- optimiser has only a heap to work with and falls back to rescanning the whole
-- table once per outer row. TRUNCATE preserves indexes, so these only need to be
-- recreated when this script rebuilds the table.
CREATE NONCLUSTERED INDEX [IX_RC_SMS_Debtor_Code]
    ON [dbo].[RC_SMS] ([Debtor_Code])
GO
CREATE NONCLUSTERED INDEX [IX_RC_SMS_Extended_Debt_Code]
    ON [dbo].[RC_SMS] ([Extended_Debt_Code])
GO
