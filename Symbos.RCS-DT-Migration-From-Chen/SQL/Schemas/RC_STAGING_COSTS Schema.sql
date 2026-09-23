/****** Object:  Table [dbo].[RC_STAGING_COSTS]    Script Date: 8/09/2026 ******/
-- One row per debtor per charged cost code - the long form of the 71 [Chg_<code>]
-- columns on RC_COSTS_EXTRACT. Written by cost_service.py before the migration SQL
-- runs, from variables/cost_codes.json, with CostTypeID and MasterCostID already
-- resolved against tblCostType and tblMasterCost. 51.tblcosts.sql reads it instead of
-- carrying its own hardcoded list of code-to-column pairs.
--
-- Keyed on Debtor_Code rather than AccountID: it is built before 01.tblaccount.sql has
-- created the accounts, so the join to tblAccount happens in 51 instead. Rows are kept
-- per LoadID the same way RC_STAGING_TREATMENTS keeps them, and the service deletes its
-- own LoadID's rows before inserting so a re-run replaces rather than doubles them.
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_STAGING_COSTS]') AND type in (N'U'))
DROP TABLE [dbo].[RC_STAGING_COSTS]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_STAGING_COSTS](
	[StagingCostID] [bigint] IDENTITY(1,1) NOT NULL,
	[Debtor_Code] [int] NULL,
	[CostTypeCode] [nvarchar](20) NULL,
	[SourceColumn] [nvarchar](128) NULL,
	[Amount] [decimal](18, 2) NULL,
	[CostTypeID] [int] NULL,
	[MasterCostID] [int] NULL,
	[LoadID] [int] NULL,
	[CreateID] [int] NULL,
	[CreateSessionID] [int] NULL,
	[CreateTS] [datetime] NULL,
	[StatusID] [int] NULL,
	CONSTRAINT [PK_RC_STAGING_COSTS] PRIMARY KEY CLUSTERED
	(
		[StagingCostID] ASC
	)
) ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_RC_STAGING_COSTS_LOAD_DEBTOR]
ON [dbo].[RC_STAGING_COSTS]
(
	[LoadID] ASC,
	[Debtor_Code] ASC
)
INCLUDE
(
	[CostTypeCode],
	[Amount],
	[CostTypeID],
	[MasterCostID]
)
GO
