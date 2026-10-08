/*
    DT Find Delete Blockers
    -----------------------
    Read-only. Lists every child table holding rows that will raise Msg 547 when
    "DT Delete Migrated Data" runs for a given LoadID.

    Why this exists: comparing the migration's INSERTs against the delete script only
    finds tables the migration itself writes to. Tables the application populates against
    migrated rows (tblBankAccount_Contact was the first) are invisible to that comparison
    and only surface one 547 at a time, one full run apart.

    Method: for every single-column FK whose PARENT table carries a LoadID column, count
    the child rows pointing at parent rows in this load. Anything with BlockingRows > 0
    needs either a batch delete in DT Delete Migrated Data.sql (placed before its parent's
    delete) or a NOCHECK entry if the rows are meant to survive.

    Note: child tables the delete script ALREADY handles still appear here - it reports the
    data, not the script. Cross-check the list against the deletes before adding anything.
*/

SET NOCOUNT ON;

DECLARE @LoadID INT = $(LoadID);   -- or hardcode, e.g. DECLARE @LoadID INT = 42;

IF OBJECT_ID('tempdb..#Blockers') IS NOT NULL DROP TABLE #Blockers;
CREATE TABLE #Blockers
    (
      ParentTable   SYSNAME ,
      ChildTable    SYSNAME ,
      FKName        SYSNAME ,
      ChildColumn   SYSNAME ,
      BlockingRows  INT
    );

DECLARE @ParentTable SYSNAME ,
        @ChildTable  SYSNAME ,
        @FKName      SYSNAME ,
        @ParentCol   SYSNAME ,
        @ChildCol    SYSNAME ,
        @sql         NVARCHAR(MAX);

DECLARE FKCursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT  QUOTENAME(ps.name) + '.' + QUOTENAME(pt.name) ,
            QUOTENAME(cs.name) + '.' + QUOTENAME(ct.name) ,
            fk.name ,
            QUOTENAME(pc.name) ,
            QUOTENAME(cc.name)
    FROM    sys.foreign_keys fk
            INNER JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
            INNER JOIN sys.tables ct ON ct.object_id = fk.parent_object_id
            INNER JOIN sys.schemas cs ON cs.schema_id = ct.schema_id
            INNER JOIN sys.columns cc ON cc.object_id = fkc.parent_object_id
                                     AND cc.column_id = fkc.parent_column_id
            INNER JOIN sys.tables pt ON pt.object_id = fk.referenced_object_id
            INNER JOIN sys.schemas ps ON ps.schema_id = pt.schema_id
            INNER JOIN sys.columns pc ON pc.object_id = fkc.referenced_object_id
                                     AND pc.column_id = fkc.referenced_column_id
    WHERE   EXISTS ( SELECT 1                       -- parent is load-scoped
                     FROM   sys.columns lc
                     WHERE  lc.object_id = pt.object_id
                            AND lc.name = 'LoadID' )
            AND ( SELECT COUNT(*)                   -- single-column FKs only
                  FROM   sys.foreign_key_columns x
                  WHERE  x.constraint_object_id = fk.object_id ) = 1
            AND fk.delete_referential_action = 0    -- no ON DELETE CASCADE: those look after themselves
            AND pt.object_id <> ct.object_id;       -- skip self-references

OPEN FKCursor;
FETCH NEXT FROM FKCursor INTO @ParentTable, @ChildTable, @FKName, @ParentCol, @ChildCol;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = N'
        INSERT INTO #Blockers (ParentTable, ChildTable, FKName, ChildColumn, BlockingRows)
        SELECT @p, @c, @f, @cc, COUNT_BIG(*)
        FROM ' + @ChildTable + N' ch WITH (NOLOCK)
        INNER JOIN ' + @ParentTable + N' p WITH (NOLOCK) ON p.' + @ParentCol + N' = ch.' + @ChildCol + N'
        WHERE p.LoadID = @LoadID
        HAVING COUNT_BIG(*) > 0;';

    EXEC sp_executesql @sql ,
        N'@LoadID INT, @p SYSNAME, @c SYSNAME, @f SYSNAME, @cc SYSNAME' ,
        @LoadID = @LoadID, @p = @ParentTable, @c = @ChildTable, @f = @FKName, @cc = @ChildCol;

    FETCH NEXT FROM FKCursor INTO @ParentTable, @ChildTable, @FKName, @ParentCol, @ChildCol;
END

CLOSE FKCursor;
DEALLOCATE FKCursor;

SELECT      ParentTable ,
            ChildTable ,
            FKName ,
            ChildColumn ,
            BlockingRows
FROM        #Blockers
ORDER BY    ParentTable, BlockingRows DESC;

/*
    Section 2: the full dependency closure.

    The count above only reaches ONE level down from a load-scoped table. When a blocker is
    itself load-scoped (tblContact) that is enough, because the next level gets counted on
    its own row. When it is NOT (tblHardship has no LoadID column), anything referencing it
    is invisible to section 1 and will only appear as the next Msg 547.

    This walks the reference graph outward from tblAccount and tblContact and lists every
    table that depends on them, directly or transitively, with its depth. Compare the list
    against the deletes in DT Delete Migrated Data.sql: any table here with no delete block
    is a 547 waiting for the right data to exist.
*/
WITH FKEdge AS (
    SELECT  DISTINCT
            parent_object_id  AS ChildID ,
            referenced_object_id AS ParentID
    FROM    sys.foreign_keys
    WHERE   delete_referential_action = 0        -- cascading FKs clear themselves
            AND parent_object_id <> referenced_object_id
),
Closure AS (
    SELECT      e.ChildID ,
                e.ParentID ,
                1 AS Depth ,
                CAST(OBJECT_NAME(e.ParentID) AS NVARCHAR(4000)) AS Path
    FROM        FKEdge e
    WHERE       OBJECT_NAME(e.ParentID) IN ('tblAccount', 'tblContact')
    UNION ALL
    SELECT      e.ChildID ,
                e.ParentID ,
                c.Depth + 1 ,
                CAST(c.Path + N' -> ' + OBJECT_NAME(e.ParentID) AS NVARCHAR(4000))
    FROM        FKEdge e
                INNER JOIN Closure c ON c.ChildID = e.ParentID
    WHERE       c.Depth < 6                       -- guard against FK cycles
                AND c.Path NOT LIKE N'%' + OBJECT_NAME(e.ParentID) + N'%'
)
SELECT      OBJECT_NAME(ChildID) AS DependentTable ,
            MIN(Depth) AS ShortestDepth ,
            MIN(Path) AS ReachedVia ,
            ( SELECT SUM(p.rows)
              FROM   sys.partitions p
              WHERE  p.object_id = Closure.ChildID
                     AND p.index_id IN (0, 1) ) AS TotalRowsInTable
FROM        Closure
GROUP BY    ChildID
ORDER BY    MIN(Depth), OBJECT_NAME(ChildID);

-- Multi-column FKs are skipped in section 1; list them so they can be checked by hand.
SELECT      fk.name AS FKName ,
            QUOTENAME(cs.name) + '.' + QUOTENAME(ct.name) AS ChildTable ,
            QUOTENAME(ps.name) + '.' + QUOTENAME(pt.name) AS ParentTable
FROM        sys.foreign_keys fk
            INNER JOIN sys.tables ct ON ct.object_id = fk.parent_object_id
            INNER JOIN sys.schemas cs ON cs.schema_id = ct.schema_id
            INNER JOIN sys.tables pt ON pt.object_id = fk.referenced_object_id
            INNER JOIN sys.schemas ps ON ps.schema_id = pt.schema_id
WHERE       ( SELECT COUNT(*)
              FROM   sys.foreign_key_columns x
              WHERE  x.constraint_object_id = fk.object_id ) > 1
            AND EXISTS ( SELECT 1
                         FROM   sys.columns lc
                         WHERE  lc.object_id = pt.object_id
                                AND lc.name = 'LoadID' );

DROP TABLE #Blockers;
