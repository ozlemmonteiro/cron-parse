# cron-parse

Pure-Python cron expression parser with deterministic next-run lookup. Standard library only, zero dependencies.

```python
from datetime import datetime
from cron_parse import CronExpression, find_next

# returns datetime(2024, 1, 1, 0, 5)
CronExpression("5 0 * * *").next_run(datetime(2024, 1, 1, 0, 0))

# returns datetime(2024, 1, 1, 9, 30)
find_next("30 9 * * *", datetime(2024, 1, 1, 8, 0))
```

Exports: `CronExpression` (class, constructor takes an expression string) with a `.next_run(after: datetime) -> datetime` method, and a `find_next(expression, after)` convenience wrapper. Both work on naive `datetime` objects only.

## Why this exists

Cron parsing is a small problem that keeps getting solved badly with heavy dependencies and timezone databases that the caller didn't ask for. This library does the one thing most callers actually need: given a five-field cron expression and a starting time, tell me the next firing time. Trade-off: no seconds field, no `@reboot`/`@yearly` macros, no timezone conversion. You pass naive datetimes; you get naive datetimes. That keeps the test suite deterministic and the dependency list empty.

## The awkward edge

When both day-of-month and day-of-week are restricted (neither is `*`), POSIX specifies **OR** semantics: a day qualifies if *either* field matches. Many implementations historically disagree. This library implements POSIX OR. If your expression is `0 0 1 * 0` and the 1st is a Saturday, the job fires the following Sunday — not skipped to the next month. If you need AND semantics (fire only when the 1st is a Sunday), this library is the wrong tool and that choice will be silent, so check now.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

## Limitations

Values are coerced to floats, so very large integers lose precision. If you need
exact integer aggregates over a window, this is the wrong tool.

