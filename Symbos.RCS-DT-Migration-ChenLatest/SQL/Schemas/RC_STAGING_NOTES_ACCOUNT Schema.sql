

IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_STAGING_NOTES_ACCOUNT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_STAGING_NOTES_ACCOUNT]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_STAGING_NOTES_ACCOUNT](
	[StagingAccountNoteID] [bigint] IDENTITY(1,1) NOT NULL,
	[Extended_Debt_Code] [int] NULL,
	[Entry] [nvarchar](max) NULL,
	[LastNoteDate] [datetime] NULL,
	[NoteCount] [int] NULL,
	[SourceRows] [bigint] NULL,
	[CreateTS] [datetime] NULL,
	CONSTRAINT [PK_RC_STAGING_NOTES_ACCOUNT] PRIMARY KEY NONCLUSTERED
	(
		[StagingAccountNoteID] ASC
	)
) ON [PRIMARY]
GO


-- Clustered on the column 67.tblentry_notes.sql joins to tblAccount on, so that join
-- seeks rather than scans. One row per account, so the key is unique in practice
-- without being declared so.
CREATE CLUSTERED INDEX [CX_RC_STAGING_NOTES_ACCOUNT_Debt]
ON [dbo].[RC_STAGING_NOTES_ACCOUNT]
(
	[Extended_Debt_Code] ASC
)
GO
