INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
       ( LoadID ,
         IsUser ,
         IsPerson ,
         ContactTypeID ,          
         LastName ,
         DOB ,          
         IsTemporaryPassword ,
         CreateID ,
         CreateSessionID ,
         CreateTS ,
         StatusID ,
         Z_REF ,
         Z_REF2 ,
         Z_REF3
       )
        SELECT DISTINCT
                {{LoadID}} ,
                0 , --IsUser
                NULL ,    --IsPerson
                ISNULL({{ContactTypeID_3PDM}}, 5) ,    --ContactTypeID
                RC.Representative_Name ,
                RC.Representative_Date_Of_Birth ,                
                1 ,                                
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                A.Full_Debt_Code ,
                NULL ,
                ContactID AS DebtrakContactID -- Link to Primary Contact
        FROM    RC_DEBTOR RC
        INNER JOIN tblAccount ON tblAccount.AccountNumberPrevious = RC.Debt_Code AND tblAccount.LoadID = {{LoadID}}
        INNER JOIN tblContact C ON RC.Debtor_Code = C.Z_REF2 and C.LoadID = {{LoadID}}
        INNER JOIN RC_ACCOUNT_EXTRACT A ON C.Z_REF = A.Full_Debt_Code
        WHERE   Contact_Rep_First = 'Yes' 
;
