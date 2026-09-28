from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
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
    """A member's pay rate starting on ``effective_from``.

    An interview is paid at the latest rate whose ``effective_from`` is on or
    before the interview date. A member's first rate also covers any earlier
    interviews, so work logged before the rate was set is never left unpriced.
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
        return f"{self.user} · {self.rate}/h from {self.effective_from}"


class Payout(models.Model):
    """A payment to one member for their unpaid interviews in one pay week.

    Amounts are copied onto the paid interviews, so later rate changes never
    alter what was already paid.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payouts")
    period_start = models.DateField()
    period_end = models.DateField()
    interview_count = models.PositiveIntegerField()
    total_minutes = models.PositiveIntegerField()
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="interviews")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(editable=False)
    interview_with = models.CharField(max_length=200)
    role = models.CharField(max_length=200)
    interview_type = models.ForeignKey(InterviewType, on_delete=models.PROTECT, related_name="interviews")
    notes = models.TextField(blank=True)
    payout = models.ForeignKey(
        Payout, null=True, blank=True, on_delete=models.SET_NULL, related_name="interviews"
    )
    paid_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-start_time"]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.date} {self.start_time:%H:%M}–{self.end_time:%H:%M} with {self.interview_with}"

    def save(self, *args, **kwargs):
        start_at, end_at = self.span()
        self.duration_minutes = int((end_at - start_at).total_seconds() // 60)
        super().save(*args, **kwargs)

    def span(self):
        return interview_span(self.date, self.start_time, self.end_time)

    @property
    def is_paid(self):
        return self.payout_id is not None

    @property
    def ends_next_day(self):
        return self.end_time <= self.start_time


def validate_time_slot(*, user_id, day, start, end, exclude_pk=None):
    """Check an interview's date and times; raises ValidationError keyed by field."""
    latest = timezone.localdate() + timedelta(days=1)  # one day of slack for time zones
    if day < EARLIEST_DATE:
        raise ValidationError({"date": "Enter a date after 2000."})
    if day > latest:
        raise ValidationError({"date": "You can't log an interview that hasn't happened yet."})
    if start == end:
        raise ValidationError({"end_time": "The end time must be different from the start time."})

    start_at, end_at = interview_span(day, start, end)
    if end_at - start_at > timedelta(minutes=MAX_INTERVIEW_MINUTES):
        raise ValidationError(
            {"end_time": "An interview can't be longer than 12 hours. Check the start and end times."}
        )

    nearby = Interview.objects.filter(user_id=user_id, date__range=(day - timedelta(days=1), day + timedelta(days=1)))
    if exclude_pk is not None:
        nearby = nearby.exclude(pk=exclude_pk)
    for other in nearby:
        other_start, other_end = other.span()
        if other_start < end_at and start_at < other_end:
            raise ValidationError(
                f"This overlaps another logged interview: {other.date:%b} {other.date.day}, "
                f"{other.start_time:%H:%M}–{other.end_time:%H:%M} with {other.interview_with}."
            )
