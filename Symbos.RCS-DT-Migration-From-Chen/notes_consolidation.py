

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Source columns this module reads. clean_frame lowercases every column name, so these
# are the names as they arrive from the staging stream.
SRC_ACCOUNT = 'extended_debt_code'
SRC_DATE = 'date_entered'
SRC_OPERATOR = 'operator'
SRC_TEXT = 'text'
SRC_ZID = 'zid'

REQUIRED_COLUMNS = (SRC_ACCOUNT, SRC_DATE, SRC_OPERATOR, SRC_TEXT, SRC_ZID)

# Separators. CRLF rather than LF because the target is read in Windows clients, and
# because 66 used CHAR(13) + CHAR(10) - keeping them identical is what lets the parity
# test in the plan compare output byte for byte.
LINE_JOIN = ' '                      # wrapped multivalues of one source line
NOTE_JOIN = '\r\n'                   # source lines within one logical note
BLOCK_JOIN = '\r\n\r\n'              # between notes, i.e. a blank line
HEADER_FMT = '--- {date} | {operator} ---'
DATE_FMT = '%d/%m/%Y %H:%M'          # Australian; CONVERT(...,103) + CONVERT(...,108)

# Output columns, matching RC_STAGING_NOTES_ACCOUNT.
OUT_ACCOUNT = 'extended_debt_code'
OUT_ENTRY = 'entry'
OUT_LAST_DATE = 'lastnotedate'
OUT_NOTE_COUNT = 'notecount'
OUT_SOURCE_ROWS = 'sourcerows'


def _parse_zid(zid: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Split a PICK record id of the form ``<recid>`` or ``<recid>*<mv>``.

    The bare form matters: 1,027,024 rows (15.5%) carry no ``*n`` suffix, and 93% of
    them share a group with rows that do. They must parse to sub-value 0 so they sort
    first within their record, which is what 66's ``CHARINDEX('*', N.ZID + '*')`` guard
    achieves. Splitting on a missing separator in pandas yields NaN for the second
    part, so the fill to 0 is the same guard by another route.
    """
    text = zid.fillna('').astype(str)
    parts = text.str.split('*', n=1, expand=True)
    if parts.shape[1] == 1:
        # No row in this frame carried a suffix at all.
        parts[1] = None

    num = pd.to_numeric(parts[0], errors='coerce').fillna(0).astype('int64')
    sub = pd.to_numeric(parts[1], errors='coerce').fillna(0).astype('int32')
    return num, sub


def _fold_to_notes(frame: pd.DataFrame) -> pd.DataFrame:
    """Levels 1 and 2: display lines -> source lines -> logical notes.

    Returns one row per logical note with the source-row count carried through, so the
    caller can prove nothing was dropped.
    """
    work = pd.DataFrame({
        'account': frame[SRC_ACCOUNT],
        'date': frame[SRC_DATE],
        # NULL-normalised here rather than at comparison time. 66 breaks its islands
        # with EXISTS(... INTERSECT ...), which treats two NULLs as equal; a raw pandas
        # `!=` would treat them as different and split one note into two.
        'operator': frame[SRC_OPERATOR].fillna(''),
        'text': frame[SRC_TEXT].fillna(''),
    })
    work['zidnum'], work['zidsub'] = _parse_zid(frame[SRC_ZID])

    # mergesort is the only stable option pandas offers here, and stability is what
    # keeps rows that tie on the whole key in their arrival order.
    work.sort_values(['account', 'zidnum', 'zidsub'], inplace=True, kind='mergesort')

    # Level 1: collapse each record's overflow multivalues back into one source line.
    # Grouping on (account, zidnum) rather than (account, date, operator, zidnum) is
    # safe and cheaper: 66 records it verified across all 6.6M rows that one ZidNum
    # carries exactly one (Date_Entered, Operator). sort=False keeps the frame in the
    # order just established, which the island pass below depends on.
    grouped = work.groupby(['account', 'zidnum'], sort=False)
    lines = grouped.agg(
        date=('date', 'first'),
        operator=('operator', 'first'),
        linetext=('text', LINE_JOIN.join),
        srcrows=('text', 'size'),
    ).reset_index()

    # Level 2: a new note starts wherever the account, timestamp or operator changes
    # from the previous source line. Consecutive lines sharing all three are one note
    # that DebtRak wrapped across several records.
    account = lines['account']
    starts = (
        (account != account.shift())
        | (lines['date'] != lines['date'].shift())
        | (lines['operator'] != lines['operator'].shift())
    )
    lines['island'] = starts.cumsum()

    notes = lines.groupby('island', sort=False).agg(
        account=('account', 'first'),
        date=('date', 'first'),
        operator=('operator', 'first'),
        notetext=('linetext', NOTE_JOIN.join),
        srcrows=('srcrows', 'sum'),
    ).reset_index(drop=True)
    return notes


def consolidate_notes(frame: pd.DataFrame, newest_first: bool = True) -> pd.DataFrame:
    """Fold one frame of display lines into one consolidated note per account.

    Every row of ``frame`` for a given account must be present - an account split
    across two calls would be consolidated into two rows, which is exactly what the
    caller's buffering has to prevent.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            f'notes consolidation needs {missing} but the frame has '
            f'{sorted(frame.columns)}')

    if frame.empty:
        return pd.DataFrame(columns=[OUT_ACCOUNT, OUT_ENTRY, OUT_LAST_DATE,
                                     OUT_NOTE_COUNT, OUT_SOURCE_ROWS])

    notes = _fold_to_notes(frame)

    # Level 3: one block per note, newest first, blank line between them.
    dates = pd.to_datetime(notes['date'], errors='coerce')
    stamped = dates.dt.strftime(DATE_FMT).fillna('')
    operators = notes['operator'].astype(str).str.strip()
    notes['block'] = (
        '--- ' + stamped + ' | ' + operators + ' ---' + NOTE_JOIN + notes['notetext']
    )

    # Sorting by the parsed datetime rather than the raw column so that a text date
    # column cannot order lexically. Stable, so notes sharing a timestamp keep the
    # source order established in _fold_to_notes.
    notes['sortdate'] = dates
    notes.sort_values(['account', 'sortdate'], ascending=[True, not newest_first],
                      inplace=True, kind='mergesort')

    rolled = notes.groupby('account', sort=False).agg(
        **{
            OUT_ENTRY: ('block', BLOCK_JOIN.join),
            OUT_NOTE_COUNT: ('block', 'size'),
            OUT_SOURCE_ROWS: ('srcrows', 'sum'),
            OUT_LAST_DATE: ('sortdate', 'max'),
        }
    ).reset_index().rename(columns={'account': OUT_ACCOUNT})

    return rolled


class NotesConsolidator:
    """Folds the notes extract to one row per account as the load streams past it.

    Shaped like FinancialAccumulator deliberately: the staging load already hands every
    cleaned chunk to an observer, so consolidation costs one more pass over frames that
    are in memory anyway. Nothing is re-read and the whole table is never materialised,
    which is the property load_staging_file_group exists to preserve.

    This works because the extract arrives grouped by account. Measured over 2,999,700
    rows of a real extract in file-sequence order: Extended_Debt_Code is globally
    non-decreasing and 0 accounts are split across more than one run. So once a row for
    a later account appears, every earlier account is complete and can be folded and
    released - the buffer only ever holds the account currently being read.

    That property is asserted rather than trusted. If an account ever reappears after
    being emitted, the extract was not grouped the way every measured one is, and
    consolidating it would silently produce two entries for one account. That raises.
    """

    def __init__(self, newest_first: bool = True):
        self.newest_first = newest_first
        self._buffer: List[pd.DataFrame] = []
        self._buffered_account: Optional[object] = None
        self._done: List[pd.DataFrame] = []
        self._emitted: set = set()
        self.source_rows = 0

    def update(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
        if missing:
            raise ValueError(
                f'notes consolidation needs {missing} but the chunk has '
                f'{sorted(frame.columns)}')

        self.source_rows += len(frame)
        slim = frame.loc[:, list(REQUIRED_COLUMNS)]

        accounts = slim[SRC_ACCOUNT]
        tail = accounts.iloc[-1]

        # Rows for the chunk's final account may continue into the next chunk, so they
        # stay buffered. Everything before them is complete.
        complete = slim.loc[accounts != tail]
        carry = slim.loc[accounts == tail]

        if not complete.empty:
            self._flush(pd.concat(self._buffer + [complete], ignore_index=True)
                        if self._buffer else complete)
            self._buffer = []

        self._buffer.append(carry)
        self._buffered_account = tail

    def _flush(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        seen = set(frame[SRC_ACCOUNT].unique())
        repeated = seen & self._emitted
        if repeated:
            sample = sorted(repeated)[:5]
            raise ValueError(
                f'Notes extract is not grouped by account: {len(repeated)} account(s) '
                f'reappeared after their rows were already consolidated, for example '
                f'{sample}. Consolidating this extract would write more than one entry '
                f'per account. Nothing has been loaded.')
        self._emitted |= seen
        self._done.append(consolidate_notes(frame, newest_first=self.newest_first))

    def result(self) -> pd.DataFrame:
        """Fold whatever is still buffered and return every account's entry."""
        if self._buffer:
            self._flush(pd.concat(self._buffer, ignore_index=True))
            self._buffer = []
            self._buffered_account = None

        if not self._done:
            return pd.DataFrame(columns=[OUT_ACCOUNT, OUT_ENTRY, OUT_LAST_DATE,
                                         OUT_NOTE_COUNT, OUT_SOURCE_ROWS])

        rolled = pd.concat(self._done, ignore_index=True)
        self._done = [rolled]
        assert_lossless(self.source_rows, rolled)
        return rolled


def assert_lossless(source_rows: int, rolled: pd.DataFrame) -> None:
    """Fail before anything is loaded if a row went missing in the fold.

    The counting half of 66's guard, which exists for the same reason: a lossy
    consolidation must not reach tblEntry. The byte half is asserted after the load,
    where it also covers the bcp hop.
    """
    accounted = int(rolled[OUT_SOURCE_ROWS].sum()) if not rolled.empty else 0
    if accounted != source_rows:
        raise ValueError(
            f'Notes consolidation lost rows: {source_rows} source display line(s) '
            f'folded into {accounted}. Nothing has been loaded; investigate before '
            f're-running.')
