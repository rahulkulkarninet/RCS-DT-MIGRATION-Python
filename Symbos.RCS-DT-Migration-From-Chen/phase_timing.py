"""Wall-clock timing for the coarse sections of one customer's load.

The per-table staging rows and the per-file SQL timings already exist; what
was missing is everything in between - validation, truncate, the mapping
steps, SQL preparation, metrics and the archive - so a run's total could not
be accounted for. One PhaseTimer lives on the processor per customer and is
reset in setup_customer_migration.

Wall clock is all this measures. On a contended instance (testse) compare
CPU time and logical reads from Query Store as well before trusting a change.
"""

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional


class PhaseTimer:
    """Records named sections in the order they finish."""

    def __init__(self) -> None:
        self.sections: List[Dict[str, Any]] = []
        self._lap_start: Optional[float] = None
        self._lap_wall: Optional[datetime] = None

    def _record(self, label: str, start_wall: datetime, seconds: float,
                ok: bool) -> None:
        self.sections.append({
            'label': label,
            'start_time': start_wall,
            'end_time': datetime.now(),
            'duration_seconds': round(seconds, 2),
            'success': ok,
        })

    @contextmanager
    def section(self, label: str) -> Iterator[None]:
        """Time a block. A block that raises is still recorded, as failed."""
        start_wall = datetime.now()
        start = time.perf_counter()
        ok = False
        try:
            yield
            ok = True
        finally:
            self._record(label, start_wall, time.perf_counter() - start, ok)

    def restart_lap(self) -> None:
        """Start a run of consecutive steps timed with lap()."""
        self._lap_start = time.perf_counter()
        self._lap_wall = datetime.now()

    def lap(self, label: str) -> None:
        """Record the time since the last lap (or restart_lap) as one section.

        For long straight-line code - the mapping steps - where wrapping every
        step in a with-block would re-indent hundreds of lines.
        """
        if self._lap_start is None:
            self.restart_lap()
            return
        now = time.perf_counter()
        self._record(label, self._lap_wall, now - self._lap_start, True)
        self._lap_start = now
        self._lap_wall = datetime.now()

    def summary_lines(self) -> List[str]:
        if not self.sections:
            return []
        width = max(len(s['label']) for s in self.sections)
        lines = ['PHASE TIMINGS (wall clock)']
        for s in self.sections:
            flag = '' if s['success'] else '  [FAILED]'
            lines.append(f"  {s['label']:<{width}}  {s['duration_seconds']:>9.1f}s{flag}")
        return lines

    def log_summary(self, logger: Any) -> None:
        for line in self.summary_lines():
            logger.info(line)

    def stats_rows(self, base: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rows shaped for RC_Processing_Stats, one per section.

        from_table='PHASE' keeps them apart from the staging and DT_Migration_
        rows; rows_inserted is 0 so they never change a row total. A label seen
        twice is suffixed, because UX_RC_Processing_Stats_Row is unique on
        Table_Name within a run and one duplicate would fail the whole insert.
        """
        rows = []
        seen: Dict[str, int] = {}
        for s in self.sections:
            name = f"PHASE_{s['label']}"[:120]
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name = f'{name}#{seen[name]}'
            row = dict(base)
            row.update({
                'from_table': 'PHASE',
                'table_name': name,
                'files_count': 0,
                'csv_rows': 0,
                'rows_inserted': 0,
                'start_time': s['start_time'],
                'end_time': s['end_time'],
                'duration_seconds': s['duration_seconds'],
                'rows_per_second': 0,
                'success': s['success'],
                'error_message': '',
            })
            rows.append(row)
        return rows


def get_timer(processor: Any) -> PhaseTimer:
    """The processor's timer, created on first use so old call paths still work."""
    timer = getattr(processor, 'phase_timer', None)
    if timer is None:
        timer = PhaseTimer()
        processor.phase_timer = timer
    return timer
