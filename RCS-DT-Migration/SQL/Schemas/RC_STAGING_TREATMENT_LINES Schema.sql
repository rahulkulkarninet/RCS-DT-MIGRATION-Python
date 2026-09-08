/****** Object:  Table [dbo].[RC_STAGING_TREATMENT_LINES]    Script Date: 7/07/2026 ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_STAGING_TREATMENT_LINES]') AND type in (N'U'))
DROP TABLE [dbo].[RC_STAGING_TREATMENT_LINES]
GO

/****** Object:  Table [dbo].[RC_STAGING_TREATMENT_LINES]    Script Date: 7/07/2026 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_STAGING_TREATMENT_LINES](
	[StagingTreatmentLineID] [bigint] IDENTITY(1,1) NOT NULL,
	[StagingTreatmentID] [bigint] NULL,
	[AccountID] [int] NULL,
	[EntityID] [int] NULL,
	[AccountStatusID] [int] NULL,
	[LoadID] [int] NULL,
	[LoadDate] [datetime] NULL,
	[CreateID] [int] NULL,
	[CreateSessionID] [int] NULL,
	[CreateTS] [datetime] NULL,
	[StatusID] [int] NULL,
	[Treatment_Date] [datetime] NULL,
	[Treatment_Code] [int] NULL,
	[Treatment_Description] [nvarchar](500) NULL,
	[Treatment_Step] [int] NULL,
	[Treatment_Type] [nvarchar](100) NULL,
	[Treatment_Result_Code] [nvarchar](100) NULL,
	[Treatment_Result] [nvarchar](500) NULL,
	CONSTRAINT [PK_RC_STAGING_TREATMENT_LINES] PRIMARY KEY CLUSTERED
	(
		[StagingTreatmentLineID] ASC
	)
) ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_RC_STAGING_TREATMENT_LINES_RELATIONSHIP_KEY]
ON [dbo].[RC_STAGING_TREATMENT_LINES]
(
	[LoadID] ASC,
	[EntityID] ASC,
	[AccountID] ASC,
	[StagingTreatmentID] ASC,
	[Treatment_Step] ASC
)
INCLUDE
(
	[Treatment_Date],
	[Treatment_Code],
	[Treatment_Type],
	[Treatment_Result_Code],
	[Treatment_Result]
)
GO

CREATE NONCLUSTERED INDEX [IX_RC_STAGING_TREATMENT_LINES_LOAD_ACCOUNT_STEP]
ON [dbo].[RC_STAGING_TREATMENT_LINES]
(
	[LoadID] ASC,
	[EntityID] ASC,
	[AccountID] ASC,
	[Treatment_Step] ASC
)
INCLUDE
(
	[Treatment_Date],
	[Treatment_Code],
	[Treatment_Type],
	[Treatment_Result_Code],
	[Treatment_Result]
)
GO

CREATE NONCLUSTERED INDEX [IX_RC_STAGING_TREATMENT_LINES_LOAD_STATUS]
ON [dbo].[RC_STAGING_TREATMENT_LINES]
(
	[LoadID] ASC,
	[StatusID] ASC,
	[AccountStatusID] ASC
)
INCLUDE
(
	[AccountID],
	[EntityID],
	[Treatment_Date],
	[Treatment_Step]
)
GO
