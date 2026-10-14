INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsExtranetUser ,
          IsPerson ,
          ContactTypeID ,
          GenderID ,
          Title ,
          FirstName ,
          MiddleName ,
          LastName ,
          DOB ,
          EntityName ,
          TradingAs ,
          BusinessNumber ,
          CorporationNumber,
          IsTemporaryPassword ,
          DriversLicenceNumber ,
          ContactReference ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          Z_REF ,
          Z_REF2
        )
        SELECT DISTINCT
                {{LoadID}} ,
                0 , --IsUser
                0 , --IsExtranetUser: NOT NULL with no default, and migrated
                    -- debtors get no portal login, matching IsUser
                K.IsPerson ,	--IsPerson
                IIF(K.IsPerson = 1, {{ContactTypeID_Individual}}, {{ContactTypeID_Entity}}) ,	--ContactTypeID
                G.GenderID ,
                C.Title ,
                IIF(K.IsPerson = 1, C.First_Name, NULL) , -- FirstName
                NULL ,	--Middle Name
                IIF(K.IsPerson = 1, C.Company_Surname, NULL) , -- LastName,
                C.Birth_Date ,
                IIF(K.IsPerson = 1, NULL, C.Company_Surname) , -- EntityName,
                COALESCE(NULLIF(LTRIM(RTRIM(C.Trading_Name)), ''), NULLIF(LTRIM(RTRIM(A.Trading_Name)), '')) ,
                C.A_B_N ,
                C.A_C_N ,
                1 ,
                C.Drivers_Licence ,
                C.Person_Id ,    -- Pulse ID
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                A.Full_Debt_Code ,
                C.Debtor_Code
        FROM    RC_DEBTOR C
                INNER JOIN RC_ACCOUNT_EXTRACT A ON C.Debt_Code = A.Full_Debt_Code
                INNER JOIN tblAccount ON tblAccount.AccountNumberPrevious = CONVERT(nvarchar(100), A.Full_Debt_Code)
                                         AND tblAccount.LoadID = {{LoadID}}
                CROSS APPLY ( SELECT CASE WHEN UPPER(LTRIM(RTRIM(C.Leg_Type))) IN ( 'INDIVIDUAL', 'SOLE TRADER', 'SOLETRADER', 'PERSON' ) THEN 1
                                          WHEN NULLIF(LTRIM(RTRIM(C.Leg_Type)), '') IS NOT NULL THEN 0
                                          WHEN C.A_B_N IS NULL AND C.A_C_N IS NULL THEN 1
                                          ELSE 0
                                     END AS IsPerson
                            ) K
                OUTER APPLY ( SELECT TOP 1
                                        GenderID
                              FROM      tblGender
                              WHERE     Gender = CASE UPPER(LTRIM(RTRIM(C.Sex)))
                                                   WHEN 'M' THEN 'Male'
                                                   WHEN 'F' THEN 'Female'
                                                   WHEN 'U' THEN 'unknown'
                                                 END
                              ORDER BY  GenderID
                            ) G
        ORDER BY C.Debtor_Code ASC ,
                A.Full_Debt_Code ASC
;