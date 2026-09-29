from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from tracker.icons import ICONS

register = template.Library()

AVATAR_TONES = 6


@register.filter
def money(value):
    """``1234.5`` -> ``$1,234.50``; None -> an em dash."""
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign = "-" if amount < 0 else ""
    return f"{sign}{settings.CURRENCY_SYMBOL}{abs(amount):,.2f}"


@register.filter
def money_short(value):
    """Compact amounts for chart axes: ``250`` -> ``$250``, ``1500`` -> ``$1.5K``."""
    amount = Decimal(value)
    symbol = settings.CURRENCY_SYMBOL
    if amount >= 1000:
        return f"{symbol}{amount / 1000:,.1f}".rstrip("0").rstrip(".") + "K"
    if amount == amount.to_integral_value():
        return f"{symbol}{amount:,.0f}"
    return f"{symbol}{amount:,.2f}"


@register.filter
def duration(minutes):
    """``90`` -> ``1h 30m``; ``0`` -> ``0h``."""
    if minutes is None or minutes == "":
        return "—"
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}h {mins:02d}m"
    if mins:
        return f"{mins}m"
    return f"{hours}h"


@register.filter
def hours(minutes):
    """``90`` -> ``1.50`` (decimal hours)."""
    if minutes is None or minutes == "":
        return "—"
    return f"{Decimal(int(minutes)) / 60:.2f}"


def _count(number, word):
    return f"{number:,} {word}" if number == 1 else f"{number:,} {word}s"


def _work_numbers(value):
    """(interviews, minutes, bids) from service ``Totals`` or a ``Payout``."""
    if hasattr(value, "total_minutes"):
        return value.interview_count, value.total_minutes, value.total_bids
    return value.interview_count, value.minutes, value.bids


@register.filter
def work(value):
    """What was logged: ``3 interviews · 4h 30m``, ``4h 30m`` (developer work),
    ``150 bids``, or a mix of them. Works on totals and payouts."""
    interviews, minutes, bids = _work_numbers(value)
    parts = []
    if interviews:
        parts.append(_count(interviews, "interview"))
    if minutes:
        parts.append(duration(minutes))
    if bids:
        parts.append(_count(bids, "bid"))
    return " · ".join(parts) or "Nothing logged"


@register.filter
def work_short(value):
    """Time and/or bids without the interview count, for narrow table cells."""
    _, minutes, bids = _work_numbers(value)
    parts = []
    if minutes:
        parts.append(duration(minutes))
    if bids:
        parts.append(_count(bids, "bid"))
    return " · ".join(parts) or "—"


@register.filter
def bid_count(number):
    """``150`` -> ``150 bids``; ``1`` -> ``1 bid``."""
    return _count(number or 0, "bid")


@dataclass(frozen=True)
class EntryKinds:
    """Which kinds of entries a table shows, so it can pick its columns."""

    interview: bool = False
    work: bool = False
    bids: bool = False

    @property
    def only_bids(self):
        return self.bids and not (self.interview or self.work)

    @property
    def logged_label(self):
        if self.only_bids:
            return "Bids"
        return "Logged" if self.bids else "Duration"

    @property
    def details_label(self):
        if self.only_bids:
            return "Notes"
        if self.interview and not (self.work or self.bids):
            return "Interview"
        if self.work and not (self.interview or self.bids):
            return "Work"
        return "Details"


@register.simple_tag
def column_count(kinds, *optional_columns):
    """Columns in an entries table: When, Logged, Details, Amount and Status, a Type
    column when it shows interviews, plus one per optional column that is on."""
    return 5 + int(kinds.interview) + sum(1 for shown in optional_columns if shown)


@register.simple_tag
def entry_kinds(groups, entries):
    """``EntryKinds`` for the groups a table shows, or else its flat list of entries.

    A tag rather than a filter so either argument may be missing from the context.
    """
    found = set()
    for item in groups or entries or ():
        for entry in getattr(item, "interviews", None) or [item]:
            found.add(entry.kind)
    return EntryKinds(interview="interview" in found, work="work" in found, bids="bids" in found)


@register.simple_tag
def icon(name, size=18, css_class=""):
    """Inline Lucide icon, e.g. ``{% icon "users" %}``."""
    return format_html(
        '<svg class="icon{}" width="{}" height="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        f" {css_class}" if css_class else "",
        size,
        size,
        mark_safe(ICONS[name]),  # trusted, bundled SVG markup
    )


@register.filter
def initials(user):
    """``Priya Sharma`` -> ``PS``; falls back to the username."""
    parts = [part for part in (user.first_name, user.last_name) if part]
    if parts:
        return "".join(part[0] for part in parts[:2]).upper()
    return (user.username[:2] or "?").upper()


@register.filter
def avatar_tone(user):
    """A stable colour slot for a member's avatar."""
    return (user.pk or 0) % AVATAR_TONES
