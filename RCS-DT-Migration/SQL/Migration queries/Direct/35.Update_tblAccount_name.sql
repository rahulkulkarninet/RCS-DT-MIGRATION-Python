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