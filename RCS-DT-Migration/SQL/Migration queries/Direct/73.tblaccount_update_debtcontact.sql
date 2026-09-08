
UPDATE  A
SET     LUPLastPhoneContactDate = DC.DebtContactsTS ,
        LUPLastPhoneDebtorDate = DC.DebtContactsTS
FROM    tblAccount A
        INNER JOIN tblDebtContact DC ON A.AccountID = DC.AccountID
WHERE   DC.StatusID = 1
        AND A.StatusID = 1
--  AND DC.Phone IS NOT NULL            -- any contact, not just phone, client requirement
        AND A.LoadID = {{LoadID}}
;