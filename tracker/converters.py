from datetime import date

from .periods import parse_date


class IsoDateConverter:
    """URL segment ``YYYY-MM-DD`` <-> ``datetime.date``."""

    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value):
        day = parse_date(value)
        if day is None:
            raise ValueError(value)  # Django treats this as "no match" -> 404
        return day

    def to_url(self, value):
        return value.isoformat() if isinstance(value, date) else str(value)
