r"""Run a named set of SQL/Schemas files against one environment's connection.

The migration deploys no schema of its own: process_staging checks the staging
tables exist and stops the run if one does not, telling you to "deploy the
matching schema from SQL/Schemas". This is the step that does that, for a set of
files defined in variables/schema_sets.json rather than one file at a time:

    python tools/deploy_schemas.py dev --list           -- the sets and what is in them
    python tools/deploy_schemas.py dev --dry-run        -- what the default set would do here
    python tools/deploy_schemas.py dev                  -- run it
    python tools/deploy_schemas.py dev --set migrations
    python tools/deploy_schemas.py dev --file "RC_SMS Schema.sql"

The environment is config/<env>.env by default; --config points somewhere else,
either at the file itself or at the directory holding it, exactly as the archive
tools take it. --database runs the same files against another database on that
same server, which is how anything but the environment's own DATABASE is
reached - the schema files carry no USE of their own.

These files are not migrations. Nearly every one of them opens with DROP TABLE,
so running one against a populated table destroys what it holds. For the staging
extracts that costs nothing - they are truncated per customer anyway - but for
the mapping and history tables it is permanent, so schema_sets.json names those
in protected_tables and this refuses to drop one that holds rows unless --force
says to. Every run prints the plan first, with the row count of each table it
would drop, and asks before doing anything; --yes answers that in advance, which
is also how this runs unattended.

Batches are split on GO the way sqlcmd splits them, ignoring a GO inside a
comment or a string, and each batch is committed as it succeeds. A file that
fails part way is therefore part applied: fix the cause and run it again - the
DROP guards make that safe - rather than assuming it rolled back. PRINT output
and any result sets come back per batch, which is what makes the additive
Migrations/*.sql files readable here (they report what they skipped).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TOOLS_DIR)

from db_manager import DatabaseHelper  # noqa: E402
from schema_files import (  # noqa: E402  - repo root, shared with the archive step
    Batch,
    SchemaFile,
    SchemaSetError,
    deduplicate as _deduplicate,
    expand_set,
    load_manifest as _load_manifest,
    resolve_files,
    split_batches,
    tables_touched,
)
from env_target import (  # noqa: E402  - tools/, alongside this script
    DEFAULT_CONFIG_DIR,
    DEFAULT_VARIABLES_DIR,
    resolve_environment,
)

SCHEMA_DIR = os.path.join(REPO_ROOT, 'SQL', 'Schemas')
DEFAULT_MANIFEST = os.path.join(DEFAULT_VARIABLES_DIR, 'schema_sets.json')

# Result rows printed per batch. The schema files return none; the additive
# migrations and any report-style script return a handful, and a cap keeps a
# stray SELECT * from filling the terminal.
MAX_RESULT_ROWS = 20


def load_manifest(path: str) -> Dict[str, Any]:
    """As schema_files.load_manifest, but exiting rather than raising.

    This is a CLI: a broken set list is a message and a non-zero status, not a
    traceback. The library raises so that a migration run can catch it.
    """
    try:
        return _load_manifest(path)
    except SchemaSetError as error:
        raise SystemExit(str(error))


def required_tables() -> List[str]:
    """Staging tables a migration run will not start without.

    The same two lists process_staging checks: the table_keywords tables it
    loads CSVs into, and the derived tables nothing loads but everything after
    the load expects. Imported rather than copied so this cannot drift from what
    the run actually demands; if that import fails, coverage is simply not
    reported.
    """
    try:
        from process_staging import ADDITIONAL_REQUIRED_TABLES
        with open(os.path.join(DEFAULT_VARIABLES_DIR, 'table_keywords.json'),
                  encoding='utf-8') as handle:
            keywords = json.load(handle)
    except Exception:
        return []

    tables = [name for name in keywords.values() if name]
    tables.extend(ADDITIONAL_REQUIRED_TABLES)
    return tables


# ----------------------------------------------------------------------------
# The plan
# ----------------------------------------------------------------------------

def existing_row_counts(db: DatabaseHelper, tables: Sequence[str]) -> Dict[str, int]:
    """Row count per table that exists, from the catalog rather than a scan.

    sys.partitions is what SSMS reports and is maintained by the engine, so this
    stays instant on a staging table holding millions of rows - which matters,
    because this runs before the confirmation prompt on a contended server.
    """
    if not tables:
        return {}

    placeholders = ', '.join('?' for _ in tables)
    query = f"""
        SELECT      t.name, SUM(p.rows)
        FROM        sys.tables t
        JOIN        sys.partitions p
                      ON p.object_id = t.object_id AND p.index_id IN (0, 1)
        WHERE       t.name IN ({placeholders})
        GROUP BY    t.name
    """
    cursor = db.pyodbc_connection.cursor()
    try:
        cursor.execute(query, list(tables))
        return {row[0]: int(row[1] or 0) for row in cursor.fetchall()}
    finally:
        cursor.close()


def print_plan(files: List[SchemaFile], counts: Dict[str, int],
               protected: Dict[str, str], target: str) -> None:
    print()
    print(f'Plan for {target}')
    for schema in files:
        if not schema.exists:
            print(f'  {schema.relative_path}: MISSING - {schema.path}')
            continue
        if not schema.batches:
            print(f'  {schema.relative_path}: nothing to run (no executable '
                  f'statements)')
            continue

        detail = f'{len(schema.batches)} batch(es)'
        if schema.creates:
            detail += f', creates {", ".join(schema.creates)}'
        print(f'  {schema.relative_path}: {detail}')

        for table in schema.drops:
            if table not in counts:
                print(f'      drops {table}: not present here')
                continue
            rows = counts[table]
            note = (f'      drops {table}: present, empty' if rows == 0
                    else f'      drops {table}: {rows:,} row(s) lost')
            if table in protected:
                note += f'  PROTECTED - {protected[table]}'
            print(note)


def blocked_files(files: List[SchemaFile], counts: Dict[str, int],
                  protected: Dict[str, str]) -> Dict[str, List[str]]:
    """File -> protected tables it would drop that are not empty."""
    blocked: Dict[str, List[str]] = {}
    for schema in files:
        at_risk = [table for table in schema.drops
                   if table in protected and counts.get(table, 0) > 0]
        if at_risk:
            blocked[schema.relative_path] = at_risk
    return blocked


def report_coverage(files: List[SchemaFile]) -> None:
    """Staging tables the run needs that nothing in this set creates.

    Only worth saying when the run is deploying staging at all: a set that
    creates none of them - the migrations, or one file named with --file - is
    not trying to, and listing all 27 as missing would be noise.
    """
    needed = required_tables()
    if not needed:
        return

    created = {name.lower() for schema in files for name in schema.creates}
    missing = [table for table in needed if table.lower() not in created]
    if missing and len(missing) < len(needed):
        print()
        print(f'Note: {len(missing)} table(s) a migration run needs are not in '
              f'this set: {", ".join(sorted(missing))}')
        print('      Already deployed is fine; absent from the database is not - '
              'process_staging stops the run for a missing staging table.')


# ----------------------------------------------------------------------------
# Running
# ----------------------------------------------------------------------------

def drain_messages(cursor: Any) -> List[str]:
    """PRINT and RAISERROR-with-severity-10 text pyodbc collected, if any."""
    messages = getattr(cursor, 'messages', None) or []
    text: List[str] = []
    for message in messages:
        body = message[1] if isinstance(message, (list, tuple)) else str(message)
        # The driver prefixes its own [Microsoft][ODBC ...][SQL Server] noise.
        body = re.sub(r'^(\[[^\]]*\])+', '', str(body)).strip()
        if body:
            text.append(body)
    return text


def run_batch(connection: Any, sql: str) -> List[str]:
    """Execute one batch; return its PRINT output and any rows it returned."""
    output: List[str] = []
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        while True:
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
                output.append(' | '.join(columns))
                for row in rows[:MAX_RESULT_ROWS]:
                    output.append(' | '.join('NULL' if value is None else str(value)
                                             for value in row))
                if len(rows) > MAX_RESULT_ROWS:
                    output.append(f'... more rows not shown (first '
                                  f'{MAX_RESULT_ROWS} only)')
            output.extend(drain_messages(cursor))
            if not cursor.nextset():
                break
    finally:
        try:
            output.extend(drain_messages(cursor))
        except Exception:
            pass
        cursor.close()
    return output


def run_file(connection: Any, schema: SchemaFile) -> Tuple[bool, float]:
    """Run every batch in one file, stopping at the first that fails."""
    started = time.time()
    for index, batch in enumerate(schema.batches, start=1):
        try:
            for line in run_batch(connection, batch.sql):
                print(f'      {line}')
        except Exception as exception:
            schema.error = (f'batch {index} of {len(schema.batches)} '
                            f'(line {batch.line}): {exception}')
            return False, time.time() - started
    return True, time.time() - started


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('environment', nargs='?', default=None,
                        help='Environment name, e.g. dev, v10, testse. Optional '
                             'when --config names an environment file, whose own '
                             'name is then the environment')
    parser.add_argument('--config', dest='config_path', default=None, metavar='PATH',
                        help='Environment file to use, or the directory holding '
                             f'<env>.env. Default: {DEFAULT_CONFIG_DIR}')
    parser.add_argument('--manifest', default=DEFAULT_MANIFEST, metavar='PATH',
                        help=f'The set list. Default: {DEFAULT_MANIFEST}')
    parser.add_argument('--schema-dir', default=SCHEMA_DIR, metavar='DIR',
                        help=f'Folder the files are relative to. Default: {SCHEMA_DIR}')
    parser.add_argument('--set', action='append', dest='sets', default=None,
                        metavar='NAME',
                        help='Set to run (repeatable). Default: the manifest\'s '
                             'default_set')
    parser.add_argument('--file', action='append', dest='files', default=None,
                        metavar='PATH',
                        help='Run this file instead of a set (repeatable), '
                             'relative to --schema-dir')
    parser.add_argument('--database', default=None, metavar='NAME',
                        help='Run against this database on the same server '
                             'instead of the environment\'s own DATABASE')
    parser.add_argument('--list', action='store_true',
                        help='Print the sets and what is in them; connect to nothing')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report the plan and the rows at risk; run nothing')
    parser.add_argument('--yes', action='store_true',
                        help='Skip the confirmation prompt. Required to run '
                             'unattended')
    parser.add_argument('--force', action='store_true',
                        help='Allow a file that drops a protected table holding '
                             'rows. Destroys that data')
    parser.add_argument('--continue-on-error', action='store_true',
                        help='Carry on to the next file after one fails. Default '
                             'is to stop')
    return parser.parse_args()


def list_sets(manifest: Dict[str, Any], schema_dir: str) -> int:
    default = manifest.get('default_set')
    protected = manifest.get('protected_tables', {})

    for name in manifest['sets']:
        definition = manifest['sets'][name]
        files = expand_set(manifest, name)
        marker = '  (default)' if name == default else ''
        print()
        print(f'{name}{marker} - {len(files)} file(s)')
        description = definition.get('description')
        if description:
            for line in _wrap(description, 88):
                print(f'    {line}')
        for relative in files:
            schema = SchemaFile(relative, schema_dir)
            flags = []
            if not schema.exists:
                flags.append('MISSING')
            for table in schema.drops:
                if table in protected:
                    flags.append(f'drops protected {table}')
            suffix = f'   [{"; ".join(flags)}]' if flags else ''
            print(f'      {relative}{suffix}')

    print()
    print(f'Protected tables: {", ".join(sorted(protected)) or "none"}')
    return 0


def _wrap(text: str, width: int) -> List[str]:
    words, lines, current = text.split(), [], ''
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f'{current} {word}'.strip()
    if current:
        lines.append(current)
    return lines


def confirm(prompt: str) -> bool:
    """Ask, and treat anything but an explicit yes - including no terminal - as no."""
    unattended = (f'No answer available, so nothing was run. Pass --yes to run '
                  f'unattended.')
    try:
        if not sys.stdin or not sys.stdin.isatty():
            print(f'{prompt}  {unattended}')
            return False
        return input(f'{prompt} [y/N] ').strip().lower() in ('y', 'yes')
    except (EOFError, OSError):
        print(f'\n{unattended}')
        return False


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    manifest = load_manifest(args.manifest)
    schema_dir = os.path.abspath(args.schema_dir)
    protected: Dict[str, str] = manifest.get('protected_tables', {})

    if args.list:
        return list_sets(manifest, schema_dir)

    relative_paths, set_names = resolve_files(manifest, args.sets or [],
                                              args.files or [])
    if not relative_paths:
        print('Nothing to run: the set is empty')
        return 1

    files = [SchemaFile(path, schema_dir) for path in relative_paths]
    missing = [schema.relative_path for schema in files if not schema.exists]

    environment, config_dir = resolve_environment(args)
    source = f'--set {", ".join(set_names)}' if set_names else '--file'
    print(f'Environment {environment} '
          f'({os.path.join(config_dir, environment + ".env")}), '
          f'{len(files)} file(s) from {source}')

    db = DatabaseHelper(environment=environment, config_path=config_dir)
    if args.database:
        db = db.for_database(args.database)

    try:
        connection = db.connect_pyodbc()
    except Exception as exception:
        print(f'Cannot reach {db.config["DATABASE"]} on {db.config["SERVER"]}: '
              f'{exception}')
        return 1

    target = f'{db.config["DATABASE"]} on {db.config["SERVER"]}'
    exit_code = 0

    try:
        at_risk = sorted({table for schema in files for table in schema.drops})
        counts = existing_row_counts(db, at_risk)

        print_plan(files, counts, protected, target)
        report_coverage(files)

        if missing:
            print()
            print(f'{len(missing)} file(s) in the set do not exist: '
                  f'{", ".join(missing)}')
            print('Fix the set list or the path before running.')
            return 1

        blocked = blocked_files(files, counts, protected)
        if blocked and not args.force:
            print()
            for relative, tables in blocked.items():
                names = ', '.join(tables)
                verb = 'hold' if len(tables) > 1 else 'holds'
                print(f'Refusing {relative}: it drops {names}, which {verb} rows '
                      f'nothing reloads.')
            print('Run the files that are not refused with --file, or --force to '
                  'drop these and lose their rows.')
        elif blocked:
            print()
            print('--force: protected tables will be dropped and their rows lost.')

        refused = bool(blocked) and not args.force
        runnable = [schema for schema in files if schema.batches]
        if args.dry_run:
            print()
            if refused:
                print(f'DRY RUN - nothing would run against {target}: '
                      f'{len(blocked)} of {len(runnable)} file(s) refused above.')
            else:
                print(f'DRY RUN - {len(runnable)} file(s) would run against '
                      f'{target}. Nothing was changed.')
            return 1 if refused else 0
        if refused:
            return 1

        if not runnable:
            print()
            print('Nothing to run.')
            return 0

        # These files drop tables, so the prompt is the last thing between a
        # mistyped environment and a dropped table. --yes is the unattended path.
        if not args.yes:
            print()
            if not confirm(f'Run {len(runnable)} file(s) against {target}?'):
                print('Nothing was run.')
                return 1

        # sqlcmd's semantics: each batch stands on its own, committed as it
        # succeeds. An explicit transaction spanning a DROP and its CREATE would
        # roll back further than the DROP guards expect, and would bar the
        # statements SQL Server will not run inside one.
        connection.autocommit = True

        print()
        applied = 0
        failures = 0
        stopped_before = 0
        for position, schema in enumerate(files):
            if not schema.batches:
                print(f'{schema.relative_path}: nothing to run')
                continue
            print(f'{schema.relative_path}: {len(schema.batches)} batch(es)')
            ok, elapsed = run_file(connection, schema)
            if ok:
                applied += 1
                print(f'   done in {elapsed:.1f}s')
                continue

            failures += 1
            print(f'   FAILED after {elapsed:.1f}s - {schema.error}')
            if not args.continue_on_error:
                stopped_before = sum(1 for later in files[position + 1:]
                                     if later.batches)
                print('   Stopping. Earlier files are already committed; this '
                      'one is applied as far as the batch above.')
                break

        print()
        print(f'{applied} file(s) applied, {failures} failed'
              + (f', {stopped_before} not attempted' if stopped_before else '')
              + f', against {target}')
        exit_code = 1 if failures else 0

        if not failures and set_names:
            print(f'Verify with: python tools/deploy_schemas.py {environment} '
                  f'--set {" --set ".join(set_names)} --dry-run')
    finally:
        db.close_connections()

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
