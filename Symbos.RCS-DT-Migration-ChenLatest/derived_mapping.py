"""Shared write and check for mapping steps that fill a derived ID column.

Staging extract columns keep exactly what the customer sent. A mapping step resolves
each distinct value to a lookup ID in Python and writes it to a derived INT column of
the same staging table (named <source column>_<lookup ID column>, declared in the
table's schema file and in process_staging.DERIVED_STAGING_COLUMNS). The migration SQL
reads that column instead of joining the source text to a lookup label.

The source column is only ever read. Every function here matches on the cleaned value
(clean_sql), and the services read their distinct values through the same expression,
so the two sides of the join always agree.
"""

from typing import Any, Iterable, List, Optional, Tuple

import pandas as pd


# NBSP, tab, CR and LF become spaces before trimming. The extracts carry all four, and
# LTRIM/RTRIM only trim spaces, so this is what makes a value with a trailing tab or
# NBSP resolve like the bare one.
_CLEAN = (
    "LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(REPLACE("
    "CAST({column} AS NVARCHAR(4000)), NCHAR(160), ' '), CHAR(9), ' '), "
    "CHAR(10), ' '), CHAR(13), ' ')))"
)

# Which rows still without an ID take the default.
DEFAULT_NONE = 'none'
DEFAULT_BLANK = 'blank'          # NULL or blank source only
DEFAULT_UNMAPPED = 'unmapped'    # non-blank source that resolved to nothing
DEFAULT_ALL = 'all'              # every row left without an ID

_DEFAULT_CONDITIONS = {
    DEFAULT_BLANK: "ISNULL({clean}, '') = ''",
    DEFAULT_UNMAPPED: "ISNULL({clean}, '') <> ''",
    DEFAULT_ALL: '1 = 1',
}


def clean_sql(column_ref: str) -> str:
    """The cleaned NVARCHAR(4000) form of a column, e.g. clean_sql('rc.[MA_Status]')."""
    return _CLEAN.format(column=column_ref)


def column_exists(db_helper: Any, table: str, column: str) -> bool:
    if not db_helper:
        return False
    frame = db_helper.execute_query(
        f"""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = '{table}'
          AND COLUMN_NAME = '{column}'
        """
    )
    return not frame.empty


def missing_column_message(table: str, column: str) -> str:
    """The fatal error for an environment whose staging schema predates the column."""
    return (
        f'{table}.{column} does not exist; the staging schema predates it. Run: '
        f'python tools/deploy_schemas.py <env> --file "{table} Schema.sql"'
    )


def read_distinct_values(db_helper: Any, table: str, column: str, alias: str) -> pd.DataFrame:
    """Distinct cleaned non-blank values of table.column, as a one-column frame."""
    if not db_helper:
        return pd.DataFrame(columns=[alias])
    clean = clean_sql(f'[{column}]')
    frame = db_helper.execute_query(
        f"""
        SELECT DISTINCT {clean} AS [{alias}]
        FROM {table}
        WHERE {clean} <> ''
        """
    )
    if frame.empty or alias not in frame.columns:
        return pd.DataFrame(columns=[alias])
    return frame


def assign_ids(
    db_helper: Any,
    table: str,
    source_column: str,
    target_column: str,
    pairs: Iterable[Tuple[str, int]],
    default_id: Optional[int] = None,
    default_scope: str = DEFAULT_NONE,
) -> Tuple[int, int]:
    """Fill table.target_column from table.source_column; returns (mapped, defaulted).

    One transaction: clear the column, set the ID of every row whose cleaned source
    value is in `pairs`, then give `default_id` to the rows still without one that
    `default_scope` covers. Clearing first means a re-run, or a changed mapping file,
    always lands on exactly what the current config says.
    """
    if not db_helper or not getattr(db_helper, 'pyodbc_connection', None):
        return 0, 0

    rows = sorted({(str(raw), int(ident)) for raw, ident in pairs})
    clean = clean_sql(f'rc.[{source_column}]')
    connection = db_helper.pyodbc_connection
    cursor = connection.cursor()

    def rowcount() -> int:
        cursor.execute('SELECT @@ROWCOUNT')
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    try:
        cursor.execute(
            f'UPDATE {table} SET [{target_column}] = NULL '
            f'WHERE [{target_column}] IS NOT NULL'
        )

        mapped = 0
        if rows:
            # Shared sessions can process several customers; clear any earlier copy.
            cursor.execute(
                "IF OBJECT_ID('tempdb..#DerivedIdResolution') IS NOT NULL "
                'DROP TABLE #DerivedIdResolution'
            )
            cursor.execute(
                'CREATE TABLE #DerivedIdResolution ('
                'raw_value NVARCHAR(4000) NOT NULL, resolved_id INT NOT NULL)'
            )
            cursor.executemany(
                'INSERT INTO #DerivedIdResolution (raw_value, resolved_id) VALUES (?, ?)',
                rows,
            )
            cursor.execute(
                f"""
                UPDATE rc
                SET rc.[{target_column}] = r.resolved_id
                FROM {table} AS rc
                INNER JOIN #DerivedIdResolution AS r
                    ON {clean} = r.raw_value
                """
            )
            mapped = rowcount()
            cursor.execute('DROP TABLE #DerivedIdResolution')

        defaulted = 0
        if default_id is not None and default_scope in _DEFAULT_CONDITIONS:
            condition = _DEFAULT_CONDITIONS[default_scope].format(clean=clean)
            cursor.execute(
                f"""
                UPDATE rc
                SET rc.[{target_column}] = ?
                FROM {table} AS rc
                WHERE rc.[{target_column}] IS NULL
                  AND {condition}
                """,
                int(default_id),
            )
            defaulted = rowcount()

        connection.commit()
        return mapped, defaulted

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def read_unresolved_values(
    db_helper: Any,
    table: str,
    source_column: str,
    target_column: str,
) -> List[str]:
    """Distinct cleaned non-blank source values whose derived ID is still NULL."""
    if not db_helper:
        return []
    clean = clean_sql(f'[{source_column}]')
    frame = db_helper.execute_query(
        f"""
        SELECT DISTINCT {clean} AS UnresolvedValue
        FROM {table}
        WHERE [{target_column}] IS NULL
          AND {clean} <> ''
        """
    )
    if frame.empty or 'UnresolvedValue' not in frame.columns:
        return []
    return sorted(str(v) for v in frame['UnresolvedValue'].dropna().tolist())
