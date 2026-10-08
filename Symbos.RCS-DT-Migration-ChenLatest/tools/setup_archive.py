

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Sequence, Tuple

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TOOLS_DIR)

from db_manager import DatabaseHelper  # noqa: E402
from drop_scope import load_drop_scope, plan_drops  # noqa: E402
from schema_files import (  # noqa: E402
    DEFAULT_SCHEMA_DIR,
    SchemaFile,
    SchemaSetError,
    deduplicate,
    expand_set,
    load_manifest,
)
from staging_archive import ARCHIVE_CATALOG, ARCHIVE_SCHEMA, quote_identifier  # noqa: E402
from env_target import DEFAULT_VARIABLES_DIR, resolve_environment  # noqa: E402

# The sets whose files describe tables that are supposed to be there.
EXPECTED_SETS = ('staging', 'support')

DEFAULT_MANIFEST = os.path.join(DEFAULT_VARIABLES_DIR, 'schema_sets.json')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('environment', nargs='?', default=None,
                        help='Environment name, e.g. dev')
    parser.add_argument('--config', dest='config_path', default=None,
                        metavar='PATH',
                        help='Environment file, or the directory holding it')
    parser.add_argument('--manifest', default=DEFAULT_MANIFEST,
                        help=f'Schema set list. Default: {DEFAULT_MANIFEST}')
    parser.add_argument('--archive', action='store_true',
                        help=f'Also consider {ARCHIVE_SCHEMA}.* tables that have '
                             f'already been swept to the archive database')
    parser.add_argument('--drop', action='store_true',
                        help='Drop the unexpected tables, after confirmation')
    parser.add_argument('--yes', action='store_true',
                        help='Answer the confirmation in advance')
    return parser.parse_args()


# ----------------------------------------------------------------------------
# What should be there
# ----------------------------------------------------------------------------

def expected_tables(manifest: Dict[str, Any], schema_dir: str) -> List[str]:
    """Every table the expected sets create, plus what the run demands.

    Read from the files rather than from their names: RC_DRINSURANCE.sql does
    not follow the "<TABLE> Schema.sql" convention the rest do, and a set list
    that grew another exception would be missed the same way.
    """
    tables: List[str] = []
    for set_name in EXPECTED_SETS:
        try:
            relative_paths = deduplicate(expand_set(manifest, set_name))
        except SchemaSetError:
            continue
        for relative_path in relative_paths:
            schema_file = SchemaFile(relative_path, schema_dir)
            tables.extend(schema_file.creates)

    try:
        from process_staging import ADDITIONAL_REQUIRED_TABLES
        tables.extend(ADDITIONAL_REQUIRED_TABLES)
    except Exception:
        pass

    seen, ordered = set(), []
    for name in tables:
        if name.lower() not in seen:
            seen.add(name.lower())
            ordered.append(name)
    return ordered


# ----------------------------------------------------------------------------
# What is there
# ----------------------------------------------------------------------------

def candidates(db: DatabaseHelper, scope: Dict[str, Any],
               include_archive: bool) -> List[Tuple[str, str]]:
    """(schema, table) pairs inside the declared scope, and nothing else.

    The scope is applied in the query, not after it. An application table is
    never fetched, never iterated and never in reach of a later bug.
    """
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    for index, prefix in enumerate(scope.get('dbo_prefixes', ())):
        key = f'prefix{index}'
        clauses.append(f"(s.name = 'dbo' AND LEFT(t.name, LEN(:{key})) = :{key})")
        params[key] = prefix

    if include_archive:
        for index, schema in enumerate(scope.get('schemas', ())):
            key = f'schema{index}'
            clauses.append(f's.name = :{key}')
            params[key] = schema

    if not clauses:
        return []

    query = f"""
    SELECT s.name AS schema_name, t.name AS table_name
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE {' OR '.join(clauses)}
    ORDER BY s.name, t.name
    """
    frame = db.execute_query(query, params=params)
    if frame.empty:
        return []
    return [(str(row['schema_name']), str(row['table_name']))
            for _, row in frame.iterrows()]


def swept_tables(db: DatabaseHelper) -> List[str]:
    """Archive tables the sweep has already copied out, so are safe to drop."""
    try:
        frame = db.execute_query(
            f'SELECT ArchiveTable FROM {quote_identifier(ARCHIVE_SCHEMA)}.'
            f'{quote_identifier(ARCHIVE_CATALOG)} WHERE SweptTS IS NOT NULL')
    except Exception:
        # No catalog means nothing has been swept, which is the safe reading.
        return []
    return [] if frame.empty else [str(name) for name in frame['ArchiveTable']]


def row_counts(db: DatabaseHelper, tables: Sequence[Tuple[str, str]]
               ) -> Dict[Tuple[str, str], int]:
    """Rows per table without scanning, for the confirmation prompt."""
    if not tables:
        return {}
    frame = db.execute_query("""
    SELECT s.name AS schema_name, t.name AS table_name,
           ISNULL(SUM(p.row_count), 0) AS row_count
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    LEFT JOIN sys.dm_db_partition_stats p
      ON p.object_id = t.object_id AND p.index_id IN (0, 1)
    GROUP BY s.name, t.name
    """)
    counts = {(str(r['schema_name']).lower(), str(r['table_name']).lower()):
              int(r['row_count']) for _, r in frame.iterrows()}
    return {(schema, table): counts.get((schema.lower(), table.lower()), 0)
            for schema, table in tables}


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    environment, config_dir = resolve_environment(args)

    try:
        manifest = load_manifest(args.manifest)
    except SchemaSetError as e:
        print(e)
        return 1

    scope = load_drop_scope(manifest)
    protected = list(manifest.get('protected_tables', {}))
    expected = expected_tables(manifest, DEFAULT_SCHEMA_DIR)

    if not expected:
        print(f'{args.manifest} named no tables. Refusing to go further: with an '
              f'empty expected set every table in scope would look unexpected.')
        return 1

    db = DatabaseHelper(environment=environment, config_path=config_dir)
    db.connect_sqlalchemy()

    print(f'Reconciling {environment}: {db.config["DATABASE"]} on '
          f'{db.config["SERVER"]}')
    print(f'  scope: dbo tables prefixed '
          f'{", ".join(scope["dbo_prefixes"]) or "(none)"}'
          + (f' + schema {", ".join(scope["schemas"])}' if args.archive else '')
          + f'; at most {scope["max_drops"]} drop(s)')
    print(f'  expected: {len(expected)} table(s) from '
          f'{", ".join(EXPECTED_SETS)}')

    try:
        found = candidates(db, scope, args.archive)
        swept = swept_tables(db)
    finally:
        pass

    present = {table.lower() for _, table in found}
    missing = [name for name in expected if name.lower() not in present]

    plan = plan_drops(found, expected, scope, protected, swept)
    counts = row_counts(db, [(s, t) for s, t, _ in plan['drop']])

    print()
    print(f'In scope and expected : {len(found) - len(plan["drop"])}')
    print(f'Expected but missing  : {len(missing)}')
    for name in missing:
        print(f'    {name}')
    if missing:
        print(f'    -> python tools/deploy_schemas.py {environment}')

    print(f'In scope, not expected: {len(plan["drop"])}')
    for schema, table, reason in plan['drop']:
        print(f'    {schema}.{table:<32} {counts.get((schema, table), 0):>10,} row(s)')

    kept = [(s, t, r) for s, t, r in plan['keep'] if r != 'expected by the schema set']
    if kept:
        print(f'In scope, kept anyway : {len(kept)}')
        for schema, table, reason in kept:
            print(f'    {schema}.{table:<32} {reason}')

    if plan['blocked']:
        print()
        print(f'REFUSING: {plan["reason"]}')
        db.close_connections()
        return 1

    if not plan['drop']:
        print()
        print('Nothing to drop.')
        db.close_connections()
        return 0

    if not args.drop:
        print()
        print('Report only. Re-run with --drop to remove the unexpected tables.')
        db.close_connections()
        return 0

    if not args.yes:
        print()
        print(f'About to DROP {len(plan["drop"])} table(s) from '
              f'{db.config["DATABASE"]} on {db.config["SERVER"]}. This cannot be '
              f'undone.')
        try:
            answer = input(f'Type the environment name ({environment}) to confirm: ')
        except EOFError:
            answer = ''
        if answer.strip() != environment:
            print('Not confirmed; nothing was dropped.')
            db.close_connections()
            return 1

    dropped, failed = 0, 0
    for schema, table, _ in plan['drop']:
        try:
            db.execute_non_query(f'DROP TABLE {quote_identifier(schema)}.'
                                 f'{quote_identifier(table)}')
            print(f'  dropped {schema}.{table}')
            dropped += 1
        except Exception as e:
            print(f'  FAILED {schema}.{table}: {type(e).__name__}: {e}')
            failed += 1

    db.close_connections()
    print(f'\n{dropped} dropped, {failed} failed')
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
