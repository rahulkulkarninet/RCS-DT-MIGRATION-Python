
INSERT  INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT DISTINCT
            C.ContactID,
            {{ContactDetailTypeID_Email}},
            LTRIM(RTRIM(X.value)) AS Value,
            1,
            1,
            {{CurrentSessionID}},
            C.CreateTS,
            {{LoadID}}
        FROM RC_DEBTOR RCC
        INNER JOIN tblContact C WITH (NOLOCK) ON C.Z_REF2 = RCC.Debtor_Code
        CROSS APPLY STRING_SPLIT(RCC.Email_Addr, '|') X
        WHERE LEN(RCC.Email_Addr) > 0
                AND C.LoadID = {{LoadID}}
                AND LTRIM(RTRIM(X.value)) != ''  -- Filter out empty values
;


/*  The representative's email, on the representative's own contact. Same 3PDM
    join as 32 uses for their phone: REP.Z_REF3 points back at the debtor's
    ContactID, and the debtor is matched on debt as well as debtor code so the
    address cannot fan out across every debt sharing that debtor.
*/
INSERT  INTO tblContactDetail WITH ( ROWLOCK )
        ( ContactID ,
          ContactDetailTypeID ,
          ContactDetail ,
          IsPrimary ,
          StatusID ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          LoadID
        )
        SELECT  REP.ContactID ,
                {{ContactDetailTypeID_Email}} ,
                LTRIM(RTRIM(X.value)) AS Value ,
                MAX(CASE WHEN LTRIM(RTRIM(ISNULL(RC.Contact_Rep_First, ''))) = 'Yes'
                         THEN 1 ELSE 0 END) ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                MIN(REP.CreateTS) ,
                {{LoadID}}
        FROM    RC_DEBTOR RC
                INNER JOIN tblContact C WITH ( NOLOCK )
                        ON C.Z_REF2 = RC.Debtor_Code
                           AND C.Z_REF = CONVERT(NVARCHAR(400), RC.Debt_Code)
                           AND C.LoadID = {{LoadID}}
                INNER JOIN tblContact REP WITH ( NOLOCK )
                        ON TRY_CONVERT(INT, REP.Z_REF3) = C.ContactID
                           AND REP.LoadID = {{LoadID}}
                           AND REP.ContactTypeID = {{ContactTypeID_3PDM}}
                CROSS APPLY STRING_SPLIT(RC.[Email], '|') X
        WHERE   LEN(ISNULL(RC.[Email], '')) > 0
                AND LTRIM(RTRIM(X.value)) != ''  -- Filter out empty values
        GROUP BY REP.ContactID ,
                LTRIM(RTRIM(X.value))
;
