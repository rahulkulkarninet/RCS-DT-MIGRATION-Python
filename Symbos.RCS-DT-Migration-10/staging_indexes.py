"""Switch staging nonclustered indexes off for the load and back on after it.

Every RC_* staging table carries 1-3 nonclustered indexes on its debt code
columns, and TRUNCATE keeps them, so each bcp batch was maintaining them row by
row. Building them once at the end is cheaper.

Only plain nonclustered rowstore indexes are touched:
  - never a clustered index: disabling one makes the table unreadable, and
    RC_STAGING_COSTS and RC_STAGING_NOTES_ACCOUNT have one;
  - never a unique index, primary key or unique constraint: disabling it would
    stop it being enforced during the load, and the rebuild would then fail.

The SQL phase depends on these indexes (see staging_archive.py - "turned a 15
second step into hours"), so the rebuild runs in a finally after each table's
load, and rebuild_disabled is called again before the SQL phase as a guard
against a run that died between the two.
"""

from typing import Iterable, List, Tuple

from staging_archive import quote_identifier, quote_literal


def _table_list(tables: Iterable[str]) -> str:
    names = sorted({str(t) for t in tables if t})
    if not names:
        raise ValueError('no staging tables given')
    return ', '.join(quote_literal(n) for n in names)


def find_indexes_sql(tables: Iterable[str], disabled: bool) -> str:
    """Disableable indexes on the given dbo tables that are currently enabled
    (disabled=False) or disabled (disabled=True)."""
    return f"""
SELECT t.name AS table_name, i.name AS index_name
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE s.name = N'dbo'
  AND t.name IN ({_table_list(tables)})
  AND i.type = 2
  AND i.is_unique = 0
  AND i.is_primary_key = 0
  AND i.is_unique_constraint = 0
  AND i.is_disabled = {1 if disabled else 0}
ORDER BY t.name, i.name
"""


def disable_sql(table: str, index: str) -> str:
    return f'ALTER INDEX {quote_identifier(index)} ON dbo.{quote_identifier(table)} DISABLE'


def rebuild_sql(table: str, index: str) -> str:
    return f'ALTER INDEX {quote_identifier(index)} ON dbo.{quote_identifier(table)} REBUILD'


def _find(engine, tables: Iterable[str], disabled: bool) -> List[Tuple[str, str]]:
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text(find_indexes_sql(tables, disabled))).fetchall()
    return [(r[0], r[1]) for r in rows]


def disable(engine, tables: Iterable[str], logger) -> List[Tuple[str, str]]:
    """Disable the nonclustered indexes on these tables; returns what it disabled."""
    from sqlalchemy import text
    targets = _find(engine, tables, disabled=False)
    if not targets:
        return []
    with engine.begin() as conn:
        for table, index in targets:
            conn.execute(text(disable_sql(table, index)))
    logger.info(f'Disabled {len(targets)} staging index(es) for the load')
    return targets


def rebuild_disabled(engine, tables: Iterable[str], logger) -> List[Tuple[str, str]]:
    """Rebuild every disabled nonclustered index on these tables.

    One statement per index, each committed on its own, so one bad index does
    not leave the others disabled. Raises after trying them all if any failed.
    """
    from sqlalchemy import text
    targets = _find(engine, tables, disabled=True)
    failures = []
    for table, index in targets:
        try:
            with engine.begin() as conn:
                conn.execute(text(rebuild_sql(table, index)))
        except Exception as e:
            failures.append(f'{table}.{index}: {e}')
            logger.error(f'Rebuild failed for {table}.{index}: {e}')
    if targets:
        logger.info(f'Rebuilt {len(targets) - len(failures)}/{len(targets)} staging index(es): '
                    + ', '.join(f'{t}.{i}' for t, i in targets))
    if failures:
        raise RuntimeError(f'{len(failures)} staging index(es) still disabled: '
                           + '; '.join(failures))
    return targets
