/****** Object:  Table [dbo].[RC_STAGING_TREATMENTS]    Script Date: 7/07/2026 ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_STAGING_TREATMENTS]') AND type in (N'U'))
DROP TABLE [dbo].[RC_STAGING_TREATMENTS]
GO

/****** Object:  Table [dbo].[RC_STAGING_TREATMENTS]    Script Date: 7/07/2026 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_STAGING_TREATMENTS](
	[StagingTreatmentID] [bigint] IDENTITY(1,1) NOT NULL,
	[AccountID] [int] NULL,
	[EntityID] [int] NULL,
	[AccountStatusID] [int] NULL,
	[LoadID] [int] NULL,
	[LoadDate] [datetime] NULL,
	[CreateID] [int] NULL,
	[CreateSessionID] [int] NULL,
	[CreateTS] [datetime] NULL,
	[StatusID] [int] NULL,
	[Current_Treatment] [int] NULL,
	[Next_Step_No_1] [int] NULL,
	[Next_Treatment_Date] [datetime] NULL,
	[Last_Treatment_Step_Date] [datetime] NULL,
	CONSTRAINT [PK_RC_STAGING_TREATMENTS] PRIMARY KEY CLUSTERED
	(
		[StagingTreatmentID] ASC
	)
) ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_RC_STAGING_TREATMENTS_RELATIONSHIP_KEY]
ON [dbo].[RC_STAGING_TREATMENTS]
(
	[LoadID] ASC,
	[EntityID] ASC,
	[AccountID] ASC
)
INCLUDE
(
	[StagingTreatmentID],
	[AccountStatusID],
	[StatusID]
)
GO

CREATE NONCLUSTERED INDEX [IX_RC_STAGING_TREATMENTS_LOAD_STATUS]
ON [dbo].[RC_STAGING_TREATMENTS]
(
	[LoadID] ASC,
	[StatusID] ASC,
	[AccountStatusID] ASC
)
INCLUDE
(
	[AccountID],
	[EntityID],
	[Current_Treatment],
	[Next_Step_No_1],
	[Next_Treatment_Date]
)
GO
