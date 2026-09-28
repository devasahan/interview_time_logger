from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


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
