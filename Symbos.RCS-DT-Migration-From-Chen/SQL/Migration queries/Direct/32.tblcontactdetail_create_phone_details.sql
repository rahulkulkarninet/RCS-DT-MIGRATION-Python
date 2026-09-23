

IF OBJECT_ID('tempdb..#DebtorPhones') IS NOT NULL
    DROP TABLE #DebtorPhones;

SELECT  RC.Debt_Code ,
        RC.Debtor_Code ,
        LTRIM(RTRIM(P.value)) AS Phone ,
        CASE UPPER(LTRIM(RTRIM(ISNULL(T.value, ''))))
          WHEN 'M' THEN {{ContactDetailTypeID_Mobile}}
          WHEN 'W' THEN {{ContactDetailTypeID_Work}}
          WHEN 'H' THEN {{ContactDetailTypeID_Home}}
          ELSE {{ContactDetailTypeID_Mobile}}
        END AS ContactDetailTypeID ,
        CASE WHEN LTRIM(RTRIM(ISNULL(R.value, ''))) = '1' THEN 1 ELSE 0 END AS IsRep ,
        CASE WHEN LTRIM(RTRIM(ISNULL(F.value, ''))) = '1' THEN 1 ELSE 0 END AS IsPreferred ,
        CASE WHEN LTRIM(RTRIM(ISNULL(RC.Contact_Rep_First, ''))) = 'Yes'
             THEN 1 ELSE 0 END AS RepFirst
INTO    #DebtorPhones
FROM    RC_DEBTOR RC
        CROSS APPLY STRING_SPLIT(RC.Phone_Number, '|', 1) P
        OUTER APPLY ( SELECT S.value
                      FROM   STRING_SPLIT(RC.Ph_Type, '|', 1) S
                      WHERE  S.ordinal = P.ordinal ) T
        OUTER APPLY ( SELECT S.value
                      FROM   STRING_SPLIT(RC.[Rep], '|', 1) S
                      WHERE  S.ordinal = P.ordinal ) R
        OUTER APPLY ( SELECT S.value
                      FROM   STRING_SPLIT(RC.Phone_Preferred_Flag, '|', 1) S
                      WHERE  S.ordinal = P.ordinal ) F
WHERE   LEN(ISNULL(RC.Phone_Number, '')) > 0
        AND LTRIM(RTRIM(P.value)) != ''  -- Filter out empty values
;


/*  The debtor's own numbers. Joined on debt as well as debtor code, matching
    the representative insert below - one debtor code can carry several debts,
    and without the debt the numbers fan out across all of them.
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
        SELECT  C.ContactID ,
                DP.ContactDetailTypeID ,
                DP.Phone ,
                MAX(DP.IsPreferred) ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                MIN(C.CreateTS) ,
                {{LoadID}}
        FROM    #DebtorPhones DP
                INNER JOIN tblContact C WITH ( NOLOCK )
                        ON C.Z_REF2 = DP.Debtor_Code
                           AND C.Z_REF = CONVERT(NVARCHAR(400), DP.Debt_Code)
                           AND C.LoadID = {{LoadID}}
        WHERE   DP.IsRep = 0
        GROUP BY C.ContactID ,
                DP.ContactDetailTypeID ,
                DP.Phone
;


/*  The representative's number, on the representative's own contact. Flagged
    primary when Contact_Rep_First says they are approached before the debtor,
    or when the extract marks the number preferred outright.
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
                DP.ContactDetailTypeID ,
                DP.Phone ,
                MAX(CASE WHEN DP.RepFirst = 1 OR DP.IsPreferred = 1
                         THEN 1 ELSE 0 END) ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                MIN(REP.CreateTS) ,
                {{LoadID}}
        FROM    #DebtorPhones DP
                INNER JOIN tblContact C WITH ( NOLOCK )
                        ON C.Z_REF2 = DP.Debtor_Code
                           AND C.Z_REF = CONVERT(NVARCHAR(400), DP.Debt_Code)
                           AND C.LoadID = {{LoadID}}
                INNER JOIN tblContact REP WITH ( NOLOCK )
                        ON TRY_CONVERT(INT, REP.Z_REF3) = C.ContactID
                           AND REP.LoadID = {{LoadID}}
                           AND REP.ContactTypeID = {{ContactTypeID_3PDM}}
        WHERE   DP.IsRep = 1
        GROUP BY REP.ContactID ,
                DP.ContactDetailTypeID ,
                DP.Phone
;


/*  Rep_Home_Ph is empty in every extract seen so far, but it is still the
    column DebtRak documents for a representative's phone, so it is read rather
    than dropped - if a client ever populates it, the number should not vanish.
    Numbers already taken from the Rep-marked multivalue are not repeated.
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
        SELECT DISTINCT
                REP.ContactID ,
                {{ContactDetailTypeID_Home}} ,
                LTRIM(RTRIM(X.value)) AS Value ,
                0 ,
                1 ,
                1 ,
                {{CurrentSessionID}} ,
                REP.CreateTS ,
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
                CROSS APPLY STRING_SPLIT(RC.Rep_Home_Ph, '|') X
        WHERE   LEN(ISNULL(RC.Rep_Home_Ph, '')) > 0
                AND LTRIM(RTRIM(X.value)) != ''  -- Filter out empty values
                AND NOT EXISTS ( SELECT 1
                                 FROM   tblContactDetail CD WITH ( NOLOCK )
                                 WHERE  CD.ContactID = REP.ContactID
                                        AND CD.LoadID = {{LoadID}}
                                        AND CD.ContactDetail = LTRIM(RTRIM(X.value)) )
;

DROP TABLE #DebtorPhones;
