-- Allocates every open migrated account on GS-COMBINED (Digital First 1-7, Primary
-- 8-27, Loop 28-37 as one 37-step treatment, per the business decision of 2026-09-23)
-- at the step treatment_step_service.py derived into RC_ACCOUNT_EXTRACT.Treatment_NewStep
-- from the RCS current treatment, next step and debt age (variables/treatment_step_codes.json).
-- A closed account has no derived step and gets no treatment. Suzanne Chhour (29 Sep):
-- allocate regardless of RCS status; the 365-day rule is a business control applied
-- after migration, not a migration filter.
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
                CROSS APPLY ( SELECT TOP 1 RC.Client_Code, RC.Treatment_NewStep AS New_Treatment_Step
                              FROM   RC_ACCOUNT_EXTRACT RC
                              WHERE  CAST(RC.Full_Debt_Code AS NVARCHAR(50)) = A.AccountNumberPrevious
                                     AND RC.Treatment_NewStep IS NOT NULL
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
