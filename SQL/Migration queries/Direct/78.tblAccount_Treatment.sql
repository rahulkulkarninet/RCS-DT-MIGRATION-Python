-- REWRITTEN 2026-09-23: Digital First, Primary and Loop are ONE continuous 37-step
-- treatment now, not three separate ones. Per the business clarification that day:
-- score-colour-based branching between them was descoped for T1 go-live, so instead of
-- three treatments with "re-allocation" between them, the whole thing was built as one
-- long sequence (Digital First 1-7, Primary extended 8-27, Loop 28-37) made long enough
-- (~90+ days) that it never needs to loop back. Matches the "New Mapping" tab of
-- Treatment_Migration_Validation (1).xlsx exactly - see build_combined_treatment*.py in
-- the scratchpad for how GS-COMBINED was built from it.
--
-- This also replaces the old approach of always allocating fresh at step 1: instead it
-- reads the CURRENT step directly from RC_TREATMENT_STEP_MAPPING, a lookup table loaded
-- from the "Complete Mapping" tab of that same workbook - Suz's own team's precomputed
-- current-legacy-code/step -> new-step numbers, not something this script re-derives.
-- That mapping was confirmed (2026-09-23) to be a literal SequenceNo in the new 37-step
-- treatment, not something needing further translation.
--
-- RC_TREATMENT_STEP_MAPPING only has rows for accounts whose Short_Debt_Code resolved
-- against our local RC_TREATMENT CSVs (3,153 of CG8110's 3,667 rows in "Complete Mapping"
-- - the other 514 didn't resolve, most likely because our local extract is a few weeks
-- stale relative to Suz's fresher export). An account with no row here is excluded via
-- CROSS APPLY, same as an account with no resolvable treatment always has been - this
-- migration does not guess a step for an account it has no precomputed mapping for.
--
-- 2026-09-29/30: two rules from the Treatment Mapping chat were briefly enforced here
-- (skip TREATMENTHOLD / TREATEOP accounts; skip debts aged 365+ days). Suzanne Chhour
-- reversed both on 29 Sep (22:46 UTC) in the same chat:
--   a. "If treatment has been mapped, map it and just move to the current status" - i.e.
--      allocate every account that has a Complete Mapping row, regardless of RCS status.
--      TREATMENTHOLD and TREATEOP both land in the Debtrak status
--      'Treatment - End of Process' (see variables/account_status_codes.json).
--   b. The 365-day rule is a business operating control on which stock gets campaigned,
--      not a migration filter. Aged files will be bulk-moved to End of Process by the
--      business (manually or via a new module) after migration.
-- So this script allocates purely from RC_TREATMENT_STEP_MAPPING again. The
-- Treatment_MaxAgeDays constant (default 365) stays in migration_variables.json in case
-- the age rule is ever wanted back, but is not referenced here.
-- Sravanthi confirmed (29 Sep) that accounts with no mapping row are files closed in
-- RCS after our extract was taken; they migrate with their status and get no treatment.
INSERT  INTO tblAccount_Treatment WITH ( ROWLOCK )
        ( AccountID ,
          EntityID ,
          ClientCode ,
          TreatmentID ,
          TreatmentVersionID ,
          TreatmentAllocationRuleID ,
          RuleSetVersion ,
          AllocationSource ,
          AllocatedAt ,
          CurrentSequenceNo ,
          NextDueDate ,
          DriftDays ,
          StatusID ,
          FamilyVersionPinTS
        )
        SELECT  A.AccountID ,
                A.EntityID ,
                'RCS' ,
                TREAT.TreatmentID ,
                TREAT.PublishedVersionID ,
                AR.TreatmentAllocationRuleID ,
                1 ,
                'Migration' ,
                -- AllocatedAt / NextDueDate (fixed 2026-10-12, Srav: "why is the next step
                -- action date 23/03/27"): the ladder stores every step as a day offset from
                -- the ladder start, and the engine shows/dues step N at AllocatedAt + offset.
                -- A migrated account is placed AT its current step, so that step is due on
                -- migration day, not offset days later. Backdating AllocatedAt by the step's
                -- offset makes "day N of the ladder" land on migration day and keeps the
                -- engine's drift display consistent; NextDueDate is migration day itself.
                DATEADD(DAY, -STEP.DayOffset, SYSDATETIMEOFFSET()) ,
                MAP.New_Treatment_Step ,
                CAST(GETUTCDATE() AS DATE) ,
                0 ,
                0 ,
                -- FamilyVersionPinTS (NOT NULL, no default; appeared on dev-debtrak between
                -- 2026-09-24 and 2026-09-29 alongside the FAM* template-family rename): the
                -- moment the account was pinned to the treatment's template-family version.
                -- For a migrated allocation that is the migration run itself (AllocatedAt is
                -- backdated by the step offset, so this is deliberately NOT the same value).
                -- No app-side INSERT existed in Query Store yet to copy the app's own value from.
                SYSDATETIMEOFFSET()
        FROM    tblAccount A WITH ( NOLOCK )
                -- One row per account, keyed on the stable Full_Debt_Code business key -
                -- loaded fresh by build_step_mapping_lookup.py from "Complete Mapping",
                -- not computed here.
                CROSS APPLY ( SELECT TOP 1 Client_Code, New_Treatment_Step
                              FROM   RC_TREATMENT_STEP_MAPPING
                              WHERE  Full_Debt_Code = A.AccountNumberPrevious
                            ) MAP
                -- CROSS, not OUTER: TreatmentID is NOT NULL on tblAccount_Treatment. Only
                -- one treatment exists now (GS-COMBINED), but this still resolves it via
                -- the stable TreatmentCode business key rather than hardcoding the
                -- IDENTITY value, so it does not break if the treatment gets rebuilt.
                CROSS APPLY ( SELECT TOP 1 TreatmentID, PublishedVersionID
                              FROM   tblTreatment
                              WHERE  TreatmentCode = 'GS-COMBINED'
                                     AND PublishedVersionID IS NOT NULL
                              ORDER BY TreatmentID
                            ) TREAT
                OUTER APPLY ( SELECT TOP 1 TreatmentAllocationRuleID
                              FROM   tblTreatmentAllocationRule
                              WHERE  ClientCode = MAP.Client_Code
                                     AND TreatmentID = TREAT.TreatmentID
                                     AND IsEnabled = 1
                              ORDER BY Priority
                            ) AR
                -- CROSS, not OUTER: NextDueDate is NOT NULL. MAP.New_Treatment_Step is a
                -- literal SequenceNo in GS-COMBINED's 37 steps - an account whose step
                -- number doesn't resolve to a real step (shouldn't happen, but not
                -- guaranteed by any constraint) is correctly excluded rather than
                -- inserted with a NULL due date.
                CROSS APPLY ( SELECT TOP 1 DayOffset
                              FROM   tblTreatmentStep
                              WHERE  TreatmentVersionID = TREAT.PublishedVersionID
                                     AND SequenceNo = MAP.New_Treatment_Step
                            ) STEP
        WHERE   A.LoadID = {{LoadID}}
                AND NOT EXISTS ( SELECT 1 FROM tblAccount_Treatment AT2 WITH ( NOLOCK ) WHERE AT2.AccountID = A.AccountID )
;
