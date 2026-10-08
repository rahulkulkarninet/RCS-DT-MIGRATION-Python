"""Column-at-a-time rendering of staging chunks into bcp character format.

The bcp sink used to call one Python formatter per cell. On a 6.6M-row notes
extract that loop was most of staging: Python, single threaded, and holding
the GIL so the parallel table loads could not overlap it either. This renders
a whole column at once.

The per-cell formatters in DatabaseHelper._build_bcp_formatters remain the
definition of the output. Every fast path here must produce byte-identical
text, and any column whose shape a fast path cannot prove it handles exactly
(mixed object columns, tz-aware datetimes, years outside 1000-9999, signed
zeros, ...) is rendered by those same per-cell formatters instead. Tests
compare the two renderings byte for byte - tests/test_bcp_format.py.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

FIELD_TERMINATOR = '\x1f'
ROW_TERMINATOR = '\x1e'


@dataclass
class ColumnSpec:
    """How one target column is rendered.

    kind is 'generic', 'date', 'datetime' or 'decimal'. cell is the per-cell
    formatter, which is the reference and the fallback.
    """
    kind: str
    cell: Callable[[Any], str]
    digits: int = 0
    time_only: bool = False
    quantum: Optional[Decimal] = None
    scale: Optional[int] = None


def format_decimal(value: Any, quantum: Decimal, scale: int) -> Optional[Tuple[str, bool]]:
    """Render a float/Decimal for a scaled column: (text, was_rescaled).

    None means "not this formatter's business" and the generic formatter
    answers instead - kept identical to the per-cell closure, which calls this.
    """
    if not isinstance(value, (float, np.floating, Decimal)):
        return None
    try:
        if pd.isna(value):
            return '', False
    except (TypeError, ValueError):
        pass
    try:
        exact = value if isinstance(value, Decimal) else Decimal(str(value))
        rescaled = -exact.as_tuple().exponent > scale
        return format(exact.quantize(quantum, rounding=ROUND_HALF_UP), 'f'), rescaled
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------------------
# Fast paths. Each returns an object ndarray of str, or None to fall back.
# ---------------------------------------------------------------------------

def _cellwise(values: pd.Series, cell: Callable[[Any], str]) -> np.ndarray:
    return np.array([cell(v) for v in values.tolist()], dtype=object) \
        if len(values) else np.array([], dtype=object)


def _ints(values: pd.Series) -> Optional[np.ndarray]:
    """int64 / nullable Int* columns: str(int(v)), NULL as ''."""
    dtype = values.dtype
    if isinstance(dtype, pd.api.extensions.ExtensionDtype):
        if not pd.api.types.is_integer_dtype(dtype):
            return None
        mask = values.isna().to_numpy()
        raw = values.to_numpy(dtype='int64', na_value=0)
    elif np.issubdtype(dtype, np.integer):
        mask = None
        raw = values.to_numpy()
    else:
        return None
    out = raw.astype(str).astype(object)
    if mask is not None and mask.any():
        out[mask] = ''
    return out


def _as_iterated(values: pd.Series, position: int) -> Any:
    """The element exactly as DataFrame.itertuples would hand it over. That is
    not always the Python type: a nullable boolean column yields numpy bools,
    which the per-cell formatter renders 'True'/'False', not '1'/'0'."""
    return next(iter(values.iloc[position:position + 1]))


def _bools(values: pd.Series, cell: Callable[[Any], str]) -> Optional[np.ndarray]:
    """Bool columns have two possible texts; render one of each per cell."""
    dtype = values.dtype
    if not (pd.api.types.is_bool_dtype(dtype)):
        return None
    mask = values.isna().to_numpy()
    raw = values.to_numpy(dtype=bool, na_value=False)
    texts = {}
    for flag in (True, False):
        hits = np.flatnonzero((raw == flag) & ~mask)
        texts[flag] = cell(_as_iterated(values, int(hits[0]))) if len(hits) else ''
    out = np.where(raw, texts[True], texts[False]).astype(object)
    if mask.any():
        out[mask] = ''
    return out


def _strings(values: pd.Series) -> Optional[np.ndarray]:
    """Object columns holding only str (and nulls): the text as is."""
    if values.dtype != object:
        return None
    inferred = pd.api.types.infer_dtype(values, skipna=True)
    if inferred == 'empty':
        return np.full(len(values), '', dtype=object)
    if inferred != 'string':
        return None
    out = values.to_numpy(dtype=object, copy=True)
    mask = pd.isna(out)
    if mask.any():
        out[mask] = ''
    return out


def _memoised(values: pd.Series, render: Callable[[Any], Tuple[str, int]]
              ) -> Optional[Tuple[np.ndarray, int]]:
    """Render each distinct float once. Hash-equal floats render the same,
    except signed zeros (0.0 == -0.0), so a column holding -0.0 falls back."""
    if values.dtype.kind != 'f':
        return None
    raw = values.to_numpy()
    zeros = raw == 0
    if zeros.any() and np.signbit(raw[zeros]).any():
        return None
    nulls = np.isnan(raw)
    out = np.full(len(raw), '', dtype=object)
    present = raw[~nulls]
    if not len(present):
        return out, 0
    uniques, inverse, counts = np.unique(present, return_inverse=True, return_counts=True)
    rendered = []
    extra = 0
    for u, n in zip(uniques.tolist(), counts.tolist()):
        text, flag = render(u)
        rendered.append(text)
        extra += flag * n
    out[~nulls] = np.array(rendered, dtype=object)[inverse.reshape(-1)]
    return out, extra


def _datetime_parts(values: pd.Series):
    """(seconds-resolution datetime64 array, microsecond ints, null mask), or
    None when the column is not a naive datetime64 inside years 1000-9999."""
    dtype = values.dtype
    if not (np.issubdtype(dtype, np.datetime64) if isinstance(dtype, np.dtype) else False):
        return None   # tz-aware and object columns fall back
    raw = values.to_numpy()
    nulls = np.isnat(raw)
    present = raw[~nulls]
    if len(present):
        years = present.astype('datetime64[Y]').astype(int) + 1970
        if years.min() < 1000 or years.max() > 9999:
            return None
    as_us = raw.astype('datetime64[us]')
    seconds = as_us.astype('datetime64[s]')
    micro = (as_us - seconds).astype('int64')
    return seconds, micro, nulls


def _fixed_text(seconds: np.ndarray, time_only: bool, date_only: bool = False) -> np.ndarray:
    """'%Y%m%d %H:%M:%S', '%H:%M:%S' or '%Y-%m-%d' for datetime64[s] values,
    by slicing the ISO text as a code-point matrix - no Python per value."""
    iso = np.datetime_as_string(seconds, unit='s').astype('<U19')   # YYYY-MM-DDTHH:MM:SS
    cp = iso.view(np.uint32).reshape(-1, 19)
    if date_only:
        picked = cp[:, 0:10]
    elif time_only:
        picked = cp[:, 11:19]
    else:
        space = np.full((len(cp), 1), ord(' '), dtype=np.uint32)
        picked = np.concatenate([cp[:, 0:4], cp[:, 5:7], cp[:, 8:10], space, cp[:, 11:19]], axis=1)
    width = picked.shape[1]
    return np.ascontiguousarray(picked).view(f'<U{width}').reshape(-1)


def _digits_text(numbers: np.ndarray, digits: int) -> np.ndarray:
    """Zero-padded decimal text of non-negative ints, fixed width."""
    cols = [(numbers // 10 ** (digits - 1 - k)) % 10 + ord('0') for k in range(digits)]
    cp = np.stack(cols, axis=1).astype(np.uint32)
    return np.ascontiguousarray(cp).view(f'<U{digits}').reshape(-1)


def _datetimes(values: pd.Series, digits: int, time_only: bool) -> Optional[np.ndarray]:
    """Mirror of DatabaseHelper._format_bcp_datetime for naive datetime64."""
    parts = _datetime_parts(values)
    if parts is None:
        return None
    seconds, micro, nulls = parts
    one = np.timedelta64(1, 's')
    if digits <= 0:
        seconds = np.where(micro >= 500000, seconds + one, seconds)
        fraction = np.zeros(len(micro), dtype=np.int64)
        width = 0
    elif digits < 6:
        unit = 10 ** (6 - digits)
        fraction = (micro + unit // 2) // unit
        carry = fraction * unit >= 1000000
        seconds = np.where(carry, seconds + one, seconds)
        fraction = np.where(carry, 0, fraction)
        width = digits
    else:
        fraction = micro
        width = 6
    if (~nulls).any():
        years = seconds[~nulls].astype('datetime64[Y]').astype(int) + 1970
        if years.max() > 9999:
            return None   # carried past 9999-12-31 23:59:59
    base = _fixed_text(seconds.astype('datetime64[s]'), time_only)
    out = base.astype(object)
    has_fraction = (fraction != 0) & ~nulls
    if width and has_fraction.any():
        suffix = _digits_text(fraction[has_fraction], width)
        out[has_fraction] = np.char.add(np.char.add(base[has_fraction], '.'), suffix).astype(object)
    if nulls.any():
        out[nulls] = ''
    return out


def _dates(values: pd.Series) -> Optional[np.ndarray]:
    """DATE column from datetime64 values: '%Y-%m-%d'."""
    parts = _datetime_parts(values)
    if parts is None:
        return None
    seconds, _micro, nulls = parts
    out = _fixed_text(seconds, time_only=False, date_only=True).astype(object)
    if nulls.any():
        out[nulls] = ''
    return out


def render_column(values: pd.Series, spec: ColumnSpec, stats: Dict[str, int]
                  ) -> Tuple[np.ndarray, bool]:
    """(rendered strings, may_contain_text). The flag is False only where the
    output is digits/punctuation the renderer produced itself, so the
    terminator sanitiser can skip it."""
    if spec.kind == 'generic':
        for fast in (_strings,):
            out = fast(values)
            if out is not None:
                return out, True
        out = _ints(values)
        if out is not None:
            return out, False
        out = _bools(values, spec.cell)
        if out is not None:
            return out, False
        memo = _memoised(values, lambda v: (spec.cell(v), 0))
        if memo is not None:
            return memo[0], False
    elif spec.kind == 'date':
        out = _dates(values)
        if out is not None:
            return out, False
        out = _strings(values)
        if out is not None:
            return out, True
    elif spec.kind == 'datetime':
        out = _datetimes(values, spec.digits, spec.time_only)
        if out is not None:
            return out, False
        out = _strings(values)
        if out is not None:
            return out, True
    elif spec.kind == 'decimal':
        out = _ints(values)
        if out is not None:
            return out, False

        def render(v):
            result = format_decimal(v, spec.quantum, spec.scale)
            if result is None:
                return spec.cell(v), 0
            return result[0], int(result[1])
        memo = _memoised(values, render)
        if memo is not None:
            out, rescaled = memo
            if rescaled:
                stats['rescaled'] = stats.get('rescaled', 0) + rescaled
            return out, False
        out = _strings(values)
        if out is not None:
            return out, True
    # Anything else: the per-cell reference, which also does its own
    # rescaled counting through the stats dict its closure holds.
    return _cellwise(values, spec.cell), True


def _sanitise(column: np.ndarray) -> Tuple[np.ndarray, int]:
    """Blank out terminator characters, counting the cells changed."""
    if not len(column):
        return column, 0
    joined = ''.join(column.tolist())
    if FIELD_TERMINATOR not in joined and ROW_TERMINATOR not in joined:
        return column, 0
    hit = 0
    out = column.copy()
    for i, value in enumerate(out.tolist()):
        if FIELD_TERMINATOR in value or ROW_TERMINATOR in value:
            out[i] = value.replace(FIELD_TERMINATOR, ' ').replace(ROW_TERMINATOR, ' ')
            hit += 1
    return out, hit


def render_chunk(chunk: pd.DataFrame, specs: List[ColumnSpec],
                 stats: Dict[str, int]) -> Tuple[str, int]:
    """One chunk as bcp text (rows joined, trailing row terminator included),
    plus the number of cells whose terminators were blanked."""
    if chunk is None or chunk.empty:
        return '', 0
    columns = []
    sanitised = 0
    for position, spec in enumerate(specs):
        out, textual = render_column(chunk.iloc[:, position], spec, stats)
        if textual:
            out, hit = _sanitise(out)
            sanitised += hit
        columns.append(out.tolist())
    lines = [FIELD_TERMINATOR.join(row) for row in zip(*columns)]
    return ROW_TERMINATOR.join(lines) + ROW_TERMINATOR, sanitised


def render_chunk_cellwise(chunk: pd.DataFrame, formatters: List[Callable[[Any], str]]
                          ) -> Tuple[str, int]:
    """The original one-call-per-cell renderer, kept as the reference."""
    if chunk is None or chunk.empty:
        return '', 0
    sanitised = 0
    lines = []
    for record in chunk.itertuples(index=False, name=None):
        fields = []
        for fmt, value in zip(formatters, record):
            rendered = fmt(value)
            if FIELD_TERMINATOR in rendered or ROW_TERMINATOR in rendered:
                rendered = rendered.replace(FIELD_TERMINATOR, ' ').replace(ROW_TERMINATOR, ' ')
                sanitised += 1
            fields.append(rendered)
        lines.append(FIELD_TERMINATOR.join(fields))
    return ROW_TERMINATOR.join(lines) + ROW_TERMINATOR, sanitised
