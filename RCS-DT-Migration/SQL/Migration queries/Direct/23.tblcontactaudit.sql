INSERT  INTO tblContactAudit
        ( ContactID ,
          AuditTS ,
          LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,
          Title ,
          FirstName ,
          LastName ,
          DOB ,
          EntityName ,
          TradingAs ,
          BusinessNumber ,
          CorporationNumber ,
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
                tblContact.ContactID ,
                GETDATE() ,
                {{LoadID}} ,
                0 , --IsUser
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, 1, 0) ,	--IsPerson
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, {{ContactTypeID_Individual}}, {{ContactTypeID_Entity}}) ,	--ContactTypeID 
                C.Title ,
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, C.First_Name, NULL) , -- FirstName
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, C.Company_Surname, NULL) , -- LastName,
                C.Birth_Date ,
                IIF(C.A_B_N IS NULL AND C.A_C_N IS NULL, NULL, C.Company_Surname) , -- EntityName,
                C.Trading_Name ,
                C.A_B_N ,
                C.A_C_N ,
                C.Drivers_Licence ,
                C.Person_Id ,    -- Pulse ID
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                A.Full_Debt_Code ,
                C.Debtor_Code
        FROM    RC_DEBTOR C
                INNER JOIN tblContact ON tblContact.Z_REF2 = C.Debtor_Code and tblContact.LoadID = {{LoadID}}
                INNER JOIN RC_ACCOUNT_EXTRACT A ON C.Debt_Code = A.Full_Debt_Code
                INNER JOIN tblAccount ON tblAccount.AccountNumberPrevious = A.Full_Debt_Code
                                         AND tblAccount.LoadID = {{LoadID}}
        ORDER BY C.Debtor_Code ASC ,
                A.Full_Debt_Code ASC
;