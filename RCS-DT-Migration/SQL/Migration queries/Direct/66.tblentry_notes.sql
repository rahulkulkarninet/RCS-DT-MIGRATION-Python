-- Notes -> tblEntry. The largest step in the transform: ~8M source rows, and the
-- single 8M-row INSERT it used to be took 15+ minutes on Azure SQL.
--
-- Three changes, all shape-preserving. The set of rows inserted is identical to the
-- previous single statement; only the physical execution differs.
--
-- 1. A post-load index on the staging table. RC_NOTES_EXTRACT is a heap with no
--    indexes, so the old plan read all 8M rows with a Table Scan as the hash probe
--    side. RC_* table DDL is immutable, but additive post-load indexes are allowed,
--    and 67/69 join the same column so they benefit too.
--
-- 2. Batched by account instead of one statement. Azure SQL is always FULL recovery
--    with a log-rate governor: 8M rows in one transaction is throttled and cannot
--    truncate mid-flight. Batching lets the log recycle between iterations and makes
--    progress visible in Rows_Affected rather than all-or-nothing.
--
-- 3. TABLOCK rather than ROWLOCK. ROWLOCK forbids lock escalation, so an 8M-row
--    insert held millions of individual lock structures - the opposite of what a bulk
--    insert wants.
--
-- On the cast direction: Extended_Debt_Code is int, AccountNumberPrevious is
-- nvarchar(200), so the two cannot be compared without a conversion somewhere. The
-- conversion is put on the small account side so the staging index can seek; putting
-- it on the staging column would make the new index useless. This is safe because
-- AccountNumberPrevious is fed from RC_ACCOUNT_EXTRACT.Full_Debt_Code, which is an
-- int, so its text form never carries leading zeros or non-numeric characters.

IF NOT EXISTS ( SELECT  1
                FROM    sys.indexes
                WHERE   object_id = OBJECT_ID('RC_NOTES_EXTRACT')
                        AND name = 'IX_RC_NOTES_EXTRACT_Extended_Debt_Code' )
    CREATE NONCLUSTERED INDEX IX_RC_NOTES_EXTRACT_Extended_Debt_Code
        ON RC_NOTES_EXTRACT (Extended_Debt_Code)
        INCLUDE (Operator);
;

DECLARE @AccountsPerBatch INT = 2000;

-- Accounts for this load, numbered so batches are contiguous ranges. Keyed on rn so
-- each iteration is a clustered range scan of a few thousand rows.
DECLARE @Accounts TABLE
    (
      rn INT IDENTITY(1, 1) NOT NULL PRIMARY KEY CLUSTERED ,
      AccountID INT NOT NULL ,
      MatchKey INT NOT NULL
    );

-- TRY_CONVERT, not CONVERT: a non-numeric AccountNumberPrevious would otherwise abort
-- the whole step. The old implicit conversion had the same exposure and no guard.
-- Ordered by the match key on purpose: rn then runs in key order, so each batch of
-- accounts covers a contiguous, non-overlapping slice of Extended_Debt_Code. That is
-- what makes the key-range predicate below a range seek on the staging index.
INSERT  INTO @Accounts
        ( AccountID ,
          MatchKey
        )
        SELECT  A.AccountID ,
                TRY_CONVERT(INT, A.AccountNumberPrevious)
        FROM    tblAccount A WITH ( NOLOCK )
        WHERE   A.LoadID = {{LoadID}}
                AND A.AccountNumberPrevious IS NOT NULL
                AND TRY_CONVERT(INT, A.AccountNumberPrevious) IS NOT NULL
        ORDER BY TRY_CONVERT(INT, A.AccountNumberPrevious);

DECLARE @LowRn INT = 1;
DECLARE @HighRn INT;
DECLARE @LowKey INT;
DECLARE @HighKey INT;
DECLARE @MaxRn INT = ( SELECT   ISNULL(MAX(rn), 0)
                       FROM     @Accounts
                     );

WHILE @LowRn <= @MaxRn
    BEGIN
        SET @HighRn = @LowRn + @AccountsPerBatch - 1;

        -- The key range this batch of accounts spans. Logically redundant - the join
        -- already restricts to these accounts - but it gives the optimizer a seekable
        -- predicate, so each iteration range-seeks the staging index instead of
        -- scanning the whole table. Without it, batching would turn one 8M-row scan
        -- into one scan per batch.
        SELECT  @LowKey = MIN(MatchKey) ,
                @HighKey = MAX(MatchKey)
        FROM    @Accounts
        WHERE   rn BETWEEN @LowRn AND @HighRn;

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
                SELECT  45,
                        1 ,
                        AC.AccountID ,
                        N.Text ,
                        N.Date_Entered ,
                        ISNULL(OM.ContactIDDestination, 1) ,
                        {{CurrentSessionID}} ,
                        N.Date_Entered ,  --GETDATE() ,
                        1 ,
                        {{LoadID}}
                FROM    @Accounts AC
                        INNER JOIN RC_NOTES_EXTRACT N WITH ( NOLOCK )
                            ON N.Extended_Debt_Code = AC.MatchKey
                        LEFT JOIN CSRC_OperatorContactMapping OM
                            ON OM.OperatorCode = N.Operator
                WHERE   AC.rn BETWEEN @LowRn AND @HighRn
                        AND N.Extended_Debt_Code BETWEEN @LowKey AND @HighKey
                OPTION  ( RECOMPILE );

        SET @LowRn = @HighRn + 1;
    END
;
