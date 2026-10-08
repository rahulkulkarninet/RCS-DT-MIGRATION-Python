--USE [sqldb-glass-uat]
--GO

/****** Object:  Table [dbo].[RC_PaymentMethod_Mapping]    Script Date: 17/08/2026 ******/
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_PaymentMethod_Mapping]') AND type in (N'U'))
DROP TABLE [dbo].[RC_PaymentMethod_Mapping]
GO

/****** Object:  Table [dbo].[RC_PaymentMethod_Mapping]    Script Date: 17/08/2026 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_PaymentMethod_Mapping](
	ID BIGINT IDENTITY(1,1) PRIMARY KEY,
    [RCS_PaymentMethod] NVARCHAR(100) NOT NULL,
    [DT_BankTransactionMethodID] INT NOT NULL,
    [DT_BankTransactionMethod] NVARCHAR(100) NOT NULL,

    Created_Date DATETIME2(3) DEFAULT CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'AUS Eastern Standard Time' AS DATETIME2(3)),

    -- Indexes for better performance
    INDEX IX_PaymentMethod_Mapping_RCS_PaymentMethod ([RCS_PaymentMethod]),
    INDEX IX_PaymentMethod_Mapping_DT_BankTransactionMethodID ([DT_BankTransactionMethodID])
)
GO

INSERT INTO [dbo].[RC_PaymentMethod_Mapping] ([RCS_PaymentMethod], [DT_BankTransactionMethodID], [DT_BankTransactionMethod])
VALUES
    (N'DD',   6, N'Direct Debit'),
    (N'BPAY', 5, N'BPAY')
GO
