--USE [sqldb-glass-uat]
--GO

/****** Object:  Table [dbo].[RC_Entity_Mapping]    Script Date: 19/08/2025 ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_Entity_Mapping]') AND type in (N'U'))
DROP TABLE [dbo].[RC_Entity_Mapping]
GO

/****** Object:  Table [dbo].[RC_Entity_Mapping]    Script Date: 19/08/2025 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_Entity_Mapping](
	ID BIGINT IDENTITY(1,1) PRIMARY KEY,
    [Client_Description] NVARCHAR(1000) NOT NULL,
    [DATABASE] NVARCHAR(50) NOT NULL,
    [Client_Code] NVARCHAR(100) NOT NULL,
    [Client_Group] NVARCHAR(100) NOT NULL,
    [Entity_ID] INT NOT NULL,
 
    Created_Date DATETIME2(3) DEFAULT CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'AUS Eastern Standard Time' AS DATETIME2(3)),
    
    -- Indexes for better performance
    INDEX IX_Entity_Mapping_database ([DATABASE]),
    INDEX IX_Entity_Mapping_client_code ([Client_Code]),
    INDEX IX_Entity_Mapping_Entity_ID ([Entity_ID])
)
GO

