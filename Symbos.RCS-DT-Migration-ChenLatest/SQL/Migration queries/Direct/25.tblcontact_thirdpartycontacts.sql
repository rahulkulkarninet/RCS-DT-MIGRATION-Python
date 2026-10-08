
INSERT  INTO dbo.tblContact WITH ( ROWLOCK )
       ( LoadID ,
         IsUser ,
         IsExtranetUser ,
         IsPerson ,
         ContactTypeID ,
         LastName ,
         EntityName ,
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
                0 , --IsExtranetUser (NOT NULL, no default)
                NULL ,    --IsPerson: a representative may be a person or an agency
                {{ContactTypeID_3PDM}} ,    --ContactTypeID
                LTRIM(RTRIM(RC.Representative_Name)) ,  -- LastName: DebtRak holds one unsplit name
                NULLIF(LTRIM(RTRIM(RC.Rep_Other_Info)), '') ,   -- EntityName: the agency the rep acts for
                TRY_CONVERT(DATETIME,
                            NULLIF(LTRIM(RTRIM(RC.Representative_Date_Of_Birth)), ''),
                            120) ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE() ,
                1 ,
                C.Z_REF ,       -- the debt the representative was recorded against
                NULL ,
                C.ContactID     -- Z_REF3: the debtor this representative acts for
        FROM    RC_DEBTOR RC
                -- The debtor contact from 22 already proves the account passed the
                -- retention filter, so this join replaces the tblAccount and
                -- RC_ACCOUNT_EXTRACT ones. Matching on the debt as well as the
                -- debtor keeps one representative per debtor row should a
                -- Debtor_Code ever appear against more than one debt.
                INNER JOIN tblContact C WITH ( NOLOCK )
                        ON C.Z_REF2 = RC.Debtor_Code
                           AND C.Z_REF = CONVERT(NVARCHAR(400), RC.Debt_Code)
                           AND C.LoadID = {{LoadID}}
                           AND C.StatusID = 1
        WHERE   NULLIF(LTRIM(RTRIM(RC.Representative_Name)), '') IS NOT NULL
;
