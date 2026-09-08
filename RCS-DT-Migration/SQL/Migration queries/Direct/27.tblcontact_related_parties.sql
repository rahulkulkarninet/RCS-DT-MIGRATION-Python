INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
        ( LoadID ,
          IsUser ,
          IsPerson ,
          ContactTypeID ,  
          FirstName,
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
                IIF(A_B_N IS NULL, 1, 0) ,	--IsPerson
                IIF(A_B_N IS NULL, {{ContactTypeID_Individual}}, {{ContactTypeID_Entity}}) ,	--ContactTypeID 
                First_Name,
                Last_Name ,
                Date_Of_Birth ,                
                1 ,                                
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                Extended_Debt_Code ,
                ZID ,
                NULL
        FROM    RC_RELATEDPARTY RPA

        WHERE   EXISTS ( SELECT  1
                         FROM    tblAccount A WITH ( NOLOCK )
                         WHERE   A.AccountNumberPrevious = RPA.Extended_Debt_Code
                                 AND A.LoadID = {{LoadID}} )
;