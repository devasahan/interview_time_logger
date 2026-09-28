"""Pay weeks and calendar months."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

WEEK = "week"
MONTH = "month"

# Sanity bounds for any date typed in by a person or read from a URL.
EARLIEST_DATE = date(2000, 1, 1)
LATEST_DATE = date(2100, 12, 31)


def week_start(day):
    return day - timedelta(days=(day.weekday() - settings.WEEK_START_DAY) % 7)


def parse_date(value):
    """Parse ``YYYY-MM-DD``; returns None for anything invalid or out of range."""
    try:
        day = date.fromisoformat(value or "")
    except (TypeError, ValueError):
        return None
    return day if EARLIEST_DATE <= day <= LATEST_DATE else None


def format_range(start, end, with_year=True):
    """'Sep 22 – 28, 2026', 'Sep 29 – Oct 5, 2026' or 'Dec 29, 2025 – Jan 4, 2026'."""
    year = f", {end.year}" if with_year else ""
    if start.year != end.year:
        return f"{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%b} {start.day} – {end:%b} {end.day}{year}"
    return f"{start:%b} {start.day} – {end.day}{year}"


@dataclass(frozen=True)
class Period:
    kind: str
    start: date
    end: date

    @classmethod
    def week_of(cls, day):
        start = week_start(day)
        return cls(WEEK, start, start + timedelta(days=6))

    @classmethod
    def month_of(cls, day):
        start = day.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return cls(MONTH, start, next_month - timedelta(days=1))

    @classmethod
    def of(cls, kind, day):
        return cls.month_of(day) if kind == MONTH else cls.week_of(day)

    @classmethod
    def from_query(cls, params):
        """The period selected by ``?period=week|month&date=YYYY-MM-DD`` (default: this week)."""
        kind = MONTH if params.get("period") == MONTH else WEEK
        return cls.of(kind, parse_date(params.get("date")) or timezone.localdate())

    @property
    def label(self):
        if self.kind == MONTH:
            return f"{self.start:%B %Y}"
        return format_range(self.start, self.end)

    @property
    def is_current(self):
        return self.contains(timezone.localdate())

    def contains(self, day):
        return self.start <= day <= self.end

    def previous(self):
        return Period.of(self.kind, self.start - timedelta(days=1))

    def next(self):
        return Period.of(self.kind, self.end + timedelta(days=1))
