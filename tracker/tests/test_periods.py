from datetime import date
from unittest import mock

from django.test import SimpleTestCase, override_settings

from tracker.periods import MONTH, WEEK, Period, format_range, parse_date, week_start


class WeekStartTests(SimpleTestCase):
    def test_weeks_start_on_monday_by_default(self):
        self.assertEqual(week_start(date(2026, 9, 27)), date(2026, 9, 21))  # Sunday -> Monday
        self.assertEqual(week_start(date(2026, 9, 21)), date(2026, 9, 21))

    @override_settings(WEEK_START_DAY=6)
    def test_weeks_can_start_on_sunday(self):
        self.assertEqual(week_start(date(2026, 9, 26)), date(2026, 9, 20))  # Saturday -> Sunday
        self.assertEqual(week_start(date(2026, 9, 27)), date(2026, 9, 27))


class PeriodTests(SimpleTestCase):
    def test_week_period(self):
        period = Period.week_of(date(2026, 9, 24))
        self.assertEqual((period.kind, period.start, period.end), (WEEK, date(2026, 9, 21), date(2026, 9, 27)))
        self.assertEqual(period.label, "Sep 21 – 27, 2026")
        self.assertEqual(period.previous().start, date(2026, 9, 14))
        self.assertEqual(period.next().start, date(2026, 9, 28))

    def test_month_period(self):
        period = Period.month_of(date(2028, 2, 10))
        self.assertEqual((period.kind, period.start, period.end), (MONTH, date(2028, 2, 1), date(2028, 2, 29)))
        self.assertEqual(period.label, "February 2028")
        self.assertEqual(Period.month_of(date(2026, 12, 31)).next().start, date(2027, 1, 1))
        self.assertEqual(Period.month_of(date(2026, 1, 5)).previous().start, date(2025, 12, 1))

    def test_from_query(self):
        with mock.patch("tracker.periods.timezone.localdate", return_value=date(2026, 9, 24)):
            self.assertEqual(Period.from_query({}), Period.week_of(date(2026, 9, 24)))
            self.assertEqual(Period.from_query({"date": "not-a-date"}), Period.week_of(date(2026, 9, 24)))
            self.assertEqual(Period.from_query({"date": "0001-01-01"}), Period.week_of(date(2026, 9, 24)))
        self.assertEqual(
            Period.from_query({"period": "month", "date": "2026-03-15"}), Period.month_of(date(2026, 3, 1))
        )

    def test_format_range(self):
        self.assertEqual(format_range(date(2026, 9, 29), date(2026, 10, 5)), "Sep 29 – Oct 5, 2026")
        self.assertEqual(format_range(date(2025, 12, 29), date(2026, 1, 4)), "Dec 29, 2025 – Jan 4, 2026")
        self.assertEqual(format_range(date(2026, 9, 1), date(2026, 9, 6), with_year=False), "Sep 1 – 6")

    def test_parse_date_rejects_out_of_range(self):
        self.assertEqual(parse_date("2026-09-24"), date(2026, 9, 24))
        self.assertIsNone(parse_date("1999-12-31"))
        self.assertIsNone(parse_date(None))
