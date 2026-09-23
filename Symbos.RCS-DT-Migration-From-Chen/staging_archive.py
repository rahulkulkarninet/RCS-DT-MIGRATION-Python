"""Archive each customer's staging extract by renaming it, not by copying it.

The staging tables are truncated and reloaded for every customer, so the raw
extract as it was loaded only exists between that customer's load and the next
customer's truncate. This module keeps it - by moving the table itself:

    dbo.RC_ACCOUNT_EXTRACT  ->  archive.SM9641_RC_ACCOUNT_EXTRACT

then rebuilding an empty dbo.RC_ACCOUNT_EXTRACT from its own schema file, all in
one transaction. Renaming is a catalog operation: it costs the same whether the
table holds ten rows or ten million, and it does not care that Azure SQL has no
cross-database queries, because nothing crosses a database. The rows never move.

That is the whole reason this replaced a bcp copy. The archive database lives on
the same server but is a different database, and on Azure SQL that means every
row had to be read out to the client and pushed back - twice across the WAN, for
data that was about to be thrown away by the next truncate anyway.

What the rename cannot do is cross into that archive database, so these tables
accumulate in the environment's own DATABASE. tools/sweep_archive.py moves them
on to ARCHIVE_DATABASE out of band, and nothing in a migration run waits for it.
Until it has run, the table here is the ONLY copy of that customer's extract.

Three things follow from renaming rather than copying, and each is load-bearing:

  The rebuild comes from the schema files, not from sys.columns.
      Nearly every staging table carries one to three nonclustered indexes that
      the migration's own queries depend on - SQL/Schemas/RC_SMS Schema.sql
      records that losing one "turned a 15 second step into hours". Regenerating
      the table from its catalog entry would reproduce the columns and silently
      drop every index. Only the schema file has them.

  The audit values live in archive.ArchiveCatalog, not in columns.
      A renamed table cannot gain LoadID/CreateTS/EntityCode columns without an
      ALTER TABLE ADD, and for an nvarchar NOT NULL DEFAULT that rewrites the
      whole table - which would cost exactly what the rename saves. One catalog
      row per archived table carries them instead.

  The customer code is validated, never sanitised.
      It reaches sp_rename as a string literal rather than a quoted identifier,
      and it originates in a filename in a drop folder. A code that cannot be a
      table name is a broken input: raise, so nobody has to find a mangled
      archive table later.
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Schema of the archive tables and of the catalog, created by
# SQL/Schemas/Migrations/006.archive_schema.sql.
ARCHIVE_SCHEMA = 'archive'
ARCHIVE_CATALOG = 'ArchiveCatalog'

# The migration script that creates both, named in the error a run gets when it
# finds them missing. Here so the two cannot drift apart.
SETUP_COMMAND = 'python tools/deploy_schemas.py <env> --set migrations'

# What a customer code may be, given it ends up in a table name and in an
# sp_rename string literal. Letters and digits, starting with a letter: no
# underscore, so {code}_{table} stays unambiguously parseable back apart.
#
# \Z, not $: in Python $ also matches immediately before a trailing newline, so
# ^...$ would accept "SM9641\n" and pass the newline straight into the DDL this
# builds. The strip() in validate_customer_code catches that one too - this is
# the belt to its braces, and the reason neither was left to the other.
CUSTOMER_CODE_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9]{0,29}\Z')
# Staging table names come from variables/table_keywords.json, but they land in
# the same DDL, so they are held to the same standard.
STAGING_TABLE_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,99}\Z')
MAX_IDENTIFIER = 128

# CreateTS is datetime2(3); see archive_timestamp.
CREATE_TS_SCALE = 3

# Column types SQL Server generates itself; they cannot be given a value.
GENERATED_COLUMN_TYPES = ('timestamp', 'rowversion')

# Column metadata for one table, read from the catalog rather than reflected.
# Used by tools/sweep_archive.py to build a matching table in the archive
# database; the rename path needs no such thing, because the table it moves is
# already the right shape by definition.
_COLUMN_QUERY = """
SELECT c.name              AS column_name,
       ty.name             AS type_name,
       c.max_length        AS max_length,
       c.precision         AS precision_value,
       c.scale             AS scale_value,
       c.is_nullable       AS is_nullable,
       c.is_identity       AS is_identity,
       c.is_computed       AS is_computed,
       CASE WHEN dc.object_id IS NULL THEN 0 ELSE 1 END AS has_default
FROM sys.columns c
JOIN sys.types ty
  ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints dc
  ON dc.parent_object_id = c.object_id
 AND dc.parent_column_id = c.column_id
WHERE c.object_id = OBJECT_ID(:qualified_name)
ORDER BY c.column_id
"""

# Rows per table, without scanning any of them. Accurate here because the table
# is quiescent between the migration finishing and the rename: index_id 0 is a
# heap, 1 a clustered index, and a staging table is one or the other.
_ROW_COUNT_QUERY = """
SELECT t.name                AS table_name,
       SUM(p.row_count)      AS row_count
FROM sys.tables t
JOIN sys.schemas s
  ON s.schema_id = t.schema_id
JOIN sys.dm_db_partition_stats p
  ON p.object_id = t.object_id
WHERE s.name = :schema_name
  AND p.index_id IN (0, 1)
GROUP BY t.name
"""

# Tables that exist in a schema right now.
_TABLE_LIST_QUERY = """
SELECT t.name AS table_name
FROM sys.tables t
JOIN sys.schemas s
  ON s.schema_id = t.schema_id
WHERE s.name = :schema_name
"""

# Views or functions bound WITH SCHEMABINDING to a staging table. sp_rename
# would break them, and it does so without complaint. None exist today; this is
# what notices if one ever does.
_SCHEMA_BOUND_QUERY = """
SELECT OBJECT_NAME(d.referencing_id) AS referencing_object,
       o.name                        AS referenced_table
FROM sys.sql_expression_dependencies d
JOIN sys.objects o
  ON o.object_id = d.referenced_id
JOIN sys.schemas s
  ON s.schema_id = o.schema_id
WHERE d.is_schema_bound_reference = 1
  AND s.name = :schema_name
"""

# Nonclustered indexes on the archived tables. Dropped after the rename commits:
# an archive nobody queries does not need the migration's join indexes, and the
# space they hold is the cost that matters here - these tables accumulate in the
# application's own database until the sweep moves them out. Nonclustered only:
# dropping a clustered index rebuilds the table as a heap, which is real work.
_ARCHIVE_INDEX_QUERY = """
SELECT t.name AS table_name,
       i.name AS index_name
FROM sys.indexes i
JOIN sys.tables t
  ON t.object_id = i.object_id
JOIN sys.schemas s
  ON s.schema_id = t.schema_id
WHERE s.name = :schema_name
  AND i.type_desc = 'NONCLUSTERED'
  AND i.name IS NOT NULL
  AND i.is_primary_key = 0
  AND i.is_unique_constraint = 0
  AND t.name <> :catalog_table
"""

# Character types whose sys.columns.max_length is in bytes at 2 bytes per char.
_DOUBLE_BYTE_TYPES = ('nvarchar', 'nchar')
# Types declared with a length.
_LENGTH_TYPES = ('varchar', 'char', 'varbinary', 'binary') + _DOUBLE_BYTE_TYPES
# Types declared with precision and scale.
_PRECISION_TYPES = ('decimal', 'numeric')
# Types declared with a fractional-seconds scale only.
_SCALE_TYPES = ('datetime2', 'time', 'datetimeoffset')


# ----------------------------------------------------------------------------
# Names
# ----------------------------------------------------------------------------

def quote_identifier(name: str) -> str:
    """Bracket-quote one identifier for T-SQL."""
    return '[' + str(name).replace(']', ']]') + ']'


def quote_literal(value: str) -> str:
    """Wrap one value as a Unicode string literal, doubling embedded quotes.

    sp_rename takes names as literals, not identifiers, so bracket-quoting is
    not the escape that applies there.
    """
    return "N'" + str(value).replace("'", "''") + "'"


def validate_customer_code(code: Any) -> str:
    """The customer code, or ValueError explaining why it cannot be one.

    Deliberately not a sanitiser. This value arrives from a filename in a drop
    folder - customer_file_service pulls it out of
    SMAUS_SM9641_RC_ACCOUNT_EXTRACT_0001.csv - and is checked nowhere else in
    the chain, yet it becomes part of a table name and is passed to sp_rename as
    a literal. Stripping the bad characters out would turn a broken input into a
    wrongly-named archive that nobody goes looking for.
    """
    text = '' if code is None else str(code).strip()
    if not text:
        raise ValueError(
            'No customer code for the archive: the staging tables are renamed to '
            '<customer code>_<table>, so there is no name to give them.')
    if not CUSTOMER_CODE_PATTERN.match(text):
        raise ValueError(
            f'Customer code {text!r} cannot be part of a table name. Expected '
            f'letters and digits starting with a letter, up to 30 characters '
            f'(for example SM9641). It is read from the extract filename, so a '
            f'code like this usually means a file is named wrongly.')
    return text


def validate_table_name(name: Any) -> str:
    """The staging table name, or ValueError. Same reasoning as the code."""
    text = '' if name is None else str(name).strip()
    if not STAGING_TABLE_PATTERN.match(text):
        raise ValueError(
            f'Staging table name {text!r} cannot be used in DDL. Check '
            f'variables/table_keywords.json.')
    return text


def archive_table_name(customer_code: str, table_name: str) -> str:
    """The archive name for one staging table, both parts validated."""
    code = validate_customer_code(customer_code)
    table = validate_table_name(table_name)
    name = f'{code}_{table}'
    if len(name) > MAX_IDENTIFIER:
        raise ValueError(
            f'Archive table name {name!r} is {len(name)} characters; SQL Server '
            f'allows {MAX_IDENTIFIER}.')
    return name


def archive_timestamp(moment: Optional[datetime] = None) -> datetime:
    """Now, at the resolution the CreateTS column actually holds.

    datetime.now() carries microseconds; CreateTS is datetime2(3). Rounding here
    rather than leaving it to the driver keeps what is written equal to what is
    read back, which is what the sweep compares against.
    """
    moment = moment or datetime.now()
    if CREATE_TS_SCALE >= 6:
        return moment
    unit = 10 ** (6 - CREATE_TS_SCALE)
    return moment.replace(microsecond=(moment.microsecond // unit) * unit)


# ----------------------------------------------------------------------------
# Catalog reads and DDL generation - used by tools/sweep_archive.py
# ----------------------------------------------------------------------------

def read_columns(helper: Any, table_name: str,
                 schema: str = 'dbo') -> List['ArchiveColumn']:
    """Column metadata for one table, or [] when the table does not exist."""
    qualified = f'{schema}.{table_name}'
    frame = helper.execute_query(_COLUMN_QUERY, params={'qualified_name': qualified})
    if frame.empty:
        return []
    return [ArchiveColumn(row) for _, row in frame.iterrows()]


class ArchiveColumn:
    """One column of a staging or archive table, and what may be done with it."""

    __slots__ = ('name', 'type_name', 'max_length', 'precision', 'scale',
                 'nullable', 'identity', 'computed', 'has_default')

    def __init__(self, row: Any):
        self.name = str(row['column_name'])
        self.type_name = str(row['type_name']).lower()
        self.max_length = int(row['max_length'])
        self.precision = int(row['precision_value'])
        self.scale = int(row['scale_value'])
        self.nullable = bool(row['is_nullable'])
        self.identity = bool(row['is_identity'])
        self.computed = bool(row['is_computed'])
        self.has_default = bool(row['has_default'])

    @property
    def insertable(self) -> bool:
        """False for columns SQL Server fills in itself."""
        return not (self.identity or self.computed
                    or self.type_name in GENERATED_COLUMN_TYPES)

    def render_type(self) -> str:
        """This column's type as DDL, e.g. NVARCHAR(100) or DECIMAL(18,2)."""
        name = self.type_name.upper()

        # rowversion generates its own value, so a copy stores the source value
        # in the binary column it is equivalent to instead.
        if self.type_name in GENERATED_COLUMN_TYPES:
            return 'BINARY(8)'

        if self.type_name in _LENGTH_TYPES:
            if self.max_length == -1:
                return f'{name}(MAX)'
            length = self.max_length
            if self.type_name in _DOUBLE_BYTE_TYPES:
                length = max(1, length // 2)
            return f'{name}({length})'

        if self.type_name in _PRECISION_TYPES:
            return f'{name}({self.precision},{self.scale})'

        if self.type_name in _SCALE_TYPES:
            return f'{name}({self.scale})'

        return name

    def render_definition(self) -> str:
        """This column as a CREATE TABLE line.

        A generated column - identity, computed, rowversion - is rendered as a
        plain nullable column of the same type: a copy holds the value the
        source produced, and must never generate one of its own.
        """
        nullability = 'NULL' if (self.nullable or not self.insertable) else 'NOT NULL'
        return f'{quote_identifier(self.name)} {self.render_type()} {nullability}'


def create_table_statement(table_name: str, columns: Sequence[ArchiveColumn],
                           schema: str = 'dbo') -> str:
    """CREATE TABLE mirroring one table's columns, and nothing else.

    No indexes and no constraints: the only caller is the sweep, building a
    destination for a table whose indexes were already dropped after it was
    archived. A heap is what it wants.
    """
    body = ',\n    '.join(column.render_definition() for column in columns)
    return (f'CREATE TABLE {quote_identifier(schema)}.'
            f'{quote_identifier(table_name)} (\n    {body}\n)')


# ----------------------------------------------------------------------------
# The rename
# ----------------------------------------------------------------------------

class StagingRenamer:
    """Move one customer's staging tables into the archive schema.

    One transaction for the whole set. A partial failure must not leave staging
    half-renamed - some tables gone, some still holding the extract - which is
    the same reasoning process_staging applies to its truncate loop. Everything
    here is a catalog operation plus an empty CREATE TABLE, so the transaction
    is short no matter how much data the tables hold.
    """

    def __init__(self, db: Any, customer_code: str, tables: Sequence[str],
                 schema_files: Dict[str, Any],
                 logger: Optional[logging.Logger] = None,
                 schema: str = 'dbo',
                 archive_schema: str = ARCHIVE_SCHEMA):
        # Validated here, before anything else, so a bad code fails the step
        # rather than a table part way through it.
        self.customer_code = validate_customer_code(customer_code)
        self.db = db
        self.tables = [validate_table_name(name)
                       for name in dict.fromkeys(tables) if name]
        self.schema_files = schema_files
        self.logger = logger or logging.getLogger(__name__)
        self.schema = schema
        self.archive_schema = archive_schema

    # ------------------------------------------------------------------
    # Names
    # ------------------------------------------------------------------

    def target_name(self, table_name: str) -> str:
        return archive_table_name(self.customer_code, table_name)

    def _qualified(self, schema: str, table_name: str) -> str:
        return f'{quote_identifier(schema)}.{quote_identifier(table_name)}'

    # ------------------------------------------------------------------
    # Catalog reads
    # ------------------------------------------------------------------

    def _tables_in(self, schema: str) -> set:
        frame = self.db.execute_query(_TABLE_LIST_QUERY,
                                      params={'schema_name': schema})
        if frame.empty:
            return set()
        return {str(name).lower() for name in frame['table_name']}

    def _row_counts(self) -> Dict[str, int]:
        frame = self.db.execute_query(_ROW_COUNT_QUERY,
                                      params={'schema_name': self.schema})
        if frame.empty:
            return {}
        return {str(row['table_name']).lower(): int(row['row_count'])
                for _, row in frame.iterrows()}

    def _schema_bound_blockers(self) -> List[str]:
        """Schema-bound objects that sp_rename would silently break."""
        frame = self.db.execute_query(_SCHEMA_BOUND_QUERY,
                                      params={'schema_name': self.schema})
        if frame.empty:
            return []
        wanted = {name.lower() for name in self.tables}
        return [f"{row['referencing_object']} -> {row['referenced_table']}"
                for _, row in frame.iterrows()
                if str(row['referenced_table']).lower() in wanted]

    def archive_ready(self) -> str:
        """Why the archive schema cannot be written to, or '' when it can."""
        frame = self.db.execute_query(
            'SELECT 1 AS present FROM sys.schemas WHERE name = :schema_name',
            params={'schema_name': self.archive_schema})
        if frame.empty:
            return (f'this database has no {self.archive_schema} schema. It is '
                    f'created once per environment, not per run - run '
                    f'{SETUP_COMMAND}.')
        if ARCHIVE_CATALOG.lower() not in self._tables_in(self.archive_schema):
            return (f'{self.archive_schema}.{ARCHIVE_CATALOG} does not exist, so '
                    f'an archived table could not be traced back to its load. '
                    f'Run {SETUP_COMMAND}.')
        return ''

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------

    def rename_statements(self, table_name: str) -> List[str]:
        """Everything that moves one staging table, in order.

        The schema file's own batches follow these and rebuild the staging
        table; they are appended by the caller, which has them already.
        """
        target = self.target_name(table_name)
        archived = self._qualified(self.archive_schema, target)
        return [
            # A re-run of the same customer replaces its previous snapshot:
            # latest load wins, so the stale table goes first.
            f"IF OBJECT_ID({quote_literal(f'{self.archive_schema}.{target}')}, N'U') "
            f'IS NOT NULL DROP TABLE {archived}',
            # sp_rename wants the old name qualified and the new name bare - a
            # schema-qualified new name becomes part of the table's name.
            f"EXEC sp_rename {quote_literal(f'{self.schema}.{table_name}')}, "
            f"{quote_literal(target)}, N'OBJECT'",
            f'ALTER SCHEMA {quote_identifier(self.archive_schema)} TRANSFER '
            f'{self._qualified(self.schema, target)}',
        ]

    def catalog_statement(self) -> str:
        table = self._qualified(self.archive_schema, ARCHIVE_CATALOG)
        return (
            f'DELETE FROM {table} WHERE ArchiveTable = ?;\n'
            f'INSERT INTO {table} (ArchiveTable, StagingTable, EntityCode, '
            f'LoadID, CreateTS, RowsArchived, SessionID, RunID, SourceDb) '
            f'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )

    # ------------------------------------------------------------------
    # The run
    # ------------------------------------------------------------------

    def archive_all(self, context: Dict[str, Any],
                    dry_run: bool = False) -> Dict[str, Any]:
        """Rename every configured staging table into the archive schema."""
        values = {str(key).lower(): value for key, value in (context or {}).items()}
        created = values.get('createts') or archive_timestamp()

        summary: Dict[str, Any] = {
            'schema': self.archive_schema,
            'customer_code': self.customer_code,
            'method': 'rename',
            'dry_run': dry_run,
            'success': True,
            'tables': {},
            'tables_archived': 0,
            'tables_skipped': 0,
            'rows_archived': 0,
            'statements': [],
            'errors': [],
        }

        problem = self.archive_ready()
        if problem:
            summary['success'] = False
            summary['errors'].append(problem)
            self.logger.error(f'Archive not possible: {problem}')
            return summary

        blockers = self._schema_bound_blockers()
        if blockers:
            problem = (
                f'schema-bound object(s) reference the staging tables, and '
                f'renaming a table out from under one breaks it silently: '
                f'{blockers}. Drop them, or exclude those tables from the '
                f'archive.')
            summary['success'] = False
            summary['errors'].append(problem)
            self.logger.error(f'Archive not possible: {problem}')
            return summary

        present = self._tables_in(self.schema)
        counts = self._row_counts()

        planned: List[Tuple[str, str, int, List[str]]] = []
        for table_name in self.tables:
            target = self.target_name(table_name)
            result: Dict[str, Any] = {
                'table_name': table_name,
                'target_table': target,
                'rows': 0,
                'skipped': False,
                'reason': '',
            }

            if table_name.lower() not in present:
                result['skipped'] = True
                result['reason'] = 'staging table does not exist'
                summary['tables'][table_name] = result
                summary['tables_skipped'] += 1
                self.logger.warning(
                    f'{table_name}: not archived, {result["reason"]}')
                continue

            schema_file = self.schema_files.get(table_name)
            if schema_file is None:
                # load_staging_schema_files raises for this at startup, so
                # reaching it here means the caller assembled its own mapping.
                summary['success'] = False
                message = (f'{table_name}: no schema file to rebuild it with, so '
                           f'renaming it away would leave the next customer '
                           f'without a staging table')
                summary['errors'].append(message)
                self.logger.error(message)
                return summary

            rows = counts.get(table_name.lower(), 0)
            result['rows'] = rows
            statements = self.rename_statements(table_name)
            statements += [batch.sql for batch in schema_file.batches]
            summary['statements'].extend(statements)
            planned.append((table_name, target, rows, statements))
            summary['tables'][table_name] = result

        if not planned:
            self.logger.warning('Nothing to archive: no staging table was found')
            return summary

        self.logger.info(
            f'{"Dry run: would archive" if dry_run else "Archiving"} '
            f'{len(planned)} staging table(s) as {self.customer_code}_* in '
            f'{self.archive_schema}')

        if dry_run:
            for table_name, target, rows, _ in planned:
                summary['tables'][table_name]['skipped'] = True
                summary['tables'][table_name]['reason'] = (
                    f'dry run: {rows} row(s) would move to '
                    f'{self.archive_schema}.{target}')
            summary['tables_skipped'] += len(planned)
            return summary

        started = time.time()
        try:
            self._apply(planned, values, created)
        except Exception as e:
            summary['success'] = False
            summary['errors'].append(f'{type(e).__name__}: {e}')
            self.logger.error(
                f'Archive failed and rolled back; staging is unchanged and still '
                f"holds this customer's extract: {type(e).__name__}: {e}",
                exc_info=True)
            return summary

        elapsed = time.time() - started
        for table_name, target, rows, _ in planned:
            summary['tables_archived'] += 1
            summary['rows_archived'] += rows
            self.logger.info(
                f'{table_name}: {rows:,} row(s) archived as '
                f'{self.archive_schema}.{target}')

        self.logger.info(
            f'Archive of {self.customer_code}: {summary["tables_archived"]} '
            f'table(s), {summary["rows_archived"]:,} row(s) in {elapsed:.2f}s '
            f'(renamed, not copied)')

        # After the commit, and never a reason to fail the customer.
        self._drop_archived_indexes([target for _, target, _, _ in planned])
        return summary

    def _apply(self, planned: List[Tuple[str, str, int, List[str]]],
               values: Dict[str, Any], created: datetime) -> None:
        """Run every table's statements in one transaction, or none of them."""
        connection = self.db.pyodbc_connection
        if connection is None:
            connection = self.db.connect_pyodbc()

        catalog_sql = self.catalog_statement()
        cursor = connection.cursor()
        try:
            # Any error aborts the whole transaction rather than leaving it in a
            # state where the remaining statements could still commit.
            cursor.execute('SET XACT_ABORT ON')
            for table_name, target, rows, statements in planned:
                for statement in statements:
                    cursor.execute(statement)
                cursor.execute(catalog_sql, (
                    target,
                    target, table_name, self.customer_code,
                    values.get('loadid'), created, rows,
                    values.get('sessionid'), values.get('runid'),
                    values.get('db'),
                ))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            self.db.last_activity = time.time()

    def _drop_archived_indexes(self, targets: Sequence[str]) -> int:
        """Drop the join indexes the archived tables inherited from staging.

        They exist for the migration's queries, not for the archive, and the
        space they hold is the cost that matters: these tables sit in the
        application's own database until the sweep moves them out. Best effort -
        a failure here costs storage, not correctness, and the customer's
        migration has already succeeded by this point.
        """
        wanted = {name.lower() for name in targets}
        dropped = 0
        try:
            frame = self.db.execute_query(
                _ARCHIVE_INDEX_QUERY,
                params={'schema_name': self.archive_schema,
                        'catalog_table': ARCHIVE_CATALOG})
            for _, row in frame.iterrows():
                table_name = str(row['table_name'])
                if table_name.lower() not in wanted:
                    continue
                self.db.execute_non_query(
                    f'DROP INDEX {quote_identifier(str(row["index_name"]))} ON '
                    f'{self._qualified(self.archive_schema, table_name)}')
                dropped += 1
        except Exception as e:
            self.logger.warning(
                f'Archived tables kept their staging indexes; they cost space '
                f'but nothing else, and the next sweep clears them: '
                f'{type(e).__name__}: {e}')
            return dropped

        if dropped:
            self.logger.info(
                f'Dropped {dropped} staging index(es) from the archived tables')
        return dropped
