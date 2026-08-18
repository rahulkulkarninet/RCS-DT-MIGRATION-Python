"""Shared lookup-key normalization for mapping raw staging values to DT labels.

Extracted from StatusService so the bank transaction method mapping can reuse the
same rules. StatusService keeps its public methods as delegates to these functions.

Two levels of aggressiveness:
  normalize_lookup_key  - readable form: upper-cased, mojibake/dash/NBSP repaired,
                          whitespace collapsed. Used for display and as the input
                          to match_key.
  match_key             - comparison form: everything except A-Z0-9 stripped, so
                          'Direct Debit' and 'DIRECT-DEBIT' collide on purpose.

The characters being repaired are written as literals below and in the bodies, so
keep this file UTF-8 encoded when editing it:
  â€“ / â€”  UTF-8 en/em dash misread as cp1252
  �                                  Unicode replacement character
  Â                                  stray latin capital A with circumflex
  – / —                         en dash / em dash
                                     non-breaking space
"""

import re

import pandas as pd


def normalize_text_series(series: pd.Series) -> pd.Series:
    """Repair a staged text column in place of storing it raw.

    Unlike normalize_lookup_series this preserves case and internal spacing, so
    it is safe on data values rather than lookup keys.

    NBSP (U+00A0) is the point of this: Debtrak extracts pad fields with it, and
    SQL Server does not treat it as whitespace. 'X' <> 'X' + NCHAR(160), and
    LTRIM/RTRIM will not remove it, so a padded value silently fails to match
    while looking identical on screen. Replacing it with a real space first is
    what makes the subsequent strip effective - .strip() alone leaves NBSP.
    """
    return series.str.replace('\xa0', ' ', regex=False).str.strip()


def match_key(value: str) -> str:
    return re.sub(r'[^A-Z0-9]+', '', str(value).upper())


def match_key_series(series: pd.Series) -> pd.Series:
    return series.fillna('').astype(str).str.upper().str.replace(r'[^A-Z0-9]+', '', regex=True)


def normalize_lookup_key(value: str) -> str:
    normalized = str(value).strip().upper()
    normalized = normalized.replace('â€“', '-')
    normalized = normalized.replace('â€”', '-')
    normalized = normalized.replace('�', '-')
    normalized = normalized.replace('Â', ' ')
    normalized = normalized.replace('–', '-')
    normalized = normalized.replace('—', '-')
    normalized = normalized.replace(' ', ' ')
    normalized = re.sub('�+', '-', normalized)
    normalized = ' '.join(normalized.split())
    return normalized


def normalize_lookup_series(series: pd.Series) -> pd.Series:
    normalized = series.fillna('').astype(str).str.strip().str.upper()
    normalized = normalized.str.replace('â€“', '-', regex=False)
    normalized = normalized.str.replace('â€”', '-', regex=False)
    normalized = normalized.str.replace('�', '-', regex=False)
    normalized = normalized.str.replace('Â', ' ', regex=False)
    normalized = normalized.str.replace('–', '-', regex=False)
    normalized = normalized.str.replace('—', '-', regex=False)
    normalized = normalized.str.replace(' ', ' ', regex=False)
    normalized = normalized.str.replace('�+', '-', regex=True)
    normalized = normalized.str.replace(r'\s+', ' ', regex=True).str.strip()
    return normalized
