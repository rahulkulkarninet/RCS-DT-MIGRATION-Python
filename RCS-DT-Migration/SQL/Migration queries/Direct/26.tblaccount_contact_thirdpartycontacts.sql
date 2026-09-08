
INSERT  INTO  tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          Related_ContactID ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS,
          Primary_Related_ContactID,
          Primary_Related_Contact_ActiveTS
        )

    SELECT 
        A.AccountID ,
        C.ContactID ,
        ISNULL({{RelationshipID_3PDM}}, 11),
        D.ContactID ,
        1 ,
        1,
        {{CurrentSessionID}} ,
        GETDATE(),
        D.ContactID Primary_Related_ContactID,
        RC.Rep_Start_Dte Primary_Related_Contact_ActiveTS
        
        FROM    RC_DEBTOR RC
        INNER JOIN tblAccount A ON A.AccountNumberPrevious = RC.Debt_Code AND A.LoadID = {{LoadID}}
        INNER JOIN tblContact C ON RC.Debtor_Code = C.Z_REF2 and C.LoadID = {{LoadID}}
        INNER JOIN tblContact D on D.Z_REF3 = C.ContactID and D.LoadID = {{LoadID}}
        INNER JOIN RC_ACCOUNT_EXTRACT RCA ON C.Z_REF = RCA.Full_Debt_Code
        INNER JOIN tblAccount_Contact AC  ON AC.ContactID = D.ContactID
        
        WHERE   Contact_Rep_First = 'Yes' 
        AND C.ContactTypeID = {{ContactTypeID_3PDM}}
        AND AC.RelationshipID = 1 -- PrimaryDebtor
        AND C.StatusID = 1     
;