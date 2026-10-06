"""Pure-Python cron expression parser with deterministic next-run lookup.

Scope deliberately kept small: five-field cron (min hour day-of-month month day-of-week),
  * / , - and names for DOW/MONTH. No @reboot, no seconds, no years.
  No timezone database; we operate on naive datetime objects.

Cron's week-day handling has a genuine ambiguity: when DOM and DOW are both restricted
  (neither is '*'), POSIX specifies OR semantics, cron implementations historically
  disagree. We implement POSIX OR: a day matches if EITHER field matches. The README
  states this so a reader who needs AND semantics knows to look elsewhere.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Iterable, Mapping

_MONTH_NAMES: Mapping[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DOW_NAMES: Mapping[str, int] = {
    # POSIX: 0 and 7 both mean Sunday. We normalise to the 0-6 range, Sunday=0.
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}

_LIMITS = {
    "minute": (0, 59),
    "hour": (0, 23),
    "dom": (1, 31),
    "month": (1, 12),
    "dow": (0, 6),
}


class _Field:
    """Sorted set of integer values that one cron field can match."""

    __slots__ = ("values", "wildcard")

    def __init__(self, values: frozenset[int], wildcard: bool) -> None:
        self.values = values
        self.wildcard = wildcard

    def matches(self, v: int) -> bool:
        if self.wildcard:
            return True
        return v in self.values


def _parse_names(tok: str, names: Mapping[str, int]) -> int:
    key = tok.lower()
    if key in names:
        return names[key]
    raise ValueError(f"Unknown name {tok!r}")


def _expand_step(low: int, high: int, step: int) -> Iterable[int]:
    if step <= 0:
        raise ValueError("step must be positive")
    # range() is half-open; we want inclusive high so we bump by 1.
    return range(low, high + 1, step)


def _parse_field(raw: str, field: str, names: Mapping[str, int] | None = None) -> _Field:
    text = raw.strip().lower()
    if not text:
        raise ValueError(f"empty {field} field")
    lo, hi = _LIMITS[field]
    if text == "*":
        return _Field(frozenset(), wildcard=True)

    out: set[int] = set()
    for part in text.split(","):
        if part == "":
            raise ValueError(f"empty list element in {field}")
        step = 1
        if "/" in part:
            base, _, step_s = part.partition("/")
            try:
                step = int(step_s)
            except ValueError as exc:
                raise ValueError(f"bad step {step_s!r} in {field}") from exc
        else:
            base = part

        if base == "*":
            b_lo, b_hi = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            try:
                if names is not None and not a.isdigit():
                    b_lo = _parse_names(a, names)
                else:
                    b_lo = int(a)
                if names is not None and not b.isdigit():
                    b_hi = _parse_names(b, names)
                else:
                    b_hi = int(b)
            except ValueError as exc:
                raise ValueError(f"bad range {base!r} in {field}") from exc
        else:
            try:
                if names is not None and not base.isdigit():
                    v = _parse_names(base, names)
                else:
                    v = int(base)
            except ValueError as exc:
                raise ValueError(f"bad value {base!r} in {field}") from exc
            if field == "dow" and v == 7:
                v = 0  # Sunday normalisation
            b_lo = b_hi = v

        if b_lo > b_hi:
            raise ValueError(f"inverted range {base!r} in {field}")
        if b_lo < lo or b_hi > hi:
            # Cron silently clamps some out-of-range values; we reject so callers see typos.
            raise ValueError(f"value out of range in {field}: {base!r}")

        for v in _expand_step(b_lo, b_hi, step):
            if field == "dow" and v == 7:
                v = 0
            out.add(v)

    return _Field(frozenset(out), wildcard=False)


class CronExpression:
    """A compiled five-field cron expression.

    Construct with an expression string; query with :meth:`next_run`.
    The clock is injected so tests are deterministic.
    """

    __slots__ = ("_minute", "_hour", "_dom", "_month", "_dow", "_raw")

    def __init__(self, expression: str) -> None:
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(
                f"expected 5 fields, got {len(parts)}: {expression!r}"
            )
        m, h, dom, mon, dow = parts
        self._raw = expression
        self._minute = _parse_field(m, "minute")
        self._hour = _parse_field(h, "hour")
        self._dom = _parse_field(dom, "dom")
        self._month = _parse_field(mon, "month", _MONTH_NAMES)
        self._dow = _parse_field(dow, "dow", _DOW_NAMES)

    @property
    def expression(self) -> str:
        return self._raw

    def _day_matches(self, dt: datetime) -> bool:
        dom_ok = self._dom.matches(dt.day)
        # Python weekday(): Monday=0..Sunday=6. Cron wants Sunday=0..Saturday=6.
        cron_dow = (dt.weekday() + 1) % 7
        dow_ok = self._dow.matches(cron_dow)
        if self._dom.wildcard or self._dow.wildcard:
            return dom_ok and dow_ok
        # POSIX OR semantics when both restricted. See module docstring.
        return dom_ok or dow_ok

    def next_run(self, after: datetime) -> datetime:
        """Return the next datetime >= after that satisfies the expression.

        `after` is treated as an exclusive lower bound at second-resolution: we start
        searching from the top of the minute containing `after` plus one minute, so
        the answer is strictly later than `after` at minute granularity. This matches
        the common cron behaviour where a job fired at 12:00 does not immediately
        re-fire at 12:00 on a next-run query.
        """
        if after.tzinfo is not None:
            raise ValueError("only naive datetimes are supported")

        # Start from the minute strictly after `after`. Discard seconds.
        cur = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        for _ in range(366 * 24 * 60 + 10):
            if not self._month.matches(cur.month):
                cur = self._advance_month(cur)
                continue
            if not self._day_matches(cur):
                cur = self._advance_day(cur)
                continue
            if not self._hour.matches(cur.hour):
                cur = self._advance_hour(cur)
                continue
            if not self._minute.matches(cur.minute):
                cur = self._advance_minute(cur)
                continue
            return cur
        raise RuntimeError("no match within search bound")

    def _advance_month(self, cur: datetime) -> datetime:
        year = cur.year + (cur.month // 12)
        month = (cur.month % 12) + 1
        return cur.replace(year=year, month=month, day=1, hour=0, minute=0)

    def _advance_day(self, cur: datetime) -> datetime:
        nxt = cur + timedelta(days=1)
        return nxt.replace(hour=0, minute=0)

    def _advance_hour(self, cur: datetime) -> datetime:
        nxt = cur + timedelta(hours=1)
        return nxt.replace(minute=0)

    def _advance_minute(self, cur: datetime) -> datetime:
        return cur + timedelta(minutes=1)


def find_next(expression: str, after: datetime) -> datetime:
    """Convenience: parse `expression` and return its next run after `after`."""
    return CronExpression(expression).next_run(after)
