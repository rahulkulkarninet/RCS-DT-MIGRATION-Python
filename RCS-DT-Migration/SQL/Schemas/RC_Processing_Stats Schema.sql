--USE [sqldb-glass-uat]
--GO

/****** Object:  Table [dbo].[RC_Processing_Stats]    Script Date: 19/08/2025 ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_Processing_Stats]') AND type in (N'U'))
DROP TABLE [dbo].[RC_Processing_Stats]
GO

/****** Object:  Table [dbo].[RC_Processing_Stats]    Script Date: 19/08/2025 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_Processing_Stats](
	ID BIGINT IDENTITY(1,1) PRIMARY KEY,
    Staging_LoadID NVARCHAR(100) NOT NULL,
    Customer_Code NVARCHAR(50) NOT NULL,
    db NVARCHAR(100) NULL,
    EntityID INT NOT NULL,
    [User] NVARCHAR(100) NOT NULL,
    From_Table NVARCHAR(255) NULL,
    Table_Name NVARCHAR(255) NOT NULL,
    Files_Count INT NOT NULL DEFAULT 0,
    Csv_Rows BIGINT NOT NULL DEFAULT 0,
    Rows_Inserted BIGINT NOT NULL DEFAULT 0,
    Start_Time DATETIME2(3) NOT NULL,
    End_Time DATETIME2(3) NOT NULL,
    Duration_Seconds DECIMAL(10,2) NOT NULL DEFAULT 0,
    Rows_Per_Second DECIMAL(10,0) NOT NULL DEFAULT 0,
    Success BIT NOT NULL DEFAULT 0,
    [Error_Message] NVARCHAR(MAX) NULL,
    Total_Debt DECIMAL(18,2) NULL,
    Total_Paid DECIMAL(18,2) NULL,
    Total_Overpayments DECIMAL(18,2) NULL,
    Total_Costs DECIMAL(18,2) NULL,
    Total_Outstanding DECIMAL(18,2) NULL,
    Total_Commission DECIMAL(18,2) NULL,
    Total_Interest DECIMAL(18,2) NULL,
    --Created_Date DATETIME2(3) DEFAULT GETDATE(),
    Created_Date DATETIME2(3) DEFAULT CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'AUS Eastern Standard Time' AS DATETIME2(3)),
    Migration_LoadID INT NULL,
    Migration_SessionID INT NULL,
    
    -- Indexes for better performance
    INDEX IX_processing_stats_load_id (Staging_LoadID),
    INDEX IX_processing_stats_customer_code (Customer_Code),
    INDEX IX_processing_stats_entityid (EntityID),
    INDEX IX_processing_stats_user ([User]),
    INDEX IX_processing_stats_start_time (Start_Time),
    INDEX IX_processing_stats_success (Success)
)
GO


