-- Use a temporary table instead of table variable for dynamic SQL
DECLARE @sql NVARCHAR(MAX) = ''
DECLARE @loadid INT = 5452
DECLARE @sessionid NVARCHAR(100) = '72190'

-- Create temporary table (accessible in dynamic SQL)
IF OBJECT_ID('tempdb..#results') IS NOT NULL DROP TABLE #results
CREATE TABLE #results (
    TableName NVARCHAR(128),
    Filteredrowcount INT,
    HasLoadid BIT,
    Hascreatesessionid BIT,
    Hassessionid BIT,
    FilterCondition NVARCHAR(500)
)

SELECT @sql = @sql +
    'INSERT INTO #results (TableName, Filteredrowcount, HasLoadid,Hascreatesessionid, Hassessionid, FilterCondition) ' +
    'SELECT ''' + sub.TABLE_NAME + ''', COUNT(*), ' +
    CAST(sub.HasLoadid AS VARCHAR(1)) + ', ' +
    CAST(sub.Hascreatesessionid AS VARCHAR(1)) + ', ' +
    CAST(sub.Hassessionid AS VARCHAR(1)) + ', ''' +
    CASE 
        WHEN sub.HasLoadID = 1 AND sub.Hassessionid = 1 AND sub.Hascreatesessionid = 1 THEN 'loadid or sessionid or createsessionid exists'
        WHEN sub.HasLoadID = 1 AND sub.Hassessionid = 1 THEN 'loadid or sessionid exists'
        WHEN sub.HasLoadID = 1 AND sub.Hascreatesessionid = 1 THEN 'loadid or createsessionid exists'
        WHEN sub.Hassessionid = 1 AND sub.Hascreatesessionid = 1 THEN 'sessionid or createsessionid exists'
        WHEN sub.HasLoadid = 1 THEN 'loadid only'
        WHEN sub.Hascreatesessionid = 1 THEN 'createsessionid only'
        WHEN sub.Hassessionid = 1 THEN 'sessionid only'
        ELSE 'none'
    END + ''' ' +
    'FROM [' + sub.Table_Schema + '].[' + sub.Table_Name + '] t ' +
    'WHERE ' +
    CASE 
        WHEN sub.HasLoadid = 1 AND sub.Hassessionid = 1 AND sub.Hascreatesessionid = 1 THEN 
            '(t.[loadid] = ' + CAST(@loadid AS VARCHAR(10)) + ' OR t.[createsessionid] = ''' + @sessionid + ''' OR t.[sessionid] = ''' + @sessionid + ''')'
        WHEN sub.HasLoadid = 1 AND sub.Hassessionid = 1 THEN 
            '(t.[loadid] = ' + CAST(@loadid AS VARCHAR(10)) + ' OR t.[sessionid] = ''' + @sessionid + ''')'
        WHEN sub.HasLoadid = 1 AND sub.Hascreatesessionid = 1 THEN 
            '(t.[loadid] = ' + CAST(@loadid AS VARCHAR(10)) + ' OR t.[createsessionid] = ''' + @sessionid + ''')'
        WHEN sub.Hassessionid = 1 AND sub.Hascreatesessionid = 1 THEN 
            '(t.[sessionid] = ''' + @sessionid + ''' OR t.[createsessionid] = ''' + @sessionid + ''')'
        WHEN sub.HasLoadid = 1 THEN 
            't.[loadid] = ' + CAST(@loadid AS VARCHAR(10))
        WHEN sub.Hascreatesessionid = 1 THEN 
            't.[createsessionid] = ''' + @sessionid + ''''
        WHEN sub.Hassessionid = 1 THEN 
            't.[sessionid] = ''' + @sessionid + ''''
        ELSE '1=0'
    END + '; ' + CHAR(13)
FROM (
    SELECT DISTINCT
        t.TABLE_NAME,
        t.TABLE_SCHEMA,
        MAX(CASE WHEN LOWER(c.COLUMN_NAME) = 'loadid' THEN 1 ELSE 0 END) AS HasLoadID,
        MAX(CASE WHEN LOWER(c.COLUMN_NAME) = 'createsessionid' THEN 1 ELSE 0 END) AS Hascreatesessionid,
        MAX(CASE WHEN LOWER(c.COLUMN_NAME) = 'sessionid' THEN 1 ELSE 0 END) AS Hassessionid
    FROM INFORMATION_SCHEMA.TABLES t
    INNER JOIN INFORMATION_SCHEMA.COLUMNS c
        ON t.TABLE_NAME = c.TABLE_NAME
        AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
    WHERE t.TABLE_TYPE = 'BASE TABLE'
        AND (LOWER(c.COLUMN_NAME) = 'loadid' OR LOWER(c.COLUMN_NAME) = 'createsessionid' OR LOWER(c.COLUMN_NAME) = 'sessionid')
    GROUP BY t.TABLE_NAME, t.TABLE_SCHEMA
) sub
ORDER BY sub.TABLE_NAME

-- Check if we have any SQL to execute
IF LEN(@sql) > 0
BEGIN
    -- Print the generated SQL for debugging
    PRINT 'Generated SQL:'
    PRINT @sql
    
    -- Execute the dynamic SQL
    EXEC sp_executesql @sql

    -- Display results
    SELECT
        TableName,
        Filteredrowcount,
        FilterCondition,
        CASE WHEN HasLoadid = 1 THEN 'YES' ELSE 'NO' END AS Has_LoadID,
        CASE WHEN Hascreatesessionid = 1 THEN 'YES' ELSE 'NO' END AS Has_CreateSessionID,
        CASE WHEN Hassessionid = 1 THEN 'YES' ELSE 'NO' END AS Has_SessionID,
        CASE
            WHEN HasLoadid = 1 AND Hassessionid = 1 AND Hascreatesessionid = 1 THEN '3 Columns'
            WHEN HasLoadid = 1 AND Hassessionid = 1 THEN 'LoadID + SessionID'
            WHEN HasLoadid = 1 AND Hascreatesessionid = 1 THEN 'LoadID + CreateSessionID'
            WHEN Hassessionid = 1 AND Hascreatesessionid = 1 THEN 'SessionID + CreateSessionID'
            WHEN HasLoadid = 1 THEN 'LoadID only'
            WHEN Hascreatesessionid = 1 THEN 'CreateSessionID only'
            WHEN Hassessionid = 1 THEN 'SessionID only'
            ELSE 'Neither'
        END AS [Column_Type]
    FROM #results
    ORDER BY TableName
END
ELSE 
BEGIN
    SELECT 'No tables found with LoadID or CreateSessionID columns' AS Message
END

-- Clean up temporary table
DROP TABLE #results