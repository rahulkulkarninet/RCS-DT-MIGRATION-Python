/*
    tblEntry write cost — the index and change-tracking side of 66.tblentry_notes.

    ADDITIVE ONLY is not possible here: this script drops and rebuilds indexes.
    NOT run by Run_Migration.py.

    Sections 1 to 3 are safe to run top to bottom on any environment. Every step
    is guarded on what that database actually carries and on the step before it,
    so running it twice, or on an environment a step does not apply to, prints
    what it skipped and changes nothing. Section 3 additionally refuses to run
    before section 2 has.

    Section 4 is deliberately not executable. It cannot be undone cleanly and
    needs a conversation first.

    ---------------------------------------------------------------------------
    0. Why
    ---------------------------------------------------------------------------
    66.tblentry_notes inserts every note in the extract into tblEntry - millions
    of rows per customer. Query Store on testse measured the batch INSERT at
    150-456 s per execution, 10-27 million logical reads, memory grants between
    1 MB and 5 GB for the same statement, and up to 1.3 GB spilled to tempdb.

    The plan says why: the read side is a nested-loops seek and costs almost
    nothing. Every row then has to be written into the clustered index, each
    nonclustered index, and - where it is enabled - the change-tracking side
    table. Most of those go through a Sort and an Eager Spool. Batching by note
    row count (in 66.tblentry_notes) made that work uniform; this script reduces
    how much of it there is.

    Index counts and sizes differ per environment, so nothing below is hardcoded
    to one list. Measured 2026-09-04:

        uat / dev-debtrak    14 nonclustered, PK 11.41 GB, no change tracking
        testse / test-debtrak 15 nonclustered, PK 4.29 GB, change tracking ON

    ---------------------------------------------------------------------------
    1. Report first - what applies here
    ---------------------------------------------------------------------------
*/

/* Provably redundant indexes: keys are a leading prefix of another index's keys
   AND every include is covered by that index. Every seek they serve, the wider
   index serves. This finds them rather than trusting a list, because the two
   environments do not carry the same indexes. */
SELECT      redundant.name                        AS drop_candidate,
            CAST(SUM(rp.reserved_page_count) * 8 / 1024.0 / 1024.0
                 AS DECIMAL(10, 2))               AS gb_reclaimed,
            covering.name                         AS served_instead_by
FROM        sys.indexes redundant
JOIN        sys.indexes covering
              ON covering.object_id = redundant.object_id
             AND covering.index_id <> redundant.index_id
LEFT JOIN   sys.dm_db_partition_stats rp
              ON rp.object_id = redundant.object_id
             AND rp.index_id = redundant.index_id
WHERE       redundant.object_id = OBJECT_ID('dbo.tblEntry')
            AND redundant.type = 2
            AND redundant.is_unique = 0
            AND redundant.is_primary_key = 0
            /* redundant's keys are a leading prefix of covering's keys */
            AND NOT EXISTS ( SELECT 1
                             FROM   sys.index_columns rc
                             WHERE  rc.object_id = redundant.object_id
                                    AND rc.index_id = redundant.index_id
                                    AND rc.is_included_column = 0
                                    AND NOT EXISTS ( SELECT 1
                                                     FROM   sys.index_columns cc
                                                     WHERE  cc.object_id = covering.object_id
                                                            AND cc.index_id = covering.index_id
                                                            AND cc.is_included_column = 0
                                                            AND cc.column_id = rc.column_id
                                                            AND cc.key_ordinal = rc.key_ordinal ) )
            /* and its includes are covered by covering's keys or includes */
            AND NOT EXISTS ( SELECT 1
                             FROM   sys.index_columns rc
                             WHERE  rc.object_id = redundant.object_id
                                    AND rc.index_id = redundant.index_id
                                    AND rc.is_included_column = 1
                                    AND NOT EXISTS ( SELECT 1
                                                     FROM   sys.index_columns cc
                                                     WHERE  cc.object_id = covering.object_id
                                                            AND cc.index_id = covering.index_id
                                                            AND cc.column_id = rc.column_id ) )
GROUP BY    redundant.name, covering.name;

/* Indexes carrying an LOB column as an include. One of these on tblEntry is the
   single most expensive nonclustered index on the table, because every note's
   full text is written into it as well as into the row. */
SELECT      i.name                                AS index_name,
            c.name                                AS lob_include,
            ty.name                               AS type_name,
            CAST(SUM(ps.reserved_page_count) * 8 / 1024.0 / 1024.0
                 AS DECIMAL(10, 2))               AS gb
FROM        sys.indexes i
JOIN        sys.index_columns ic
              ON ic.object_id = i.object_id AND ic.index_id = i.index_id
             AND ic.is_included_column = 1
JOIN        sys.columns c
              ON c.object_id = ic.object_id AND c.column_id = ic.column_id
JOIN        sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN   sys.dm_db_partition_stats ps
              ON ps.object_id = i.object_id AND ps.index_id = i.index_id
WHERE       i.object_id = OBJECT_ID('dbo.tblEntry')
            AND c.max_length = -1
GROUP BY    i.name, c.name, ty.name;

/* Is the migration paying for change tracking on this table, and is anything
   reading it? A migration is not an incremental sync: with retention at 2 days
   and auto-cleanup on, rows written during a load are deleted again two days
   later without anyone having read them. */
SELECT      CASE WHEN EXISTS ( SELECT 1
                               FROM   sys.change_tracking_tables
                               WHERE  object_id = OBJECT_ID('dbo.tblEntry') )
                 THEN 'ENABLED' ELSE 'not enabled'
            END                                   AS change_tracking_on_tblEntry,
            ( SELECT  retention_period
              FROM    sys.change_tracking_databases
              WHERE   database_id = DB_ID() )     AS retention_period,
            ( SELECT  retention_period_units_desc
              FROM    sys.change_tracking_databases
              WHERE   database_id = DB_ID() )     AS retention_units;

/*
    ---------------------------------------------------------------------------
    2. Drop the LOB include - run this BEFORE section 3
    ---------------------------------------------------------------------------
    IX_tblEntry_CreateTS_StatusType is (CreateTS, EntryStatusID, EntryTypeID,
    AccountID) INCLUDE (Entry). Entry is nvarchar(max), so the index is a second
    copy of every note: 9.40 GB on uat against ~0.80 GB for a comparable index
    without the include, and 3.79 GB on testse. Every note inserted is written
    twice, and both writes go through that index's Sort and Eager Spool.

    Rebuilding without the include keeps every seek this index serves. What it
    costs is that a query which both filters on those keys AND returns Entry now
    does a lookup into the clustered index per row instead of reading it from the
    index leaf. On uat this index recorded 0 seeks, 0 scans and 0 lookups against
    426 writes over 136 hours of uptime - but that is a development database, so
    treat it as evidence that nothing in the migration needs the covering, NOT as
    evidence that no production query does. If a production report reads Entry
    filtered by CreateTS, check its plan before and after.

    ONLINE = ON so the rebuild does not block the table; it is slower and needs
    more log. Remove that option on an environment where a brief exclusive lock
    is acceptable.
*/
IF EXISTS ( SELECT  1
            FROM    sys.indexes i
            JOIN    sys.index_columns ic
                      ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                     AND ic.is_included_column = 1
            JOIN    sys.columns c
                      ON c.object_id = ic.object_id AND c.column_id = ic.column_id
            WHERE   i.object_id = OBJECT_ID('dbo.tblEntry')
                    AND i.name = 'IX_tblEntry_CreateTS_StatusType'
                    AND c.max_length = -1 )
BEGIN
    CREATE NONCLUSTERED INDEX IX_tblEntry_CreateTS_StatusType
        ON dbo.tblEntry (CreateTS, EntryStatusID, EntryTypeID, AccountID)
        WITH ( DROP_EXISTING = ON, ONLINE = ON, MAXDOP = 0 );
    PRINT 'Rebuilt IX_tblEntry_CreateTS_StatusType without INCLUDE (Entry)';
END
ELSE
    PRINT 'IX_tblEntry_CreateTS_StatusType already carries no LOB include';
GO

/*
    ---------------------------------------------------------------------------
    3. Drop the redundant indexes section 1 reported
    ---------------------------------------------------------------------------
    Order matters, which is why section 2 comes first. IX_tblEntry_CreateTS
    (CreateTS) is a leading-prefix subset of IX_tblEntry_CreateTS_StatusType on
    both environments, so it is redundant for coverage - but while that index
    still carries INCLUDE (Entry), a CreateTS-only seek would move from a 0.90 GB
    index to a 9.40 GB one, which is not obviously a win. After section 2 they are
    the same shape and the narrow one is pure overhead.

    IX_tblEntry_AccountID (AccountID) is a leading-prefix subset of
    ix_entry_account_entry_date (AccountID, EntryDate) on testse. uat has no such
    index, so there IX_tblEntry_AccountID is the only way to seek by AccountID and
    must stay - the guard below checks rather than assuming.

    Both are recreatable from this script if a plan regresses. Each drop checks
    that its covering index is actually present, so this section is correct on
    either environment and on one where someone has already run it.
*/

/* The second EXISTS is the ordering guard: it refuses to drop the narrow index
   while the wide one still carries the LOB include, because until section 2 has
   run this would send CreateTS seeks to a 9.4 GB index. */
IF EXISTS ( SELECT  1 FROM sys.indexes
            WHERE   object_id = OBJECT_ID('dbo.tblEntry')
                    AND name = 'IX_tblEntry_CreateTS' )
   AND EXISTS ( SELECT 1 FROM sys.indexes
                WHERE  object_id = OBJECT_ID('dbo.tblEntry')
                       AND name = 'IX_tblEntry_CreateTS_StatusType' )
   AND NOT EXISTS ( SELECT 1
                    FROM   sys.indexes i
                    JOIN   sys.index_columns ic
                             ON ic.object_id = i.object_id
                            AND ic.index_id = i.index_id
                            AND ic.is_included_column = 1
                    JOIN   sys.columns c
                             ON c.object_id = ic.object_id
                            AND c.column_id = ic.column_id
                    WHERE  i.object_id = OBJECT_ID('dbo.tblEntry')
                           AND i.name = 'IX_tblEntry_CreateTS_StatusType'
                           AND c.max_length = -1 )
BEGIN
    DROP INDEX IX_tblEntry_CreateTS ON dbo.tblEntry;
    PRINT 'Dropped IX_tblEntry_CreateTS (covered by IX_tblEntry_CreateTS_StatusType)';
    -- Recreate with:
    -- CREATE NONCLUSTERED INDEX IX_tblEntry_CreateTS ON dbo.tblEntry (CreateTS);
END
ELSE
    PRINT 'IX_tblEntry_CreateTS left alone (absent, uncovered, or section 2 not run)';
GO

/* Only redundant where ix_entry_account_entry_date exists - testse has it, uat
   does not, and on uat this is the only way to seek tblEntry by AccountID. */
IF EXISTS ( SELECT  1 FROM sys.indexes
            WHERE   object_id = OBJECT_ID('dbo.tblEntry')
                    AND name = 'IX_tblEntry_AccountID' )
   AND EXISTS ( SELECT 1 FROM sys.indexes
                WHERE  object_id = OBJECT_ID('dbo.tblEntry')
                       AND name = 'ix_entry_account_entry_date' )
BEGIN
    DROP INDEX IX_tblEntry_AccountID ON dbo.tblEntry;
    PRINT 'Dropped IX_tblEntry_AccountID (covered by ix_entry_account_entry_date)';
    -- Recreate with:
    -- CREATE NONCLUSTERED INDEX IX_tblEntry_AccountID ON dbo.tblEntry (AccountID);
END
ELSE
    PRINT 'IX_tblEntry_AccountID left alone (absent, or nothing else covers AccountID)';
GO

/*
    ---------------------------------------------------------------------------
    4. Change tracking - testse only, and the one change that cannot be undone
    ---------------------------------------------------------------------------
    tblEntry is change-tracked on testse and not on uat. Every migrated row
    therefore writes an extra row into the change-tracking side table on testse,
    through its own Sort and Eager Spool, for changes that retention deletes two
    days later.

    DO NOT run this because the migration would be faster. Disabling change
    tracking discards the table's change history, and re-enabling it starts a new
    baseline: any consumer doing an incremental sync off tblEntry must do a full
    reinitialize, and one that does not notice will silently miss every change in
    between. Query Store on uat shows CHANGETABLE queries against other tables, so
    something in this product does consume change tracking.

    Confirm with whoever owns the sync that nothing reads tblEntry's changes, then
    either turn it off permanently:

        ALTER TABLE dbo.tblEntry DISABLE CHANGE_TRACKING;

    or, if it is needed but not during a migration, disable before the run and
    re-enable after - accepting that consumers must reinitialize each time:

        ALTER TABLE dbo.tblEntry ENABLE CHANGE_TRACKING
            WITH ( TRACK_COLUMNS_UPDATED = OFF );

    The middle option - leave it alone - is the right default until that
    conversation has happened.
*/
