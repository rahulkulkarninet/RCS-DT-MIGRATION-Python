-- 009: RC_ACCOUNT_EXTRACT.Arrangement_Active
--
-- Derived column filled by arrangement_status_service.py during the mapping phase:
-- INSTALMENT / DEAL / NONE for every open account in an instalment / PTP / dishonour
-- RCS status (NULL outside that scope). The service adds the column itself when it is
-- missing; this script is for deploying it ahead of a run.
IF COL_LENGTH('dbo.RC_ACCOUNT_EXTRACT', 'Arrangement_Active') IS NULL
    ALTER TABLE dbo.RC_ACCOUNT_EXTRACT ADD [Arrangement_Active] NVARCHAR(20) NULL;
GO
