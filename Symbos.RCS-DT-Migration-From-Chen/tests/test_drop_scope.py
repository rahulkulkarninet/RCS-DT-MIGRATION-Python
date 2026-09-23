"""Tests for the drop decision.

The thing being protected here is the DebtRak application database - over a
thousand tables the migration does not own, in the same database it does own
tables in. Every test below is ultimately the same question: can anything make
is_droppable say yes to one of them?

    python -m pytest tests/ -q
"""

import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from drop_scope import (  # noqa: E402
    DEFAULT_MAX_DROPS,
    in_scope,
    is_droppable,
    load_drop_scope,
    plan_drops,
)

SCOPE = {'dbo_prefixes': ('RC_',), 'schemas': ('archive',), 'max_drops': 40}
EXPECTED = ['RC_ACCOUNT_EXTRACT', 'RC_SMS', 'RC_STAGING_COSTS']
PROTECTED = ['RC_Processing_Stats', 'RC_Entity_Mapping', 'RC_PaymentMethod_Mapping']
SWEPT = ['SM9596_RC_SMS']


def droppable(schema, table, **kwargs):
    kwargs.setdefault('expected', EXPECTED)
    kwargs.setdefault('scope', SCOPE)
    kwargs.setdefault('protected', PROTECTED)
    kwargs.setdefault('swept', SWEPT)
    return is_droppable(schema, table, **kwargs)[0]


# ----------------------------------------------------------------------------
# The application's tables. None of these may ever be droppable.
# ----------------------------------------------------------------------------

@pytest.mark.parametrize('table', [
    'tblAccount', 'tblentity', 'tblEntry', 'tblLoad', 'tblSMSOutput',
    'sysdiagrams', 'DT_Migration_SQLProgress', 'RoundhousE',
    'Recall_Accounts',      # begins with R but not RC_
    'rc_lowercase_trap',    # lowercase prefix still in scope - see below
])
def test_application_tables_are_never_droppable(table):
    if table == 'rc_lowercase_trap':
        # This one IS in scope: prefix matching is case-insensitive on purpose,
        # because SQL Server's default collation is. It is here so that fact is
        # asserted rather than discovered.
        assert droppable('dbo', table)
        return
    assert not droppable('dbo', table)


def test_an_empty_scope_drops_nothing():
    """A missing or broken drop_scope must make the tool inert, not universal."""
    empty = {'dbo_prefixes': (), 'schemas': (), 'max_drops': 40}
    for table in ('tblAccount', 'RC_OLD_THING', 'SM9596_RC_SMS'):
        assert not droppable('dbo', table, scope=empty)
        assert not droppable('archive', table, scope=empty)


def test_other_schemas_are_out_of_scope():
    assert not droppable('grate', 'RC_ANYTHING')
    assert not droppable('RoundhousE', 'RC_ANYTHING')


# ----------------------------------------------------------------------------
# Staging tables
# ----------------------------------------------------------------------------

def test_an_expected_staging_table_is_kept():
    assert not droppable('dbo', 'RC_ACCOUNT_EXTRACT')
    assert not droppable('dbo', 'RC_SMS')


def test_expected_matching_is_case_insensitive():
    assert not droppable('dbo', 'rc_account_extract')


def test_an_unexpected_rc_table_is_droppable():
    assert droppable('dbo', 'RC_OLD_THING')
    assert droppable('dbo', 'RC_STAGING_TREATMENTS')


@pytest.mark.parametrize('table', PROTECTED)
def test_protected_tables_are_never_droppable(table):
    assert not droppable('dbo', table)


def test_protected_beats_everything_and_has_no_override():
    """There is no force parameter; the only way past this is to edit the file."""
    import inspect
    from drop_scope import is_droppable as fn
    assert 'force' not in inspect.signature(fn).parameters


# ----------------------------------------------------------------------------
# Archive tables - the only copy until they are swept
# ----------------------------------------------------------------------------

def test_an_unswept_archive_table_is_never_droppable():
    allowed, reason = is_droppable('archive', 'SM9641_RC_NOTES_EXTRACT',
                                   EXPECTED, SCOPE, PROTECTED, SWEPT)
    assert not allowed
    assert 'only copy' in reason


def test_a_swept_archive_table_is_droppable():
    assert droppable('archive', 'SM9596_RC_SMS')


def test_no_swept_list_means_no_archive_table_is_droppable():
    assert not droppable('archive', 'SM9596_RC_SMS', swept=None)
    assert not droppable('archive', 'SM9596_RC_SMS', swept=[])


def test_the_catalog_itself_is_never_droppable():
    assert not droppable('archive', 'ArchiveCatalog')
    assert not droppable('archive', 'ArchiveCatalog', swept=['ArchiveCatalog'])


# ----------------------------------------------------------------------------
# Blast radius
# ----------------------------------------------------------------------------

def test_a_normal_plan_is_not_blocked():
    candidates = [('dbo', 'RC_ACCOUNT_EXTRACT'), ('dbo', 'RC_OLD_ONE'),
                  ('dbo', 'RC_OLD_TWO'), ('dbo', 'tblAccount')]
    plan = plan_drops(candidates, EXPECTED, SCOPE, PROTECTED, SWEPT)
    assert not plan['blocked']
    assert {t for _, t, _ in plan['drop']} == {'RC_OLD_ONE', 'RC_OLD_TWO'}
    assert {t for _, t, _ in plan['keep']} == {'RC_ACCOUNT_EXTRACT', 'tblAccount'}


def test_too_many_drops_blocks_the_whole_run():
    candidates = [('dbo', f'RC_STRAY_{n}') for n in range(50)]
    plan = plan_drops(candidates, EXPECTED, SCOPE, PROTECTED, SWEPT)
    assert plan['blocked']
    assert '50' in plan['reason']


def test_an_empty_expected_set_does_not_make_everything_droppable_silently():
    """Losing the expected set is exactly when the circuit breaker must fire."""
    candidates = [('dbo', f'RC_TABLE_{n}') for n in range(45)]
    plan = plan_drops(candidates, [], SCOPE, PROTECTED, SWEPT)
    assert plan['blocked']


# ----------------------------------------------------------------------------
# Loading the scope from the real manifest
# ----------------------------------------------------------------------------

def test_the_repo_manifest_declares_a_scope():
    with open(os.path.join(REPO_ROOT, 'variables', 'schema_sets.json'),
              encoding='utf-8') as handle:
        manifest = json.load(handle)
    scope = load_drop_scope(manifest)
    assert scope['dbo_prefixes'] == ('RC_',)
    assert scope['schemas'] == ('archive',)
    assert scope['max_drops'] > 0


def test_a_manifest_without_a_scope_yields_an_inert_one():
    scope = load_drop_scope({})
    assert scope['dbo_prefixes'] == ()
    assert scope['schemas'] == ()
    assert scope['max_drops'] == DEFAULT_MAX_DROPS
    assert not in_scope('dbo', 'RC_ANYTHING', scope)


@pytest.mark.parametrize('broken', [
    {'drop_scope': 'RC_'},
    {'drop_scope': {'dbo_prefixes': 'RC_'}},      # string, not a list
    {'drop_scope': {'dbo_prefixes': None}},
    {'drop_scope': {'max_drops': -1}},
])
def test_a_malformed_scope_is_inert_rather_than_permissive(broken):
    scope = load_drop_scope(broken)
    assert not in_scope('dbo', 'RC_ANYTHING', scope)
    assert not in_scope('dbo', 'tblAccount', scope)
    assert scope['max_drops'] >= 0


def test_the_real_expected_set_keeps_every_real_staging_table():
    """The tables actually configured today must all be kept, not dropped."""
    with open(os.path.join(REPO_ROOT, 'variables', 'table_keywords.json'),
              encoding='utf-8') as handle:
        expected = [name for name in json.load(handle).values() if name]

    assert expected
    for table in expected:
        allowed, reason = is_droppable('dbo', table, expected, SCOPE, PROTECTED,
                                       SWEPT)
        assert not allowed, f'{table} would be dropped: {reason}'
