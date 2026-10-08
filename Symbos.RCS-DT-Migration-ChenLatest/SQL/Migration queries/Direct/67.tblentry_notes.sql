IF NOT EXISTS ( SELECT  1
                FROM    RC_STAGING_NOTES_ACCOUNT WITH ( NOLOCK ) )
   AND EXISTS ( SELECT  1
                FROM    RC_NOTES_EXTRACT WITH ( NOLOCK ) )
    BEGIN
        RAISERROR('RC_STAGING_NOTES_ACCOUNT is empty but RC_NOTES_EXTRACT is populated - the staging load did not consolidate the notes.', 16, 1);
        RETURN;
    END
;



DECLARE @BeforeRows BIGINT ,
        @BeforeBytes BIGINT;

SELECT  @BeforeRows = COUNT_BIG(*) ,
        @BeforeBytes = ISNULL(SUM(DATALENGTH(E.[Entry])), 0)
FROM    tblEntry E WITH ( NOLOCK )
WHERE   E.LoadID = {{LoadID}}
        AND E.EntryTypeID = 45;


INSERT  INTO tblEntry WITH ( TABLOCK )
        ( EntryTypeID ,
          EntryStatusID ,
          AccountID ,
          [Entry] ,
          EntryDate ,
          CreateID ,
          CreateSessionID ,
          CreateTS ,
          StatusID ,
          LoadID
        )
        SELECT  45 ,
                1 ,
                A.AccountID ,
                N.[Entry] ,
                -- NOT NULL in tblEntry, and LastNoteDate is nullable here. Measured as
                -- zero nulls on testse; the guard costs nothing and removes the
                -- question.
                ISNULL(N.LastNoteDate, GETDATE()) ,
                {{DefaultOperatorContactID}} ,
                {{CurrentSessionID}} ,
                ISNULL(N.LastNoteDate, GETDATE()) ,
                1 ,
                {{LoadID}}
        FROM    tblAccount A WITH ( NOLOCK )
                CROSS APPLY ( VALUES ( TRY_CONVERT(INT, A.AccountNumberPrevious) ) )
                    AS K ( MatchKey )
                INNER JOIN RC_STAGING_NOTES_ACCOUNT N WITH ( NOLOCK )
                    ON N.Extended_Debt_Code = K.MatchKey
        WHERE   A.LoadID = {{LoadID}}
                AND K.MatchKey IS NOT NULL
        OPTION  ( RECOMPILE );

DECLARE @Expected BIGINT ,
        @ExpectedBytes BIGINT;

SELECT  @Expected = COUNT_BIG(*) ,
        @ExpectedBytes = ISNULL(SUM(DATALENGTH(N.[Entry])), 0)
FROM    RC_STAGING_NOTES_ACCOUNT N WITH ( NOLOCK )
WHERE   EXISTS ( SELECT 1
                 FROM   tblAccount A WITH ( NOLOCK )
                 WHERE  A.LoadID = {{LoadID}}
                        AND TRY_CONVERT(INT, A.AccountNumberPrevious)
                            = N.Extended_Debt_Code );

DECLARE @Written BIGINT ,
        @WrittenBytes BIGINT;

SELECT  @Written = COUNT_BIG(*) - @BeforeRows ,
        @WrittenBytes = ISNULL(SUM(DATALENGTH(E.[Entry])), 0) - @BeforeBytes
FROM    tblEntry E WITH ( NOLOCK )
WHERE   E.LoadID = {{LoadID}}
        AND E.EntryTypeID = 45;

IF @Written <> @Expected
   OR @WrittenBytes <> @ExpectedBytes
    BEGIN
        DECLARE @Message NVARCHAR(400) =
            N'Consolidated notes did not reach tblEntry intact: expected '
            + CAST(@Expected AS NVARCHAR(20)) + N' row(s) totalling '
            + CAST(@ExpectedBytes AS NVARCHAR(20)) + N' byte(s), wrote '
            + CAST(@Written AS NVARCHAR(20)) + N' row(s) totalling '
            + CAST(@WrittenBytes AS NVARCHAR(20))
            + N'. This file is rolled back; investigate before re-running.';
        RAISERROR(@Message, 16, 1);
    END
;
