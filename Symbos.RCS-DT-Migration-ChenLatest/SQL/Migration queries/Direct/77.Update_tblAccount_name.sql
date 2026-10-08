-- Names each account after its first contact. Was 35.Update_tblAccount_name.sql, which
-- collided with 35.tblcontactdetail_create_email_insurance.sql - two files on one
-- sequence, so which ran first was decided by a filename sort rather than by intent.
--
-- Moved here rather than to 36 because nothing depends on when it runs: tblAccount.
-- AccountName is written by 01 and updated here, and no other migration file reads it.
-- Last before the loop file is the safest slot - every contact and account-contact link
-- exists by now, and a stored procedure in the loop file that reads AccountName still
-- sees the updated value.
--
-- Known defect, unchanged by the move: the CROSS APPLY picks the lowest ContactID with
-- no RelationshipID = 1 filter, so an account can be named after a witness or an
-- insurer once 25-30 have added third-party and related-party contacts. See
-- HARDCODED_VALUES_AUDIT.md.
UPDATE  A
SET     A.AccountName = X.Name
FROM    tblAccount A
        CROSS APPLY ( SELECT TOP 1
                                ISNULL(C.FirstName + ' ', '') + ISNULL(C.LastName, '') AS [Name]
                      FROM      tblAccount_Contact AC
                                INNER JOIN tblContact C ON AC.ContactID = C.ContactID
                      WHERE     AC.AccountID = A.AccountID
                      ORDER BY  C.ContactID ASC
                    ) X
WHERE   LoadID = {{LoadID}}
;