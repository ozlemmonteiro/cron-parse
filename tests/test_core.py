import unittest
from datetime import datetime

from cron_parse import CronExpression, find_next


class ParseTests(unittest.TestCase):
    def test_basic(self):
        c = CronExpression("5 0 * * *")
        self.assertEqual(c.next_run(datetime(2024, 1, 1, 0, 0)), datetime(2024, 1, 1, 0, 5))

    def test_star(self):
        c = CronExpression("* * * * *")
        nxt = c.next_run(datetime(2024, 6, 15, 12, 30, 45))
        self.assertEqual(nxt, datetime(2024, 6, 15, 12, 31))

    def test_step(self):
        c = CronExpression("*/15 * * * *")
        nxt = c.next_run(datetime(2024, 6, 15, 12, 7))
        self.assertEqual(nxt, datetime(2024, 6, 15, 12, 15))

    def test_range(self):
        c = CronExpression("10-14 * * * *")
        nxt = c.next_run(datetime(2024, 6, 15, 12, 9))
        self.assertEqual(nxt, datetime(2024, 6, 15, 12, 10))

    def test_list(self):
        c = CronExpression("5,15,25 * * * *")
        nxt = c.next_run(datetime(2024, 6, 15, 12, 14))
        self.assertEqual(nxt, datetime(2024, 6, 15, 12, 15))

    def test_month_name(self):
        c = CronExpression("0 0 1 jan,jul *")
        nxt = c.next_run(datetime(2024, 2, 1))
        self.assertEqual(nxt, datetime(2024, 7, 1, 0, 0))

    def test_dow_names(self):
        c = CronExpression("0 0 * * mon,fri")
        nxt = c.next_run(datetime(2024, 6, 15))  # Saturday
        self.assertEqual(nxt, datetime(2024, 6, 17, 0, 0))

    def test_dow_sunday_zero_and_seven(self):
        a = CronExpression("0 0 * * 0").next_run(datetime(2024, 6, 15))  # Sat
        b = CronExpression("0 0 * * 7").next_run(datetime(2024, 6, 15))
        self.assertEqual(a, datetime(2024, 6, 16, 0, 0))
        self.assertEqual(a, b)

    def test_dom_and_dow_or_semantics(self):
        # 1st of month OR Sunday. 2024-06-01 is Saturday; next Sunday is 2024-06-02.
        c = CronExpression("0 0 1 * 0")
        nxt = c.next_run(datetime(2024, 6, 1, 0, 1))
        self.assertEqual(nxt, datetime(2024, 6, 2, 0, 0))

    def test_dom_and_dow_one_wildcard_is_and(self):
        # dom=1 (restricted), dow=* (wildcard) -> AND, so must be 1st.
        c = CronExpression("0 0 1 * *")
        nxt = c.next_run(datetime(2024, 6, 2))
        self.assertEqual(nxt, datetime(2024, 7, 1, 0, 0))

    def test_rejects_too_few_fields(self):
        with self.assertRaises(ValueError):
            CronExpression("5 0 * *")

    def test_rejects_bad_step(self):
        with self.assertRaises(ValueError):
            CronExpression("*/0 * * * *")

    def test_rejects_inverted_range(self):
        with self.assertRaises(ValueError):
            CronExpression("10-5 * * * *")

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            CronExpression("60 * * * *")

    def test_rejects_tz_aware(self):
        from datetime import timezone
        with self.assertRaises(ValueError):
            find_next("5 0 * * *", datetime(2024, 1, 1, tzinfo=timezone.utc))

    def test_exclusive_after(self):
        # exactly at the matching minute should NOT return same minute.
        c = CronExpression("5 0 * * *")
        nxt = c.next_run(datetime(2024, 1, 1, 0, 5))
        self.assertEqual(nxt, datetime(2024, 1, 2, 0, 5))

    def test_february_wrap(self):
        # non-leap year, day 29 of every month at 00:00.
        c = CronExpression("0 0 29 * *")
        nxt = c.next_run(datetime(2025, 2, 28))
        self.assertEqual(nxt, datetime(2025, 3, 29, 0, 0))

    def test_leap_february(self):
        c = CronExpression("0 0 29 2 *")
        nxt = c.next_run(datetime(2024, 2, 28))
        self.assertEqual(nxt, datetime(2024, 2, 29, 0, 0))

    def test_find_next_helper(self):
        nxt = find_next("30 9 * * *", datetime(2024, 6, 15, 8, 0))
        self.assertEqual(nxt, datetime(2024, 6, 15, 9, 30))


if __name__ == "__main__":
    unittest.main()
