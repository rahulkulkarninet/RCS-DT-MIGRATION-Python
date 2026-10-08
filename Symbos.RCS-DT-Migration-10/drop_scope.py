"""Which tables tools/setup_archive.py is allowed to drop. Default deny.

This is the most dangerous decision in the repo, so it is the smallest and the
only one: every candidate goes through is_droppable, nothing drops a table
without it, and it needs no database to test.

The migration's own database is also the DebtRak application database - over a
thousand tables that have nothing to do with this project. So the logic is
inverted from the obvious one. Not "list every table, subtract the ones we
expect, drop the rest", which is one bad config read away from dropping
tblAccount; instead, a declared scope of things the migration owns, and within
only that scope, drop what is not expected. A table outside the scope is never a
candidate under any flag, and callers are expected not to enumerate it at all.

The scope lives in variables/schema_sets.json under "drop_scope", so widening it
is a diff somebody reviews rather than a switch somebody passes.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Set, Tuple

# Refuse the whole run if more tables than this come out droppable and the scope
# did not say otherwise. A correct run clears a handful of strays; a list of two
# hundred means the expected set failed to load, and stopping beats proceeding
# carefully.
DEFAULT_MAX_DROPS = 40


def load_drop_scope(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """The declared scope, normalised. Missing or malformed means drop nothing.

    Deliberately not defaulted to anything permissive: a schema_sets.json
    without a drop_scope, or with a broken one, must make this tool inert rather
    than make it guess.
    """
    raw = manifest.get('drop_scope')
    if not isinstance(raw, dict):
        return {'dbo_prefixes': (), 'schemas': (), 'max_drops': DEFAULT_MAX_DROPS}

    def strings(key: str) -> Tuple[str, ...]:
        value = raw.get(key)
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(str(item) for item in value if str(item).strip())

    max_drops = raw.get('max_drops', DEFAULT_MAX_DROPS)
    if not isinstance(max_drops, int) or max_drops < 0:
        max_drops = DEFAULT_MAX_DROPS

    return {
        'dbo_prefixes': strings('dbo_prefixes'),
        'schemas': strings('schemas'),
        'max_drops': max_drops,
    }


def in_scope(schema: str, table: str, scope: Dict[str, Any]) -> bool:
    """True when this table is something the migration owns.

    Everything outside this is not "kept", it is not considered at all - the
    distinction matters, because it means a bug in the expected-set logic cannot
    reach an application table however wrong it goes.
    """
    schema_lower = str(schema).lower()
    table_lower = str(table).lower()

    if schema_lower in {s.lower() for s in scope.get('schemas', ())}:
        return True
    if schema_lower == 'dbo':
        return any(table_lower.startswith(prefix.lower())
                   for prefix in scope.get('dbo_prefixes', ()))
    return False


def is_droppable(
    schema: str,
    table: str,
    expected: Iterable[str],
    scope: Dict[str, Any],
    protected: Iterable[str],
    swept: Optional[Iterable[str]] = None,
    catalog_table: str = 'ArchiveCatalog',
) -> Tuple[bool, str]:
    """(may drop, why not). False unless every condition below holds.

    `expected`  tables the schema set says should exist.
    `protected` schema_sets.json protected_tables - never dropped, and there is
                deliberately no override parameter for it.
    `swept`     archive tables whose rows have already been copied out to
                ARCHIVE_DATABASE. An archive table not in here is the only copy
                of some customer's extract.
    """
    schema_lower = str(schema).lower()
    table_lower = str(table).lower()

    if not in_scope(schema, table, scope):
        return False, 'outside the declared drop scope'

    if table_lower in {str(name).lower() for name in protected}:
        return False, 'protected by schema_sets.json'

    if table_lower == str(catalog_table).lower():
        return False, 'the archive catalog itself'

    if table_lower in {str(name).lower() for name in expected}:
        return False, 'expected by the schema set'

    archive_schemas = {s.lower() for s in scope.get('schemas', ())}
    if schema_lower in archive_schemas:
        already = {str(name).lower() for name in (swept or ())}
        if table_lower not in already:
            return False, ('not yet swept to the archive database - this is the '
                           'only copy of that extract')
        return True, 'swept archive table'

    return True, 'in scope and not expected'


def plan_drops(
    candidates: Sequence[Tuple[str, str]],
    expected: Iterable[str],
    scope: Dict[str, Any],
    protected: Iterable[str],
    swept: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Sort (schema, table) pairs into what may be dropped and what may not.

    Returns 'blocked' when the drop list is larger than the scope allows, so the
    caller reports and refuses rather than working through it.
    """
    expected = list(expected)
    protected = list(protected)
    swept = list(swept or ())

    drop: list = []
    keep: list = []
    for schema, table in candidates:
        allowed, reason = is_droppable(schema, table, expected, scope,
                                       protected, swept)
        (drop if allowed else keep).append((schema, table, reason))

    max_drops = scope.get('max_drops', DEFAULT_MAX_DROPS)
    blocked = len(drop) > max_drops
    return {
        'drop': drop,
        'keep': keep,
        'blocked': blocked,
        'max_drops': max_drops,
        'reason': (
            f'{len(drop)} table(s) came out droppable, more than the {max_drops} '
            f'this scope allows. That usually means the expected set failed to '
            f'load rather than that there is a lot to clean up - nothing has '
            f'been dropped.' if blocked else ''),
    }
