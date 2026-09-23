"""Tests for the parts of the archive that can be wrong without a database.

Everything here is a pure function over strings. That is deliberate: the two
things most worth testing in this change - what may become a table name, and
what may be dropped - are both decisions made before any SQL is issued, and both
have consequences that are hard to undo if they are wrong.

    python -m pytest tests/ -q
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from staging_archive import (  # noqa: E402
    MAX_IDENTIFIER,
    archive_table_name,
    quote_identifier,
    quote_literal,
    validate_customer_code,
    validate_table_name,
)


# ----------------------------------------------------------------------------
# Customer codes
# ----------------------------------------------------------------------------

@pytest.mark.parametrize('code', ['SM9641', 'SM9596', 'A', 'Ab123', 'X' * 30])
def test_valid_customer_codes_pass_through(code):
    assert validate_customer_code(code) == code


def test_customer_code_is_stripped_not_rewritten():
    assert validate_customer_code('  SM9641  ') == 'SM9641'


@pytest.mark.parametrize('code', [
    '',
    '   ',
    None,
    "SM'; DROP TABLE tblAccount--",   # the reason this is not a sanitiser
    "SM''9641",
    'SM 9641',                        # space
    'SM-9641',                        # hyphen
    'SM.9641',                        # would look like a schema qualifier
    'SM]9641',                        # bracket
    'SM_9641',                        # underscore separates code from table
    '9641SM',                         # must start with a letter
    'X' * 31,                         # one over
    'SM\n9641',                       # embedded newline
    'SM9641\nDROP TABLE tblAccount',  # what a trailing-newline match would let in
])
def test_bad_customer_codes_raise(code):
    with pytest.raises(ValueError):
        validate_customer_code(code)


def test_surrounding_whitespace_is_trimmed_not_rejected():
    """A newline picked up from a filename is noise, not a different code."""
    assert validate_customer_code('SM9641\n') == 'SM9641'
    assert validate_customer_code('\tSM9641 ') == 'SM9641'


def test_pattern_does_not_accept_a_trailing_newline():
    """Python's $ matches before a trailing newline; \\Z is why this holds.

    Asserted against the pattern rather than the function, because the function
    strips first and would hide a regression here.
    """
    from staging_archive import CUSTOMER_CODE_PATTERN, STAGING_TABLE_PATTERN
    assert CUSTOMER_CODE_PATTERN.match('SM9641') is not None
    assert CUSTOMER_CODE_PATTERN.match('SM9641\n') is None
    assert STAGING_TABLE_PATTERN.match('RC_SMS\n') is None


def test_customer_code_error_names_the_value():
    """The operator has to be able to find the badly named file."""
    with pytest.raises(ValueError, match='SM-9641'):
        validate_customer_code('SM-9641')


# ----------------------------------------------------------------------------
# Table names
# ----------------------------------------------------------------------------

@pytest.mark.parametrize('name', [
    'RC_ACCOUNT_EXTRACT', 'RC_SMS', 'RC_DRPAYALLOCMA_EXTRACT', '_x',
])
def test_valid_table_names_pass_through(name):
    assert validate_table_name(name) == name


@pytest.mark.parametrize('name', ['', None, 'RC SMS', 'RC-SMS', 'dbo.RC_SMS',
                                  'RC_SMS]', '1RC'])
def test_bad_table_names_raise(name):
    with pytest.raises(ValueError):
        validate_table_name(name)


# ----------------------------------------------------------------------------
# The archive name
# ----------------------------------------------------------------------------

def test_archive_name_is_code_underscore_table():
    assert archive_table_name('SM9641', 'RC_ACCOUNT_EXTRACT') == \
        'SM9641_RC_ACCOUNT_EXTRACT'


def test_archive_name_splits_back_apart_unambiguously():
    """No underscore in a customer code, so the first one is the separator."""
    name = archive_table_name('SM9641', 'RC_DRPAYALLOCMA_EXTRACT')
    code, _, table = name.partition('_')
    assert code == 'SM9641'
    assert table == 'RC_DRPAYALLOCMA_EXTRACT'


def test_archive_name_rejects_a_bad_code_before_building_anything():
    with pytest.raises(ValueError):
        archive_table_name("SM'; DROP", 'RC_SMS')


def test_archive_name_rejects_an_over_long_result():
    code = 'A' * 30
    table = 'R' + 'C' * 99
    assert len(code) + 1 + len(table) > MAX_IDENTIFIER
    with pytest.raises(ValueError, match=str(MAX_IDENTIFIER)):
        archive_table_name(code, table)


def test_every_real_staging_table_produces_a_legal_name():
    """The names actually in use, end to end."""
    import json
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'variables', 'table_keywords.json')) as handle:
        tables = [name for name in json.load(handle).values() if name]

    assert tables, 'table_keywords.json is empty'
    for table in tables:
        name = archive_table_name('SM9641', table)
        assert name.startswith('SM9641_')
        assert len(name) <= MAX_IDENTIFIER


# ----------------------------------------------------------------------------
# Quoting
# ----------------------------------------------------------------------------

def test_quote_identifier_doubles_closing_brackets():
    assert quote_identifier('we]ird') == '[we]]ird]'


def test_quote_literal_doubles_quotes():
    assert quote_literal("O'Brien") == "N'O''Brien'"


def test_quote_literal_is_what_sp_rename_needs():
    """sp_rename takes names as literals, so bracket-quoting is not the escape."""
    assert quote_literal('dbo.RC_SMS') == "N'dbo.RC_SMS'"
