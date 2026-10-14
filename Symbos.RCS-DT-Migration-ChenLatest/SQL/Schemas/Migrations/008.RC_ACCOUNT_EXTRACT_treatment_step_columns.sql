-- 008: RC_ACCOUNT_EXTRACT.Treatment_NewStep / Treatment_NewTreatmentCode
--
-- Derived columns filled by treatment_step_service.py during the mapping phase (the
-- GS-COMBINED step 78.tblAccount_Treatment allocates each open account at, and the new
-- treatment it came from). The service adds them itself when they are missing; this
-- script is for deploying them ahead of a run.
IF COL_LENGTH('dbo.RC_ACCOUNT_EXTRACT', 'Treatment_NewStep') IS NULL
    ALTER TABLE dbo.RC_ACCOUNT_EXTRACT ADD [Treatment_NewStep] INT NULL;
IF COL_LENGTH('dbo.RC_ACCOUNT_EXTRACT', 'Treatment_NewTreatmentCode') IS NULL
    ALTER TABLE dbo.RC_ACCOUNT_EXTRACT ADD [Treatment_NewTreatmentCode] NVARCHAR(50) NULL;
GO
