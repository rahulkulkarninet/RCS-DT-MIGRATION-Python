WITH    CTE_ContactData
          AS ( SELECT   C.ContactID ,
                        CD_EMAIL.ContactDetailID AS Email_ContactDetailID ,
                        CD_PHONE.ContactDetailID AS Phone_ContactDetailID ,
                        ADR.AddressID AS Address_AddressID
               FROM     tblContact C
                        CROSS APPLY ( SELECT TOP 1
                                                CD.ContactDetailID
                                      FROM      tblContactDetail CD WITH ( NOLOCK )
                                                INNER JOIN tblContactDetailType CDT WITH ( NOLOCK ) ON CD.ContactDetailTypeID = CDT.ContactDetailTypeID
                                      WHERE     CD.ContactID = C.ContactID
                                                AND CDT.SystemContactDetailTypeID = 0 --Email
                                      ORDER BY  CD.ContactDetailID ASC
                                    ) CD_EMAIL
                        CROSS APPLY ( SELECT TOP 1
                                                CD.ContactDetailID
                                      FROM      tblContactDetail CD WITH ( NOLOCK )
                                                INNER JOIN tblContactDetailType CDT WITH ( NOLOCK ) ON CD.ContactDetailTypeID = CDT.ContactDetailTypeID
                                      WHERE     CD.ContactID = C.ContactID
                                                AND CDT.SystemContactDetailTypeID = 1 --Phone
                                      ORDER BY  CD.ContactDetailID ASC
                                    ) CD_PHONE
                        CROSS APPLY ( SELECT TOP 1
                                                ADR.AddressID
                                      FROM      tblAddress ADR WITH ( NOLOCK )
                                      WHERE     ADR.ContactID = C.ContactID
                                                AND ADR.StatusID = 1
                                      ORDER BY  ADR.AddressID ASC
                                    ) ADR
               WHERE    C.LoadID = {{LoadID}}
             )
    UPDATE  C
    SET     C.PrimaryEmail_ContactDetailID = CCD.Email_ContactDetailID ,
            C.PrimaryPhone_ContactDetailID = CCD.Phone_ContactDetailID ,
            C.Primary_AddressID = CCD.Address_AddressID
    FROM    tblContact C WITH ( ROWLOCK )
            INNER JOIN CTE_ContactData CCD ON CCD.ContactID = C.ContactID
;