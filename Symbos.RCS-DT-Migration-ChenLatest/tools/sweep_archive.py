r"""Move archived tables out of the migration's database into ARCHIVE_DATABASE.

The archive step renames each customer's staging tables into the archive schema
of the environment's own database - a rename cannot cross databases, so that is
as far as it can get them. This is the second half: it copies them on to
ARCHIVE_DATABASE and drops the originals.

    python tools/sweep_archive.py uat --dry-run
    python tools/sweep_archive.py uat --older-than 30d
    python tools/sweep_archive.py uat --entity-code SM9641 --workers 4

Run it on a schedule. Nothing in a migration waits for it, and it is safe to run
while one is in flight: it only ever touches the archive schema, which a running
migration adds to and never reads. Until it has run, the tables in that schema
are the ONLY copy of those customers' extracts - which is why nothing here drops
one until its rows have been counted on the other side.

Why this is where bcp lives now. The copy has to go through the client on Azure,
which has no cross-database queries, so it is the expensive half of the archive -
and taking it off the critical path is most of the point of the rename. Because
it is off that path it can also afford to be thorough: native-format bcp rather
than the old character-mode stream (no Python in the data path at all, and
binary columns round-trip), and several tables at once.

On dev and v10 there is no client hop to avoid - source and target are databases
on one instance - so it copies with a cross-database INSERT ... SELECT instead
and the rows never leave the server.

Resumable by construction: the source table is dropped only after the target's
row count matches, so an interrupted sweep simply redoes that table next time.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TOOLS_DIR)

from db_manager import DatabaseHelper  # noqa: E402
from staging_archive import (  # noqa: E402
    ARCHIVE_CATALOG,
    ARCHIVE_SCHEMA,
    create_table_statement,
    quote_identifier,
    read_columns,
)
from env_target import resolve_environment  # noqa: E402

LOGGER = logging.getLogger('sweep_archive')

# Rows per bcp batch on the way in. Same value the CSV load uses.
BCP_BATCH_SIZE = 50000
BCP_MAX_ERRORS = 10

# Where swept tables land. The archive database holds nothing else, so its
# default schema is the natural home and the names already carry the customer.
TARGET_SCHEMA = 'dbo'

_DURATION_RE = re.compile(r'^(\d+)\s*([dwmy]?)$', re.IGNORECASE)
_DURATION_DAYS = {'': 1, 'd': 1, 'w': 7, 'm': 30, 'y': 365}

# Per-thread connections. A DatabaseHelper owns a pyodbc connection and a
# SQLAlchemy engine, neither of which is safe to share across threads; one pair
# per worker is cheap, and far cheaper than one pair per table on Azure, where a
# login costs real time.
#
# _OPENED tracks every pair any thread made, because thread-local storage cannot
# be read from the thread that has to clean up: the pool's workers are gone by
# the time the sweep finishes, and their connections would otherwise be held
# until the process exits.
_LOCAL = threading.local()
_OPENED: List[Tuple[DatabaseHelper, DatabaseHelper]] = []
_OPENED_LOCK = threading.Lock()


def parse_duration_days(text: str) -> int:
    """'30d' / '6w' / '3m' / '1y' / '30' as a number of days."""
    match = _DURATION_RE.match(str(text).strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f'Cannot read {text!r} as an age. Use 30d, 6w, 3m, 1y, or a number '
            f'of days.')
    return int(match.group(1)) * _DURATION_DAYS[match.group(2).lower()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('environment', nargs='?', default=None,
                        help='Environment name, e.g. uat')
    parser.add_argument('--config', dest='config_path', default=None,
                        metavar='PATH',
                        help='Environment file, or the directory holding it')
    parser.add_argument('--older-than', type=parse_duration_days, default=None,
                        metavar='AGE',
                        help='Only sweep tables archived at least this long ago '
                             '(30d, 6w, 3m, 1y). Default: everything unswept.')
    parser.add_argument('--entity-code', default=None,
                        help='Only this customer')
    parser.add_argument('--table', dest='tables', action='append', default=[],
                        metavar='NAME',
                        help='Only this archive table; repeatable')
    parser.add_argument('--workers', type=int, default=4,
                        help='Tables copied at once (default 4). Lower it on a '
                             'contended server.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would move; change nothing')
    return parser.parse_args()


# ----------------------------------------------------------------------------
# What to sweep
# ----------------------------------------------------------------------------

def pending(db: DatabaseHelper, args: argparse.Namespace) -> List[Dict[str, Any]]:
    """Catalog rows not yet swept, newest last, with the table still present.

    Joined against sys.tables rather than trusted outright: a catalog row whose
    table someone has already removed by hand is not an error, it is simply
    nothing to do.
    """
    clauses = ['c.SweptTS IS NULL', 't.object_id IS NOT NULL']
    params: Dict[str, Any] = {'archive_schema': ARCHIVE_SCHEMA}

    if args.older_than is not None:
        clauses.append('c.CreateTS <= :cutoff')
        params['cutoff'] = datetime.now() - timedelta(days=args.older_than)
    if args.entity_code:
        clauses.append('c.EntityCode = :entity_code')
        params['entity_code'] = args.entity_code

    query = f"""
    SELECT c.ArchiveTable, c.StagingTable, c.EntityCode, c.LoadID, c.CreateTS,
           c.RowsArchived, c.SessionID, c.RunID, c.SourceDb
    FROM {quote_identifier(ARCHIVE_SCHEMA)}.{quote_identifier(ARCHIVE_CATALOG)} c
    LEFT JOIN sys.tables t
      ON t.name = c.ArchiveTable
     AND t.schema_id = SCHEMA_ID(:archive_schema)
    WHERE {' AND '.join(clauses)}
    ORDER BY c.CreateTS
    """
    frame = db.execute_query(query, params=params)
    rows = [dict(row) for _, row in frame.iterrows()] if not frame.empty else []

    if args.tables:
        wanted = {name.lower() for name in args.tables}
        rows = [row for row in rows if str(row['ArchiveTable']).lower() in wanted]
    return rows


def ensure_target_catalog(target_db: DatabaseHelper) -> None:
    """The archive database's own copy of the catalog, created on first sweep.

    So the metadata travels with the data: a table sitting in the archive
    database still says which customer and load it came from, without anyone
    having to go back to the database it was swept out of.
    """
    target_db.execute_non_query(f"""
    IF OBJECT_ID(N'{TARGET_SCHEMA}.{ARCHIVE_CATALOG}', N'U') IS NULL
    CREATE TABLE {quote_identifier(TARGET_SCHEMA)}.{quote_identifier(ARCHIVE_CATALOG)} (
        ArchiveTable  NVARCHAR(128) NOT NULL,
        StagingTable  NVARCHAR(128) NOT NULL,
        EntityCode    NVARCHAR(200) NOT NULL,
        LoadID        INT           NULL,
        CreateTS      DATETIME2(3)  NOT NULL,
        RowsArchived  BIGINT        NULL,
        SessionID     INT           NULL,
        RunID         NVARCHAR(100) NULL,
        SourceDb      NVARCHAR(100) NULL,
        SweptTS       DATETIME2(3)  NOT NULL,
        CONSTRAINT PK_{ARCHIVE_CATALOG}_swept PRIMARY KEY CLUSTERED (ArchiveTable)
    )""")


# ----------------------------------------------------------------------------
# Connections
# ----------------------------------------------------------------------------

def helpers(environment: str, config_dir: Optional[str]
            ) -> Tuple[DatabaseHelper, DatabaseHelper]:
    """This thread's (source, target) helpers, opened once and reused."""
    pair = getattr(_LOCAL, 'pair', None)
    if pair is None:
        source = DatabaseHelper(environment=environment, config_path=config_dir)
        source.connect_pyodbc()
        source.connect_sqlalchemy()
        target = source.archive_database_helper()
        target.connect_pyodbc()
        target.connect_sqlalchemy()
        pair = (source, target)
        _LOCAL.pair = pair
        with _OPENED_LOCK:
            _OPENED.append(pair)
    return pair


def close_helpers() -> None:
    """Close every connection any worker opened. Called once, at the end."""
    with _OPENED_LOCK:
        pairs, _OPENED[:] = list(_OPENED), []
    for pair in pairs:
        for helper in pair:
            try:
                helper.close_connections()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# The copy
# ----------------------------------------------------------------------------

def same_instance(source: DatabaseHelper, target: DatabaseHelper) -> bool:
    left = str(source.config.get('SERVER', '')).strip().lower()
    right = str(target.config.get('SERVER', '')).strip().lower()
    return bool(left) and left == right


def use_cross_database_sql(source: DatabaseHelper, target: DatabaseHelper) -> bool:
    """True when a three-part-name INSERT ... SELECT will work.

    Azure SQL has no cross-database queries however close the two databases sit,
    so the server has to be a normal instance as well as the same one.
    """
    return same_instance(source, target) and not source.is_azure()


def copy_cross_database(source: DatabaseHelper, target_database: str,
                        table_name: str) -> int:
    """INSERT ... SELECT into the archive database, entirely on the server."""
    statement = (
        f'INSERT INTO {quote_identifier(target_database)}.'
        f'{quote_identifier(TARGET_SCHEMA)}.{quote_identifier(table_name)} '
        f'SELECT * FROM {quote_identifier(ARCHIVE_SCHEMA)}.'
        f'{quote_identifier(table_name)}'
    )
    connection = source.pyodbc_connection or source.connect_pyodbc()
    cursor = connection.cursor()
    try:
        cursor.execute(statement)
        copied = cursor.rowcount
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return max(0, int(copied))


def copy_via_bcp(source: DatabaseHelper, target: DatabaseHelper,
                 table_name: str) -> int:
    """bcp out of the archive schema, bcp in to the archive database.

    Native format (-n). The tables are structurally identical - the target was
    generated from the source's own sys.columns, and the audit values live in
    the catalog rather than in columns - so no format file and no column mapping
    is needed, nothing is converted to text on the way through, and binary
    columns survive, which the old character-mode stream could not promise.
    """
    source_auth = source.bcp_auth_args()
    target_auth = target.bcp_auth_args()
    if not source_auth or not target_auth:
        ready, why = (source if not source_auth else target).bcp_ready()
        raise RuntimeError(why or 'bcp could not authenticate')

    work_dir = tempfile.mkdtemp(prefix='sweep_')
    data_path = os.path.join(work_dir, f'{table_name}.dat')
    error_path = os.path.join(work_dir, f'{table_name}.err')
    try:
        out = subprocess.run(
            ['bcp', f'{ARCHIVE_SCHEMA}.[{table_name}]', 'out', data_path, '-n']
            + source_auth,
            capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError(f'bcp out failed: {out.stdout} {out.stderr}'.strip())

        into = subprocess.run(
            ['bcp', f'{TARGET_SCHEMA}.[{table_name}]', 'in', data_path, '-n',
             '-b', str(BCP_BATCH_SIZE), '-m', str(BCP_MAX_ERRORS),
             '-e', error_path] + target_auth,
            capture_output=True, text=True)
        if into.returncode != 0:
            raise RuntimeError(f'bcp in failed: {into.stdout} {into.stderr}'.strip())

        return DatabaseHelper._parse_bcp_rows_copied(into.stdout)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def row_count(db: DatabaseHelper, schema: str, table_name: str) -> int:
    frame = db.execute_query(
        f'SELECT COUNT_BIG(*) AS n FROM {quote_identifier(schema)}.'
        f'{quote_identifier(table_name)}')
    return int(frame.iloc[0, 0]) if not frame.empty else 0


# ----------------------------------------------------------------------------
# One table
# ----------------------------------------------------------------------------

def sweep_table(environment: str, config_dir: Optional[str],
                row: Dict[str, Any]) -> Dict[str, Any]:
    """Copy one archived table to the archive database, then drop the original."""
    table_name = str(row['ArchiveTable'])
    result: Dict[str, Any] = {
        'table': table_name, 'success': False, 'rows': 0, 'error': '',
        'method': '', 'seconds': 0.0,
    }
    started = time.time()

    try:
        source, target = helpers(environment, config_dir)

        columns = read_columns(source, table_name, ARCHIVE_SCHEMA)
        if not columns:
            result['error'] = (f'{ARCHIVE_SCHEMA}.{table_name} has no columns, or '
                               f'disappeared between listing and copying')
            return result

        expected = row_count(source, ARCHIVE_SCHEMA, table_name)

        # A previous attempt that failed after creating the target leaves one
        # behind; it holds at most a partial copy, so it is replaced rather
        # than added to.
        target.execute_non_query(
            f"IF OBJECT_ID(N'{TARGET_SCHEMA}.{table_name}', N'U') IS NOT NULL "
            f'DROP TABLE {quote_identifier(TARGET_SCHEMA)}.'
            f'{quote_identifier(table_name)}')
        target.execute_non_query(
            create_table_statement(table_name, columns, TARGET_SCHEMA))

        if use_cross_database_sql(source, target):
            result['method'] = 'cross-database SQL'
            copy_cross_database(source, target.config['DATABASE'], table_name)
        else:
            result['method'] = 'bcp native'
            copy_via_bcp(source, target, table_name)

        # The count on the far side, not what the copy claimed. Nothing is
        # dropped on the strength of a return value.
        landed = row_count(target, TARGET_SCHEMA, table_name)
        result['rows'] = landed
        if landed != expected:
            result['error'] = (f'row count mismatch: {ARCHIVE_SCHEMA} holds '
                               f'{expected:,}, {target.config["DATABASE"]} took '
                               f'{landed:,}. Source kept.')
            return result

        target.execute_non_query(
            f'DELETE FROM {quote_identifier(TARGET_SCHEMA)}.'
            f'{quote_identifier(ARCHIVE_CATALOG)} WHERE ArchiveTable = ?;'
            f'INSERT INTO {quote_identifier(TARGET_SCHEMA)}.'
            f'{quote_identifier(ARCHIVE_CATALOG)} (ArchiveTable, StagingTable, '
            f'EntityCode, LoadID, CreateTS, RowsArchived, SessionID, RunID, '
            f'SourceDb, SweptTS) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            params=(table_name, table_name, row['StagingTable'], row['EntityCode'],
                    row['LoadID'], row['CreateTS'], landed, row['SessionID'],
                    row['RunID'], row['SourceDb'], datetime.now()))

        # Only now, with the rows counted on the other side and the metadata
        # written, is the original expendable.
        source.execute_non_query(
            f'DROP TABLE {quote_identifier(ARCHIVE_SCHEMA)}.'
            f'{quote_identifier(table_name)}')
        source.execute_non_query(
            f'UPDATE {quote_identifier(ARCHIVE_SCHEMA)}.'
            f'{quote_identifier(ARCHIVE_CATALOG)} SET SweptTS = ? '
            f'WHERE ArchiveTable = ?',
            params=(datetime.now(), table_name))

        result['success'] = True
        return result
    except Exception as e:
        result['error'] = f'{type(e).__name__}: {e}'
        return result
    finally:
        result['seconds'] = time.time() - started


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    environment, config_dir = resolve_environment(args)

    source = DatabaseHelper(environment=environment, config_path=config_dir)
    source.connect_sqlalchemy()
    target = source.archive_database_helper()

    print(f'Sweeping {environment}: {ARCHIVE_SCHEMA} in '
          f'{source.config["DATABASE"]} -> {target.config["DATABASE"]} on '
          f'{source.config["SERVER"]}')

    try:
        rows = pending(source, args)
    except Exception as e:
        print(f'Cannot read {ARCHIVE_SCHEMA}.{ARCHIVE_CATALOG} in '
              f'{source.config["DATABASE"]}: {e}')
        print('The archive schema is created by '
              'SQL/Schemas/Migrations/006.archive_schema.sql.')
        source.close_connections()
        return 1

    if not rows:
        print('Nothing to sweep.')
        source.close_connections()
        return 0

    total = sum(int(row['RowsArchived'] or 0) for row in rows)
    print(f'{len(rows)} table(s), about {total:,} row(s):')
    for row in rows:
        print(f"  {row['ArchiveTable']:<40} {int(row['RowsArchived'] or 0):>12,} "
              f"row(s)  archived {row['CreateTS']}")

    if args.dry_run:
        print('\nDRY RUN: nothing was copied, dropped or marked swept.')
        source.close_connections()
        return 0

    try:
        target.connect_pyodbc()
        ensure_target_catalog(target)
    except Exception as e:
        print(f'\nCannot reach {target.config["DATABASE"]}: {e}')
        print('Create it with SQL/Schemas/Migrations/004.migration_data_archive.sql.')
        source.close_connections()
        return 1
    finally:
        target.close_connections()
    source.close_connections()

    workers = max(1, args.workers)
    print(f'\nCopying with {workers} worker(s)...')
    started = time.time()
    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(sweep_table, environment, config_dir, row):
                   row['ArchiveTable'] for row in rows}
        try:
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result['success']:
                    print(f"  {result['table']:<40} {result['rows']:>12,} row(s) "
                          f"in {result['seconds']:.1f}s ({result['method']})")
                else:
                    print(f"  {result['table']:<40} FAILED - {result['error']}")
        finally:
            pool.shutdown(wait=True)

    # The workers are gone but their connections are not; see _OPENED.
    close_helpers()

    elapsed = time.time() - started
    swept = sum(1 for r in results if r['success'])
    moved = sum(r['rows'] for r in results if r['success'])
    failed = [r for r in results if not r['success']]

    print(f'\n{swept} table(s) swept, {moved:,} row(s), {len(failed)} failed, '
          f'in {elapsed:.1f}s')
    if failed:
        print('Nothing was dropped for the failures; re-run to retry them.')
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
