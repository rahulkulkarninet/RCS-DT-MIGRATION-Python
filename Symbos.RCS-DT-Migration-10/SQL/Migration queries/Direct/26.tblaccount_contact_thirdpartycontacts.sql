
INSERT  INTO dbo.tblAccount_Contact WITH ( ROWLOCK )
        ( AccountID ,
          ContactID ,
          RelationshipID ,
          RelationshipDesc ,
          Related_ContactID ,
          StatusID ,
          InactiveID ,
          InactiveSessionID ,
          InactiveTS ,
          CreateID ,
          CreateSessionID ,
          CreateTS
        )
        SELECT  A.AccountID ,
                REP.ContactID ,
                {{RelationshipID_3PDM}} ,
                NULLIF(LTRIM(RTRIM(RC.Debtor_Relationship)), '') ,
                C.ContactID ,   -- Related_ContactID: the debtor represented
                IIF(Closed.EndTS IS NULL, 1, 0) ,   --StatusID
                IIF(Closed.EndTS IS NULL, NULL, 1) ,                    --InactiveID
                IIF(Closed.EndTS IS NULL, NULL, {{CurrentSessionID}}) , --InactiveSessionID
                Closed.EndTS ,
                1 ,
                {{CurrentSessionID}} ,
                GETDATE()
        FROM    tblContact REP WITH ( NOLOCK )
                INNER JOIN tblContact C WITH ( NOLOCK )
                        ON C.ContactID = TRY_CONVERT(INT, REP.Z_REF3)
                           AND C.LoadID = {{LoadID}}
                           AND C.StatusID = 1
                INNER JOIN tblAccount A WITH ( NOLOCK )
                        ON A.AccountNumberPrevious = C.Z_REF
                           AND A.LoadID = {{LoadID}}
                INNER JOIN RC_DEBTOR RC
                        ON RC.Debtor_Code = C.Z_REF2
                           AND C.Z_REF = CONVERT(NVARCHAR(400), RC.Debt_Code)
                -- An end date still in the future is an engagement that has not
                -- finished yet, so only a date on or before today closes the row.
                CROSS APPLY ( VALUES ( TRY_CONVERT(DATETIME,
                                                   NULLIF(LTRIM(RTRIM(RC.Rep_End_Dte)), ''),
                                                   120) ) ) AS Ends ( EndTS )
                CROSS APPLY ( VALUES ( IIF(Ends.EndTS <= GETDATE(), Ends.EndTS,
                                           NULL) ) ) AS Closed ( EndTS )
        WHERE   REP.LoadID = {{LoadID}}
                AND REP.StatusID = 1
                AND REP.ContactTypeID = {{ContactTypeID_3PDM}}
                AND REP.Z_REF3 IS NOT NULL      -- written only by 25
;

/*
    Who is approached first.

    Where the pointer lives: on the DEBTOR's tblAccount_Contact row, naming the
    representative. That is how spAccount_ContactUpdatePrimaryRelatedContact
    writes it - it updates the row of @ContactID and stores
    @Primary_Related_ContactID - and how it reads it back, by looking up the
    representative's own row through Related_ContactID when the pointer is
    cleared.

    The relationship swap mirrors spAccount_Contact_3PDM_RelationshipSwap. On a
    host that files 3PDM contacts under the primary-debtor relationship - dev,
    uat and testse all have RelationshipID_3PDM = RelationshipID_3PDM_Adhoc =
    RelationshipID_PrimaryDebtor = 1 - the application demotes the debtor to
    vwHost2.SecondaryRelationshipID_3PDM and keeps the original relationship in
    Secondary_RelationshipID, so the representative holds the primary slot. On a
    host that keeps 3PDM as a relationship of its own (v10: 11 and 12) the swap
    proc does nothing, and neither does the guard below - only the pointer is
    set. The guard is the proc's own condition, evaluated on substituted host
    values, so it costs nothing at run time.

    One deliberate difference from the application: spAccount_ContactSave swaps
    on every 3PDM save, whether or not that representative is the one to be
    approached. Doing the same here would demote a debtor who is still the
    person to ring, purely because someone else is on file, so the swap is tied
    to the flags instead. No extract seen so far records a representative
    without them, so nothing in the current data turns on the difference.

    Contact_Rep_First and Mail_Rep_First split the decision by channel in
    DebtRak - phone and letter. tblAccount_Contact has one primary related
    contact rather than one per channel, so either flag sets it. Mail_Rep_First
    is unpopulated in every extract seen so far; it is read anyway because an
    account flagged for letters only should still not be written to directly.

    Representatives whose engagement has ended are skipped: the insert above
    left their link inactive, and this follows only active links.
*/
UPDATE  AC WITH ( ROWLOCK )
SET     Primary_Related_ContactID = REP.ContactID ,
        Primary_Related_Contact_ActiveTS = ISNULL(TRY_CONVERT(DATETIME,
                                                              NULLIF(LTRIM(RTRIM(RC.Rep_Start_Dte)), ''),
                                                              120),
                                                  GETDATE()) ,
        -- Right-hand sides read the pre-update row, so the original relationship
        -- moves to Secondary_RelationshipID in the same statement.
        RelationshipID = IIF(Swap.Applies = 1, {{SecondaryRelationshipID_3PDM}},
                             AC.RelationshipID) ,
        Secondary_RelationshipID = IIF(Swap.Applies = 1, AC.RelationshipID,
                                       AC.Secondary_RelationshipID) ,
        ModifyID = 1 ,
        ModifySessionID = {{CurrentSessionID}} ,
        ModifyTS = GETDATE()
FROM    tblAccount_Contact AC
        INNER JOIN tblContact C WITH ( NOLOCK )
                ON C.ContactID = AC.ContactID
                   AND C.LoadID = {{LoadID}}
        INNER JOIN tblContact REP WITH ( NOLOCK )
                ON TRY_CONVERT(INT, REP.Z_REF3) = C.ContactID
                   AND REP.LoadID = {{LoadID}}
                   AND REP.StatusID = 1
                   AND REP.ContactTypeID = {{ContactTypeID_3PDM}}
        INNER JOIN tblAccount_Contact REPAC WITH ( NOLOCK )
                ON REPAC.ContactID = REP.ContactID
                   AND REPAC.AccountID = AC.AccountID
                   AND REPAC.StatusID = 1
        INNER JOIN RC_DEBTOR RC
                ON RC.Debtor_Code = C.Z_REF2
                   AND C.Z_REF = CONVERT(NVARCHAR(400), RC.Debt_Code)
        CROSS APPLY ( VALUES ( IIF({{RelationshipID_3PDM}} = {{RelationshipID_3PDM_Adhoc}}
                                   AND {{RelationshipID_3PDM}} = {{RelationshipID_PrimaryDebtor}},
                                   1, 0) ) ) AS Swap ( Applies )
WHERE   AC.StatusID = 1
        AND ( LTRIM(RTRIM(RC.Contact_Rep_First)) = 'Yes'
              OR LTRIM(RTRIM(RC.Mail_Rep_First)) = 'Yes'
            )
;
