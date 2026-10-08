"""Run the staging archive on its own, outside a migration.

The migration archives the RC_* staging tables as its last step per customer, so
exercising that step normally means sitting through a whole run. This does the
same thing against whatever is in the staging tables right now:

    python tools/archive_staging.py dev --entity-code SM9596 --dry-run
    python tools/archive_staging.py dev --entity-code SM9596 --load-id 1
    python tools/archive_staging.py dev --entity-code SM9596 --load-id 1 \
        --table RC_NOTES_EXTRACT

--entity-code is required: it is the customer code the archived tables are named
after - SM9596_RC_NOTES_EXTRACT - so without it there is nothing to call them.

What this does per table, in one transaction for all of them:

    dbo.RC_NOTES_EXTRACT -> archive.SM9596_RC_NOTES_EXTRACT     (sp_rename)
    a fresh empty dbo.RC_NOTES_EXTRACT                          (its schema file)
    a row in archive.ArchiveCatalog                             (LoadID, rows, ...)

So it MOVES the staging tables rather than copying them, and the staging tables
it leaves behind are empty. That is what the migration does too - the next
customer truncates them anyway - but it is worth knowing before running this
against staging you still wanted to look at.

Re-running for the same customer replaces that customer's previous archive
tables: latest load wins.

Without --table it covers every table in variables/table_keywords.json.
--config points at an environment file (or the directory holding one) outside
config/, and --variables at another folder holding table_keywords.json.

--dry-run prints the statements it would run, per table, and changes nothing.

The archive schema and its catalog are created once per environment by
SQL/Schemas/Migrations/006.archive_schema.sql; this reports rather than creates
them. tools/sweep_archive.py moves the archived tables on to ARCHIVE_DATABASE.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TOOLS_DIR)

from db_manager import DatabaseHelper  # noqa: E402
from schema_files import SchemaSetError, load_staging_schema_files  # noqa: E402
from staging_archive import (  # noqa: E402
    StagingRenamer,
    archive_timestamp,
    validate_customer_code,
)
from env_target import (  # noqa: E402  - tools/, alongside this script
    TABLE_KEYWORDS_FILE,
    add_target_arguments,
    describe_target,
    resolve_environment,
    resolve_tables,
    resolve_variables_dir,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_target_arguments(parser, verb='Archive')
    parser.add_argument('--entity-code', required=True,
                        help='Customer code the archived tables are named after, '
                             'e.g. SM9596 -> archive.SM9596_RC_NOTES_EXTRACT')
    parser.add_argument('--load-id', type=int, default=None,
                        help='LoadID recorded in archive.ArchiveCatalog')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print the statements; change nothing')
    return parser.parse_args()


def print_table_result(table_name: str, result: Dict[str, Any],
                       archive_schema: str) -> None:
    if result['skipped']:
        print(f'  {table_name}: skipped - {result["reason"]}')
    else:
        print(f'  {table_name}: {result["rows"]:,} row(s) -> '
              f'{archive_schema}.{result["target_table"]}')


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

    environment, config_dir = resolve_environment(args)
    variables_dir = resolve_variables_dir(args)

    tables = resolve_tables(environment, variables_dir, args.tables)
    if not tables:
        print(f'No tables to archive: '
              f'{os.path.join(variables_dir, TABLE_KEYWORDS_FILE)} is empty or '
              f'missing, and no --table was given')
        return 1

    print(describe_target(environment, config_dir, variables_dir, tables, args.tables))

    # Both checks before the connection. Neither needs a database, and a run
    # that cannot possibly work should say so without logging in first.
    try:
        validate_customer_code(args.entity_code)
    except ValueError as e:
        print(f'Will not archive: {e}')
        return 1

    try:
        schema_files = load_staging_schema_files(tables)
    except SchemaSetError as e:
        print(f'Will not archive: {e}')
        print('Renaming a staging table away without a file to rebuild it from '
              'would leave the next migration run without that table.')
        return 1

    db = DatabaseHelper(environment=environment, config_path=config_dir)
    db.connect_pyodbc()
    db.connect_sqlalchemy()

    renamer = StagingRenamer(
        db=db,
        customer_code=args.entity_code,
        tables=tables,
        schema_files=schema_files,
    )

    context = {
        'loadid': args.load_id,
        'createts': archive_timestamp(),
        'entitycode': args.entity_code,
        'db': environment,
    }

    try:
        summary = renamer.archive_all(context, dry_run=args.dry_run)
    finally:
        db.close_connections()

    print()
    print(f'{"DRY RUN " if args.dry_run else ""}Archive as '
          f'{summary["customer_code"]}_* in {summary["schema"]} (renamed, not copied)')
    for table_name, result in summary['tables'].items():
        print_table_result(table_name, result, summary['schema'])
    print(f'  {summary["tables_archived"]} archived, '
          f'{summary["tables_skipped"]} skipped, '
          f'{summary["rows_archived"]:,} row(s)')

    for error in summary['errors']:
        print(f'  ERROR: {error}')

    if args.dry_run and summary['statements']:
        print()
        print('Statements that would run, in one transaction:')
        for statement in summary['statements']:
            print(f'    {" ".join(statement.split())[:160]}')

    return 0 if summary['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
