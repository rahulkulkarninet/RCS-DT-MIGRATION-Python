"""Copy the RC_* staging tables into the environment's archive database.

The staging tables are truncated and reloaded for every customer, so the raw
extract as it was loaded only exists between that customer's load and the next
customer's truncate. This module copies it out, table for table, into a
long-lived archive database on the same server - each environment names its own
in ARCHIVE_DATABASE (test-migration-data on testse).

The archive tables carry the same columns as staging plus three audit columns -
LoadID, CreateTS, EntityCode - whose values the caller supplies as a context
dictionary keyed by column name. Anything else in the archive table that is
neither in staging nor in the context is left to its own default.

Schema and data are two separate jobs here, deliberately:

  ArchiveSchemaProvisioner   creates the archive tables from the staging tables'
                             own catalog entries and adds any audit column an
                             older archive table is missing. DDL only, no rows.
                             Run once when an environment is set up, and again
                             only when the staging schema changes -
                             tools/setup_archive.py.
  StagingArchiver            copies rows. It issues no DDL at all: an archive
                             table that is missing, or missing an audit column,
                             fails the table with a message naming the setup
                             tool rather than quietly creating it mid-migration.

Neither creates the archive database itself.

Two transfer paths, chosen per environment:

  cross-database SQL   INSERT ... SELECT with a three-part target name. Set
                       based, the data never leaves the server. Only possible
                       on a normal SQL Server instance.
  streamed via bcp     read chunks over the source connection, write them into
                       bcp's data file as they are read, load in one pass. The
                       only option on Azure SQL, which has no cross-database
                       queries.

bcp is the whole of the streamed path - there is no executemany fallback. It
uses the bulk-copy protocol, which measured 2-4x faster on the wide tables, and
one sink means one set of conversion rules to reason about rather than two that
have to agree. Where bcp cannot safely load a table the table fails, loudly,
instead of quietly going a different way: see bcp_blocker for what those cases
are and what to do about them.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pandas as pd


# The setup step that creates the archive tables, named in the error a run gets
# when it finds one missing. Here so the two cannot drift apart.
SETUP_COMMAND = 'tools/setup_archive.py'

# Rows pulled from the staging table per round trip on the streamed path.
ARCHIVE_CHUNK_ROWS = 50000

# ...but bounded by cell count, because these tables differ in width by two
# orders of magnitude: 50000 rows of RC_TREATMENT is 13 columns wide, 50000 rows
# of RC_DRDEBTINFO is 504, and every cell is a boxed Python object. Roughly
# 4000 rows for the widest table, the full 50000 for the narrowest.
ARCHIVE_MAX_CELLS_PER_CHUNK = 2_000_000
ARCHIVE_MIN_CHUNK_ROWS = 1000

# Column types SQL Server generates itself; they cannot be given a value.
GENERATED_COLUMN_TYPES = ('timestamp', 'rowversion')

# Types bcp's character mode cannot round-trip. Binary is decoded as UTF-8 with
# replacement on the way into the data file, which corrupts it silently - the
# one failure an archive must not have. None of the RC_* tables hold these
# today; the guard is so that a future one does not quietly lose data.
BCP_UNSAFE_TYPES = ('binary', 'varbinary', 'image', 'sql_variant')

# Column metadata for one table, read from the catalog rather than reflected:
# is_identity/is_computed decide what may be inserted, and having the default
# and nullability makes it possible to say up front which archive-only columns
# must be filled and which can be left alone.
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

# Audit columns every archive table carries on top of the staging columns. Types
# follow what the rest of the schema already uses: tblLoad.LoadID is int,
# RC_Processing_Stats.Created_Date is datetime2(3), and tblentity.EntityCode /
# RC_Entity_Mapping.Client_Code are nvarchar(100). All nullable, so they can be
# added to an archive table that already holds rows.
AUDIT_COLUMNS: Tuple[Dict[str, Any], ...] = (
    {'column_name': 'LoadID', 'type_name': 'int',
     'max_length': 4, 'precision_value': 10, 'scale_value': 0},
    {'column_name': 'CreateTS', 'type_name': 'datetime2',
     'max_length': 8, 'precision_value': 23, 'scale_value': 3},
    {'column_name': 'EntityCode', 'type_name': 'nvarchar',
     'max_length': 200, 'precision_value': 0, 'scale_value': 0},
)

# Character types whose sys.columns.max_length is in bytes at 2 bytes per char.
_DOUBLE_BYTE_TYPES = ('nvarchar', 'nchar')
# Types declared with a length.
_LENGTH_TYPES = ('varchar', 'char', 'varbinary', 'binary') + _DOUBLE_BYTE_TYPES
# Types declared with precision and scale.
_PRECISION_TYPES = ('decimal', 'numeric')
# Types declared with a fractional-seconds scale only.
_SCALE_TYPES = ('datetime2', 'time', 'datetimeoffset')


def quote_identifier(name: str) -> str:
    """Bracket-quote one identifier for T-SQL."""
    return '[' + str(name).replace(']', ']]') + ']'


def audit_columns() -> List['ArchiveColumn']:
    """The audit columns as column metadata, shaped like a catalog read."""
    return [
        ArchiveColumn({**spec, 'is_nullable': 1, 'is_identity': 0,
                       'is_computed': 0, 'has_default': 0})
        for spec in AUDIT_COLUMNS
    ]


def archive_timestamp(moment: Optional[datetime] = None) -> datetime:
    """Now, at the resolution the CreateTS column actually holds.

    datetime.now() carries microseconds; CreateTS is datetime2(3). Rounding it
    here rather than leaving it to the sink keeps the two sinks writing the same
    value - and bcp does not round at all: its character literal is parsed
    against the column's scale, and six digits into three is a rejected row.
    """
    moment = moment or datetime.now()
    scale = next((int(spec['scale_value']) for spec in AUDIT_COLUMNS
                  if spec['column_name'].lower() == 'createts'), 3)
    if scale >= 6:
        return moment
    unit = 10 ** (6 - scale)
    return moment.replace(microsecond=(moment.microsecond // unit) * unit)


def read_columns(helper: Any, table_name: str,
                 schema: str = 'dbo') -> List['ArchiveColumn']:
    """Column metadata for one table, or [] when the table does not exist."""
    qualified = f'{schema}.{table_name}'
    frame = helper.execute_query(_COLUMN_QUERY, params={'qualified_name': qualified})
    if frame.empty:
        return []
    return [ArchiveColumn(row) for _, row in frame.iterrows()]


def missing_audit_columns(target_columns: List['ArchiveColumn']) -> List[str]:
    """Names of the audit columns an existing archive table does not have."""
    present = {column.name.lower() for column in target_columns}
    return [column.name for column in audit_columns()
            if column.name.lower() not in present]


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

        # rowversion generates its own value, so the archive stores the source
        # value in the binary column it is equivalent to instead.
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
        plain nullable column of the same type: the archive holds the value the
        staging table produced, and must never generate one of its own.
        """
        nullability = 'NULL' if (self.nullable or not self.insertable) else 'NOT NULL'
        return f'{quote_identifier(self.name)} {self.render_type()} {nullability}'


class TablePlan:
    """How one staging table maps onto its archive table."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        # (archive column, staging column) pairs, in archive column order.
        self.copied: List[Tuple[str, str]] = []
        # (archive column, value) pairs taken from the run context.
        self.context: List[Tuple[str, Any]] = []
        # Archive columns nobody supplies; they take their own default or NULL.
        self.unfilled: List[str] = []
        # Unfilled and NOT NULL with no default, so the insert cannot succeed.
        self.blocking: List[str] = []
        # Staging columns with no home in the archive table.
        self.dropped: List[str] = []
        # Archive columns SQL Server fills in itself - identity, computed,
        # rowversion. None of these exist in a provisioned archive table.
        self.generated: List[str] = []
        # Copied columns whose type bcp's character mode would corrupt.
        self.bcp_unsafe: List[str] = []

    @property
    def target_columns(self) -> List[str]:
        return [name for name, _ in self.copied] + [name for name, _ in self.context]

    @property
    def covers_every_column(self) -> bool:
        """True when this plan supplies every column of the archive table.

        What bcp needs: it writes the whole table's column list, so anything
        this plan does not supply would be written as NULL rather than left to
        its default.
        """
        return not self.unfilled and not self.generated


class ArchiveSchemaProvisioner:
    """Create and alter the archive tables. A setup step, not a per-load one.

    Every archive table is generated from its staging table's catalog entry, so
    the archive follows whatever the staging schema is in this environment
    rather than a second copy of it that has to be kept in step by hand.

    Run this once when an environment is first set up - after the RC_* staging
    tables exist and the archive database has been created - and again after a
    staging schema change adds a column. It never touches rows, in either
    direction, so re-running it on a populated archive is safe: an existing
    table is left alone apart from audit columns it is missing, which are added
    nullable.

    What it deliberately does NOT do: create the archive database (see
    SQL/Schemas/Migrations/004.migration_data_archive.sql), drop or alter an
    existing column, or reconcile a staging column added after the archive table
    was created - that last one is reported rather than applied, because
    widening an archive table that already holds loads is a decision, not a
    detail.
    """

    def __init__(self, source_db: Any, target_db: Any, tables: List[str],
                 logger: Optional[logging.Logger] = None, schema: str = 'dbo'):
        self.source_db = source_db
        self.target_db = target_db
        self.tables = list(dict.fromkeys(tables))
        self.logger = logger or logging.getLogger(__name__)
        self.schema = schema

    @property
    def archive_database(self) -> str:
        return self.target_db.config.get('DATABASE', '')

    # ------------------------------------------------------------------
    # DDL
    # ------------------------------------------------------------------

    def create_table_statement(self, table_name: str,
                               source_columns: List[ArchiveColumn]) -> str:
        """CREATE TABLE for the archive copy of one staging table."""
        definitions = [column.render_definition() for column in source_columns]
        present = {column.name.lower() for column in source_columns}
        definitions += [
            column.render_definition() for column in audit_columns()
            if column.name.lower() not in present
        ]
        # The duplicate guard filters on exactly these two, and so does anyone
        # looking up one customer's load after the fact.
        index_name = f'IX_{table_name}_LoadID_EntityCode'
        definitions.append(
            f'INDEX {quote_identifier(index_name)} '
            f'({quote_identifier("LoadID")}, {quote_identifier("EntityCode")})'
        )
        body = ',\n    '.join(definitions)
        return (f'CREATE TABLE {quote_identifier(self.schema)}.'
                f'{quote_identifier(table_name)} (\n    {body}\n)')

    def add_column_statements(self, table_name: str,
                              target_columns: List[ArchiveColumn]) -> List[str]:
        """ALTER TABLE ADD for any audit column the archive table is missing."""
        present = {column.name.lower() for column in target_columns}
        return [
            f'ALTER TABLE {quote_identifier(self.schema)}.'
            f'{quote_identifier(table_name)} ADD {column.render_definition()}'
            for column in audit_columns()
            if column.name.lower() not in present
        ]

    # ------------------------------------------------------------------
    # Per table
    # ------------------------------------------------------------------

    def plan_table(self, table_name: str) -> Dict[str, Any]:
        """What one archive table needs, without changing anything."""
        result: Dict[str, Any] = {
            'table_name': table_name,
            'action': 'none',
            'statements': [],
            'missing_staging_columns': [],
            'error': '',
        }

        source_columns = read_columns(self.source_db, table_name, self.schema)
        if not source_columns:
            result['action'] = 'no_staging_table'
            return result

        target_columns = read_columns(self.target_db, table_name, self.schema)
        if not target_columns:
            result['action'] = 'create'
            result['statements'] = [
                self.create_table_statement(table_name, source_columns)
            ]
            return result

        statements = self.add_column_statements(table_name, target_columns)
        if statements:
            result['action'] = 'add_audit_columns'
            result['statements'] = statements

        # Staging columns the archive table has no home for. The archiver drops
        # them silently at copy time; reporting them here is the only place
        # anyone gets to notice before the rows are already gone.
        archived = {column.name.lower() for column in target_columns}
        result['missing_staging_columns'] = [
            column.name for column in source_columns
            if column.name.lower() not in archived
        ]
        return result

    def provision_table(self, table_name: str,
                        dry_run: bool = False) -> Dict[str, Any]:
        """Bring one archive table into line with its staging table."""
        result = self.plan_table(table_name)
        result['applied'] = False

        if result['action'] == 'no_staging_table':
            self.logger.warning(
                f'{table_name}: no staging table {self.schema}.{table_name} in '
                f'this environment, so no archive table was created')
            return result

        if result['missing_staging_columns']:
            self.logger.warning(
                f'{table_name}: {len(result["missing_staging_columns"])} staging '
                f'column(s) have no column in {self.archive_database} and will not '
                f'be archived: {result["missing_staging_columns"][:10]}'
                f'{"..." if len(result["missing_staging_columns"]) > 10 else ""}. '
                f'Add them by hand, or drop the archive table and re-run this to '
                f'recreate it.'
            )

        if not result['statements'] or dry_run:
            return result

        try:
            for statement in result['statements']:
                self.target_db.execute_non_query(statement)
        except Exception as e:
            result['error'] = f'{type(e).__name__}: {e}'
            self.logger.error(f'{table_name}: {result["error"]}', exc_info=True)
            return result

        result['applied'] = True
        if result['action'] == 'create':
            self.logger.info(
                f'created {self.schema}.{table_name} in {self.archive_database}')
        else:
            self.logger.info(
                f'added audit column(s) to {self.schema}.{table_name} in '
                f'{self.archive_database}')
        return result

    # ------------------------------------------------------------------
    # Whole environment
    # ------------------------------------------------------------------

    def provision_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """Create or top up every archive table this environment needs."""
        summary: Dict[str, Any] = {
            'database': self.archive_database,
            'dry_run': dry_run,
            'success': True,
            'tables': {},
            'tables_created': 0,
            'tables_altered': 0,
            'tables_unchanged': 0,
            'tables_skipped': 0,
            'tables_failed': 0,
            'errors': [],
        }

        self.logger.info(
            f'{"Dry run: would provision" if dry_run else "Provisioning"} '
            f'{len(self.tables)} archive table(s) in {self.archive_database}')

        for table_name in self.tables:
            try:
                result = self.provision_table(table_name, dry_run=dry_run)
            except Exception as e:
                self.logger.error(
                    f'{table_name}: provisioning failed: {type(e).__name__}: {e}',
                    exc_info=True)
                result = {
                    'table_name': table_name,
                    'action': 'error',
                    'statements': [],
                    'missing_staging_columns': [],
                    'applied': False,
                    'error': f'{type(e).__name__}: {e}',
                }

            summary['tables'][table_name] = result

            if result['error']:
                summary['success'] = False
                summary['tables_failed'] += 1
                summary['errors'].append(f'{table_name}: {result["error"]}')
            elif result['action'] == 'no_staging_table':
                summary['tables_skipped'] += 1
            elif result['action'] == 'create':
                summary['tables_created'] += 1
            elif result['action'] == 'add_audit_columns':
                summary['tables_altered'] += 1
            else:
                summary['tables_unchanged'] += 1

        self.logger.info(
            f'Archive schema in {self.archive_database}: '
            f'{summary["tables_created"]} table(s) created, '
            f'{summary["tables_altered"]} altered, '
            f'{summary["tables_unchanged"]} already current, '
            f'{summary["tables_skipped"]} skipped, '
            f'{summary["tables_failed"]} failed')
        return summary


class StagingArchiver:
    """Copy staging tables into the archive database, one table at a time.

    Rows only: the archive tables are created by ArchiveSchemaProvisioner as a
    one-off setup step, and a table this expects to find missing is an error
    here rather than something to fix in the middle of a customer's migration.
    """

    def __init__(self, source_db: Any, target_db: Any, tables: List[str],
                 logger: Optional[logging.Logger] = None,
                 chunk_rows: int = ARCHIVE_CHUNK_ROWS):
        self.source_db = source_db
        self.target_db = target_db
        self.tables = list(dict.fromkeys(tables))
        self.logger = logger or logging.getLogger(__name__)
        self.chunk_rows = chunk_rows
        self.schema = 'dbo'

    # ------------------------------------------------------------------
    # Transfer path
    # ------------------------------------------------------------------

    @property
    def archive_database(self) -> str:
        return self.target_db.config.get('DATABASE', '')

    def _same_instance(self) -> bool:
        source = str(self.source_db.config.get('SERVER', '')).strip().lower()
        target = str(self.target_db.config.get('SERVER', '')).strip().lower()
        return bool(source) and source == target

    def use_cross_database_sql(self) -> bool:
        """True when a three-part-name INSERT ... SELECT will work."""
        return self._same_instance() and not self.source_db.is_azure()

    @property
    def method(self) -> str:
        """The transfer path this environment takes.

        Deliberately does not call bcp_ready(): that spawns a login probe, which
        has no business running just because something wanted a label.
        """
        if self.use_cross_database_sql():
            return 'cross-database SQL'
        return 'streamed via bcp'

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _columns(self, helper: Any, table_name: str) -> List[ArchiveColumn]:
        """Column metadata for one table, or [] when the table does not exist."""
        return read_columns(helper, table_name, self.schema)

    def _archive_name(self, table_name: str) -> str:
        """Three-part name of one archive table."""
        return (f'{quote_identifier(self.archive_database)}.'
                f'{quote_identifier(self.schema)}.{quote_identifier(table_name)}')

    def schema_problem(self, table_name: str,
                       target_columns: List[ArchiveColumn]) -> str:
        """Why this archive table cannot be written to, or '' when it can.

        The archiver issues no DDL, so both cases are the same answer: the
        environment's archive schema has not been provisioned, or has not been
        provisioned since something changed.
        """
        setup = f'python {SETUP_COMMAND} <env>'

        if not target_columns:
            return (f'{self.archive_database} has no table '
                    f'{self.schema}.{table_name}. The archive schema is set up '
                    f'once per environment, not per run - create it with '
                    f'{setup}.')

        missing = missing_audit_columns(target_columns)
        if missing:
            return (f'{self.archive_database}.{self.schema}.{table_name} is '
                    f'missing audit column(s) {missing}, so an archived row '
                    f'could not be traced back to its load. Bring the archive '
                    f'schema up to date with {setup}.')

        return ''

    def _row_count(self, helper: Any, table_name: str) -> int:
        query = (f'SELECT COUNT_BIG(*) AS row_count FROM '
                 f'{quote_identifier(self.schema)}.{quote_identifier(table_name)}')
        frame = helper.execute_query(query)
        return int(frame.iloc[0, 0]) if not frame.empty else 0

    def build_plan(self, table_name: str, source_columns: List[ArchiveColumn],
                   target_columns: List[ArchiveColumn],
                   context: Dict[str, Any]) -> TablePlan:
        """Decide, column by column, what the archive insert will carry.

        A column present in both tables is copied. A column only the archive has
        is filled from the run context when the context names it - matched on the
        lowercased column name, so LoadID/loadid/LOADID all resolve. Staging wins
        over the context when both have the column, because then the value is
        part of the extract rather than run metadata.
        """
        plan = TablePlan(table_name)
        source_by_lower = {c.name.lower(): c for c in source_columns}
        matched_source: set = set()

        for column in target_columns:
            if not column.insertable:
                plan.generated.append(column.name)
                continue
            key = column.name.lower()
            source = source_by_lower.get(key)
            if source is not None:
                plan.copied.append((column.name, source.name))
                matched_source.add(key)
                if source.type_name in BCP_UNSAFE_TYPES:
                    plan.bcp_unsafe.append(source.name)
            elif key in context:
                plan.context.append((column.name, context[key]))
            else:
                plan.unfilled.append(column.name)
                if not column.nullable and not column.has_default:
                    plan.blocking.append(column.name)

        plan.dropped = [c.name for c in source_columns if c.name.lower() not in matched_source]
        return plan

    # ------------------------------------------------------------------
    # Duplicate guard
    # ------------------------------------------------------------------

    def _existing_rows_for_load(self, table_name: str, plan: TablePlan,
                                context: Dict[str, Any]) -> Tuple[int, str]:
        """Rows already archived for this LoadID (and EntityCode, when present).

        A resumed run reuses its LoadID, so without this a second pass over the
        same customer would append a second copy of the same extract.
        """
        filters: List[str] = []
        described: List[str] = []
        params: Dict[str, Any] = {}
        supplied = {name.lower(): value for name, value in plan.context}
        for key in ('loadid', 'entitycode'):
            if key in supplied and supplied[key] is not None:
                actual = next(name for name, _ in plan.context if name.lower() == key)
                filters.append(f'{quote_identifier(actual)} = :{key}')
                described.append(f'{actual} {supplied[key]}')
                params[key] = supplied[key]

        if 'loadid' not in params:
            return 0, ''

        query = (f'SELECT COUNT_BIG(*) AS row_count FROM '
                 f'{quote_identifier(self.schema)}.{quote_identifier(table_name)} '
                 f'WHERE {" AND ".join(filters)}')
        frame = self.target_db.execute_query(query, params=params)
        count = int(frame.iloc[0, 0]) if not frame.empty else 0
        return count, ', '.join(described)

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------

    def _copy_cross_database(self, table_name: str, plan: TablePlan) -> int:
        """INSERT ... SELECT straight into the archive, on the server."""
        target_columns = ', '.join(quote_identifier(name) for name in plan.target_columns)
        select_columns = [quote_identifier(source) for _, source in plan.copied]
        select_columns += ['?'] * len(plan.context)
        values = [value for _, value in plan.context]

        statement = (
            f'INSERT INTO {self._archive_name(table_name)} '
            f'({target_columns}) '
            f'SELECT {", ".join(select_columns)} '
            f'FROM {quote_identifier(self.schema)}.{quote_identifier(table_name)}'
        )

        connection = self.source_db.pyodbc_connection
        if connection is None:
            connection = self.source_db.connect_pyodbc()

        cursor = connection.cursor()
        try:
            # execute(sql, []) is not the same call as execute(sql) to pyodbc.
            if values:
                cursor.execute(statement, values)
            else:
                cursor.execute(statement)
            copied = cursor.rowcount
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

        self.source_db.last_activity = time.time()
        return max(0, int(copied))

    def _stream_chunks(self, table_name: str, plan: TablePlan,
                       counters: Dict[str, int]) -> Iterator[pd.DataFrame]:
        """Yield archive-shaped chunks read from the staging table.

        Rows are fetched with a raw cursor and held as object dtype rather than
        read with pd.read_sql, so nothing is inferred on the way through: a
        DECIMAL stays a Decimal instead of becoming float64, and a date SQL
        Server can represent but datetime64[ns] cannot - RC_DRDBINVOICE has
        years past 2500 - stays a datetime instead of failing or going NaT.
        Both sinks already accept object columns.

        The cursor comes from the SQLAlchemy engine's pool, NOT from
        db_helper.pyodbc_connection. That connection sets
        setdecoding(SQL_WCHAR, 'utf-8'), which makes pyodbc ask the driver for
        narrow characters: nvarchar then arrives converted to the client ANSI
        code page, so an en dash comes back as the single byte 0x96 and fails to
        decode as UTF-8. It only bites on non-ASCII, which is why it surfaced on
        one RC_ACCOUNT_EXTRACT row and nowhere else. The engine's connections
        never had that applied and read UTF-16 correctly.
        """
        select_columns = ', '.join(
            f'{quote_identifier(source)} AS {quote_identifier(target)}'
            for target, source in plan.copied
        )
        query = (f'SELECT {select_columns} FROM '
                 f'{quote_identifier(self.schema)}.{quote_identifier(table_name)}')

        if self.source_db.sqlalchemy_engine is None:
            self.source_db.connect_sqlalchemy()

        fetch_rows = self._fetch_rows(len(plan.copied))
        connection = self.source_db.sqlalchemy_engine.raw_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            names = [column[0] for column in cursor.description]
            while True:
                rows = cursor.fetchmany(fetch_rows)
                if not rows:
                    break
                chunk = pd.DataFrame([tuple(row) for row in rows], columns=names,
                                     dtype=object)
                for name, value in plan.context:
                    # As object, so the value reaches the driver exactly as given
                    # rather than through whatever dtype pandas would infer.
                    chunk[name] = pd.Series([value] * len(chunk),
                                            index=chunk.index, dtype=object)
                counters['rows_read'] += len(chunk)
                yield chunk
        finally:
            cursor.close()
            connection.close()      # back to the pool, not actually closed
            self.source_db.last_activity = time.time()

    def _fetch_rows(self, column_count: int) -> int:
        """Rows per fetch, bounded by cell count so wide tables stay in memory."""
        if column_count <= 0:
            return self.chunk_rows
        by_width = max(ARCHIVE_MIN_CHUNK_ROWS,
                       ARCHIVE_MAX_CELLS_PER_CHUNK // column_count)
        return min(self.chunk_rows, by_width)

    def bcp_blocker(self, plan: TablePlan) -> Optional[str]:
        """Why bcp cannot load this table, or None when it can.

        bcp is the only streamed sink, so anything here fails the table rather
        than diverting it. Each case is a correctness problem, not a preference:
        bcp writes the whole column list with no format file, so a column it
        cannot supply honestly is one it would silently get wrong.
        """
        if plan.bcp_unsafe:
            return (f"bcp's character mode would corrupt column(s) "
                    f'{plan.bcp_unsafe}. Archiving them needs a native-format '
                    f'load, which this step does not do.')
        if plan.generated:
            return (f'the archive table has generated column(s) bcp cannot fill: '
                    f'{plan.generated}. A provisioned archive table has none - '
                    f'this one was not made by {SETUP_COMMAND}.')
        if plan.unfilled:
            return (f'column(s) with nothing to supply them would be written as '
                    f'NULL rather than take their default: {plan.unfilled}. '
                    f'Drop them from the archive table, or add them to the '
                    f'archive context so this run supplies them.')
        ready, why_not = self.target_db.bcp_ready()
        if not ready:
            return why_not
        return None

    def _copy_via_bcp(self, table_name: str, plan: TablePlan) -> Tuple[bool, int, int]:
        """Stream the table into bcp's data file, then load it in one pass."""
        counters = {'rows_read': 0}
        success, rows_copied = self.target_db.bulk_insert_via_bcp(
            self._stream_chunks(table_name, plan, counters),
            table_name,
            schema=self.schema,
        )
        return success, counters['rows_read'], rows_copied

    # ------------------------------------------------------------------
    # Per table
    # ------------------------------------------------------------------

    def archive_table(self, table_name: str, context: Dict[str, Any],
                      dry_run: bool = False) -> Dict[str, Any]:
        """Copy one staging table into the archive database."""
        result: Dict[str, Any] = {
            'table_name': table_name,
            'success': True,
            'skipped': False,
            'reason': '',
            'rows_read': 0,
            'rows_copied': 0,
            'sink': '',
            'error': '',
        }

        source_columns = self._columns(self.source_db, table_name)
        if not source_columns:
            result['skipped'] = True
            result['reason'] = 'staging table does not exist'
            self.logger.warning(f'{table_name}: not archived, {result["reason"]}')
            return result

        # Before the row count, so an environment whose archive schema was never
        # provisioned says so on the first table rather than on the first table
        # that happens to hold rows.
        target_columns = self._columns(self.target_db, table_name)
        problem = self.schema_problem(table_name, target_columns)
        if problem:
            result['success'] = False
            result['error'] = problem
            self.logger.error(f'{table_name}: {problem}')
            return result

        source_rows = self._row_count(self.source_db, table_name)
        if source_rows == 0:
            result['skipped'] = True
            result['reason'] = 'no rows in staging'
            return result

        plan = self.build_plan(table_name, source_columns, target_columns, context)
        result['plan'] = {
            'copied': [name for name, _ in plan.copied],
            'context': [name for name, _ in plan.context],
            'unfilled': list(plan.unfilled),
            'dropped': list(plan.dropped),
        }

        if plan.blocking:
            result['success'] = False
            result['error'] = (
                f'{self.archive_database}.{self.schema}.{table_name} has NOT NULL '
                f'column(s) with no source and no default: {plan.blocking}. Give '
                f'them a default, make them nullable, or add them to the archive '
                f'context.'
            )
            self.logger.error(f'{table_name}: {result["error"]}')
            return result

        if not plan.copied:
            result['success'] = False
            result['error'] = (f'no column of {self.schema}.{table_name} exists in '
                               f'{self.archive_database}')
            self.logger.error(f'{table_name}: {result["error"]}')
            return result

        if plan.dropped:
            self.logger.warning(
                f'{table_name}: {len(plan.dropped)} staging column(s) have no '
                f'archive column and are not copied: {plan.dropped[:10]}'
                f'{"..." if len(plan.dropped) > 10 else ""}. The archive table '
                f'predates them; python {SETUP_COMMAND} <env> --dry-run reports '
                f'the same thing outside a run.'
            )
        if plan.unfilled:
            self.logger.info(
                f'{table_name}: archive column(s) left to their default: '
                f'{plan.unfilled}'
            )

        if dry_run:
            result['skipped'] = True
            result['reason'] = f'dry run: {source_rows} row(s) would be archived'
            return result

        already, where = self._existing_rows_for_load(table_name, plan, context)
        if already:
            result['skipped'] = True
            result['reason'] = (f'{already} row(s) already archived for {where}')
            self.logger.warning(
                f'{table_name}: not archived, {already} row(s) already in '
                f'{self.archive_database} for {where}. Delete them or run under a '
                f'new LoadID to archive again.'
            )
            return result

        start = time.time()
        if self.use_cross_database_sql():
            result['sink'] = 'cross-database SQL'
            rows_copied = self._copy_cross_database(table_name, plan)
            rows_read = source_rows
            success = True
        else:
            blocked = self.bcp_blocker(plan)
            if blocked:
                result['success'] = False
                result['error'] = f'bcp cannot load this table: {blocked}'
                self.logger.error(f'{table_name}: {result["error"]}')
                return result
            result['sink'] = 'bcp'
            success, rows_read, rows_copied = self._copy_via_bcp(table_name, plan)

        elapsed = time.time() - start
        result['rows_read'] = rows_read
        result['rows_copied'] = rows_copied
        result['success'] = success

        if success and rows_copied != source_rows:
            result['success'] = False
            result['error'] = (f'reconciliation mismatch: staging holds {source_rows}, '
                               f'archived {rows_copied}')
            self.logger.error(f'{table_name}: {result["error"]}')
        elif not success:
            result['error'] = result['error'] or (
                f'archive insert failed after {rows_copied} of {source_rows} row(s)')

        rate = rows_copied / elapsed if elapsed > 0 else 0
        self.logger.info(
            f'{table_name}: archived {rows_copied}/{source_rows} row(s) to '
            f'{self.archive_database} via {result["sink"]} in {elapsed:.1f}s '
            f'({rate:.0f} rows/sec)'
        )
        return result

    # ------------------------------------------------------------------
    # Whole run
    # ------------------------------------------------------------------

    def archive_all(self, context: Dict[str, Any],
                    dry_run: bool = False) -> Dict[str, Any]:
        """Copy every configured staging table into the archive database."""
        normalised = {str(key).lower(): value for key, value in (context or {}).items()}

        summary: Dict[str, Any] = {
            'database': self.archive_database,
            'method': self.method,
            'dry_run': dry_run,
            'success': True,
            'tables': {},
            'tables_copied': 0,
            'tables_skipped': 0,
            'tables_failed': 0,
            'rows_copied': 0,
            'errors': [],
        }

        self.logger.info(
            f'{"Dry run: would archive" if dry_run else "Archiving"} '
            f'{len(self.tables)} staging table(s) to {self.archive_database} '
            f'({self.method})'
        )

        for table_name in self.tables:
            try:
                result = self.archive_table(table_name, normalised, dry_run=dry_run)
            except Exception as e:
                self.logger.error(
                    f'{table_name}: archive failed: {type(e).__name__}: {e}',
                    exc_info=True,
                )
                result = {
                    'table_name': table_name,
                    'success': False,
                    'skipped': False,
                    'reason': '',
                    'rows_read': 0,
                    'rows_copied': 0,
                    'sink': '',
                    'error': f'{type(e).__name__}: {e}',
                }

            summary['tables'][table_name] = result
            summary['rows_copied'] += result['rows_copied']

            if not result['success']:
                summary['success'] = False
                summary['tables_failed'] += 1
                summary['errors'].append(f'{table_name}: {result["error"]}')
            elif result['skipped']:
                summary['tables_skipped'] += 1
            else:
                summary['tables_copied'] += 1

        self.logger.info(
            f'Archive to {self.archive_database}: {summary["tables_copied"]} table(s) '
            f'copied, {summary["tables_skipped"]} skipped, {summary["tables_failed"]} '
            f'failed, {summary["rows_copied"]} row(s) total'
        )
        return summary
