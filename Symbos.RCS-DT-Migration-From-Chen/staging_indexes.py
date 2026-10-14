"""Disable / rebuild the nonclustered indexes on the dbo.RC_* staging tables around a bulk load.

process_staging.py (Chen's 2026-10-05 drop) imports this module, but the drop did not include
it - neither Symbos.RCS-DT-Migration-Chen-Latest nor the repo had a staging_indexes.py, so the
tree could not even be imported. Written 2026-10-07 to the interface the callers use:

    staging_indexes.disable(engine, tables, logger)          -> list of 'table.index' disabled
    staging_indexes.rebuild_disabled(engine, tables, logger) -> list of 'table.index' rebuilt

Only NONCLUSTERED indexes are touched: disabling a clustered index makes the table unreadable,
and the join-key indexes the schemas create (e.g. IX_RC_TREATMENT_Full_Debt_Code) are all
nonclustered. rebuild_disabled only rebuilds indexes that are currently disabled, so it is safe
to call unconditionally before the SQL phase (customer_sql_workflow_service does exactly that).
Both functions are no-ops for tables that do not exist or have no such indexes.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

_LIST_SQL = """
SELECT  OBJECT_SCHEMA_NAME(i.object_id) AS schema_name,
        OBJECT_NAME(i.object_id)        AS table_name,
        i.name                          AS index_name
FROM    sys.indexes AS i
WHERE   i.object_id = OBJECT_ID(:table_name)
        AND i.type_desc = 'NONCLUSTERED'
        AND i.name IS NOT NULL
        AND i.is_disabled = :is_disabled
ORDER BY i.name
"""


def _qualified(table: str) -> str:
    """'RC_TREATMENT' -> 'dbo.RC_TREATMENT'; leave an already-qualified name alone."""
    table = table.strip().strip('[]')
    return table if '.' in table else f'dbo.{table}'


def _list_indexes(engine: Engine, table: str, disabled: bool):
    with engine.connect() as conn:
        rows = conn.execute(text(_LIST_SQL),
                            {'table_name': _qualified(table), 'is_disabled': 1 if disabled else 0}).fetchall()
    return [(r.schema_name, r.table_name, r.index_name) for r in rows]


def _alter(engine: Engine, tables: Iterable[str], action: str, want_disabled: bool,
           logger: Optional[logging.Logger]) -> List[str]:
    log = logger or logging.getLogger(__name__)
    touched: List[str] = []
    seen = set()
    for table in tables:
        key = _qualified(table).lower()
        if not table or key in seen:
            continue
        seen.add(key)
        for schema, tbl, idx in _list_indexes(engine, table, want_disabled):
            stmt = f'ALTER INDEX [{idx}] ON [{schema}].[{tbl}] {action}'
            with engine.begin() as conn:
                conn.execute(text(stmt))
            touched.append(f'{tbl}.{idx}')
            log.debug(stmt)
    if touched:
        log.info(f'{action.title()} {len(touched)} staging index(es): {", ".join(touched)}')
    return touched


def disable(engine: Engine, tables: Iterable[str], logger: Optional[logging.Logger] = None) -> List[str]:
    """Disable every enabled nonclustered index on the given staging tables."""
    return _alter(engine, tables, 'DISABLE', want_disabled=False, logger=logger)


def rebuild_disabled(engine: Engine, tables: Iterable[str], logger: Optional[logging.Logger] = None) -> List[str]:
    """Rebuild every currently-disabled nonclustered index on the given staging tables."""
    return _alter(engine, tables, 'REBUILD', want_disabled=True, logger=logger)
