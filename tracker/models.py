from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .periods import EARLIEST_DATE, format_range

MAX_INTERVIEW_MINUTES = 12 * 60


def interview_span(day, start, end):
    """Start and end datetimes of an interview.

    An end time at or before the start time means the interview ran past
    midnight, so it ends on the next day.
    """
    start_at = datetime.combine(day, start)
    end_at = datetime.combine(day, end)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return start_at, end_at


class InterviewType(models.Model):
    name = models.CharField(max_length=60, unique=True)
    is_active = models.BooleanField(
        default=True, help_text="Inactive types are hidden when logging new interviews."
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class HourlyRate(models.Model):
    """A member's pay rate starting on ``effective_from``: per hour, or per bid
    for virtual assistants.

    Work is paid at the latest rate whose ``effective_from`` is on or before
    the work date. A member's first rate also covers any earlier work, so work
    logged before the rate was set is never left unpriced.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rates")
    rate = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    effective_from = models.DateField()
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user", "effective_from"]
        constraints = [
            models.UniqueConstraint(fields=["user", "effective_from"], name="unique_rate_per_user_per_day"),
        ]

    def __str__(self):
        return f"{self.user} · {self.rate}/{self.user.rate_unit} from {self.effective_from}"


class Payout(models.Model):
    """A payment to one member for their unpaid work in one pay week.

    Amounts are copied onto the paid entries, so later rate changes never
    alter what was already paid.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payouts")
    period_start = models.DateField()
    period_end = models.DateField()
    interview_count = models.PositiveIntegerField(help_text="Interviews in this payment (not developer work or bids).")
    total_minutes = models.PositiveIntegerField()
    total_bids = models.PositiveIntegerField(default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-paid_at", "-id"]

    def __str__(self):
        return f"{self.user} · {self.period_start} to {self.period_end} · {self.amount}"

    @property
    def period_label(self):
        return format_range(self.period_start, self.period_end)


class Interview(models.Model):
    """One entry of logged work. There are three kinds, one per team role:

    - an interview: a time range with an interview type, paid per hour;
    - developer work: a time range without a type (``interview_with`` holds
      the project and ``role`` the task), paid per hour;
    - a day's bids: a count in ``bids`` and no times, paid per bid
      (virtual assistants).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="interviews")
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0, editable=False)
    bids = models.PositiveIntegerField(
        null=True, blank=True, help_text="Bids sent that day. Only for bid entries; empty for interviews."
    )
    interview_with = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=200, blank=True)
    interview_type = models.ForeignKey(
        InterviewType, null=True, blank=True, on_delete=models.PROTECT, related_name="interviews"
    )
    notes = models.TextField(blank=True)
    payout = models.ForeignKey(
        Payout, null=True, blank=True, on_delete=models.SET_NULL, related_name="interviews"
    )
    paid_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "work entry"
        verbose_name_plural = "work entries"
        ordering = ["-date", "-start_time"]
        indexes = [models.Index(fields=["user", "date"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(bids__isnull=True, start_time__isnull=False, end_time__isnull=False)
                    | Q(bids__isnull=False, start_time__isnull=True, end_time__isnull=True, interview_type__isnull=True)
                ),
                name="entry_is_timed_or_bids",
                violation_error_message="An entry has either start and end times, or a number of bids.",
            ),
            models.UniqueConstraint(
                fields=["user", "date"],
                condition=Q(bids__isnull=False),
                name="one_bid_entry_per_member_per_day",
                violation_error_message="Bids for this day are already logged.",
            ),
        ]

    def __str__(self):
        if self.is_bid_log:
            return f"{self.date} · {self.bids} bids"
        return f"{self.date} {self.start_time:%H:%M}–{self.end_time:%H:%M} · {self.interview_with}"

    def save(self, *args, **kwargs):
        if self.start_time is None or self.end_time is None:
            self.duration_minutes = 0  # bids; an entry missing its times is refused by the database
        else:
            start_at, end_at = self.span()
            self.duration_minutes = int((end_at - start_at).total_seconds() // 60)
        super().save(*args, **kwargs)

    def span(self):
        return interview_span(self.date, self.start_time, self.end_time)

    @property
    def is_bid_log(self):
        return self.bids is not None

    @property
    def is_interview(self):
        return self.interview_type_id is not None

    @property
    def kind(self):
        """"interview", "work" (developer time) or "bids"."""
        if self.is_bid_log:
            return "bids"
        return "interview" if self.is_interview else "work"

    @property
    def rate_unit(self):
        return "bid" if self.is_bid_log else "h"

    @property
    def description(self):
        """``interview with Globex``, ``work on Acme website`` or ``40 bids``."""
        if self.is_bid_log:
            return f"{self.bids:,} bid{'' if self.bids == 1 else 's'}"
        if self.is_interview:
            return f"interview with {self.interview_with}"
        return f"work on {self.interview_with}"

    @property
    def sort_key(self):
        """Chronological order; a day's bids sort before that day's interviews."""
        return (self.date, self.start_time or time.min)

    @property
    def is_paid(self):
        return self.payout_id is not None

    @property
    def ends_next_day(self):
        return not self.is_bid_log and self.end_time <= self.start_time


def validate_work_date(day, what="an interview"):
    """Work dates must be real and not in the future; raises ValidationError keyed by field."""
    latest = timezone.localdate() + timedelta(days=1)  # one day of slack for time zones
    if day < EARLIEST_DATE:
        raise ValidationError({"date": "Enter a date after 2000."})
    if day > latest:
        raise ValidationError({"date": f"You can't log {what} for a day that hasn't happened yet."})


def validate_time_slot(*, user_id, day, start, end, exclude_pk=None, kind="interview"):
    """Check the date and times of an interview or developer work (``kind="work"``).

    Raises ValidationError keyed by field.
    """
    validate_work_date(day, "an interview" if kind == "interview" else "work")
    if start == end:
        raise ValidationError({"end_time": "The end time must be different from the start time."})

    start_at, end_at = interview_span(day, start, end)
    if end_at - start_at > timedelta(minutes=MAX_INTERVIEW_MINUTES):
        what = "An interview" if kind == "interview" else "One entry"
        raise ValidationError({"end_time": f"{what} can't be longer than 12 hours. Check the start and end times."})

    nearby = Interview.objects.filter(
        user_id=user_id, date__range=(day - timedelta(days=1), day + timedelta(days=1)), bids__isnull=True
    )
    if exclude_pk is not None:
        nearby = nearby.exclude(pk=exclude_pk)
    for other in nearby:
        other_start, other_end = other.span()
        if other_start < end_at and start_at < other_end:
            when = f"{other.date:%b} {other.date.day}, {other.start_time:%H:%M}–{other.end_time:%H:%M}"
            if kind == "interview":
                raise ValidationError(f"This overlaps another logged interview: {when} with {other.interview_with}.")
            raise ValidationError(f"This overlaps time you already logged: {when} ({other.interview_with}).")
