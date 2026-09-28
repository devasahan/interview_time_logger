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
