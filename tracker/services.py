"""Pay calculations, summaries and payouts."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from itertools import groupby
from operator import attrgetter

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import HourlyRate, Interview, Payout
from .periods import WEEK, Period, format_range, week_start

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def amount_for(minutes, rate):
    return (Decimal(minutes) * rate / 60).quantize(CENT, rounding=ROUND_HALF_UP)


class RateBook:
    """Hourly rate history for a set of members, loaded in a single query."""

    def __init__(self, user_ids=None):
        rates = HourlyRate.objects.order_by("user_id", "effective_from")
        if user_ids is not None:
            rates = rates.filter(user_id__in=list(user_ids))
        self._dates = defaultdict(list)
        self._rates = defaultdict(list)
        for user_id, effective_from, rate in rates.values_list("user_id", "effective_from", "rate"):
            self._dates[user_id].append(effective_from)
            self._rates[user_id].append(rate)

    def rate_for(self, user_id, day):
        """The rate in effect on ``day``. A member's first rate also covers earlier days."""
        dates = self._dates.get(user_id)
        if not dates:
            return None
        index = max(bisect_right(dates, day) - 1, 0)
        return self._rates[user_id][index]

    def current_rate(self, user_id):
        return self.rate_for(user_id, timezone.localdate())


def price_interviews(interviews, rate_book=None):
    """Attach ``rate`` and ``amount`` to each interview and return them as a list.

    Paid interviews keep the rate and amount frozen when they were paid. Unpaid
    ones use the rate in effect on the interview date, or None if the member has
    no rate yet.
    """
    interviews = list(interviews)
    if rate_book is None:
        rate_book = RateBook({interview.user_id for interview in interviews})
    for interview in interviews:
        if interview.is_paid and interview.paid_amount is not None:
            interview.rate = interview.paid_rate
            interview.amount = interview.paid_amount
        else:
            interview.rate = rate_book.rate_for(interview.user_id, interview.date)
            interview.amount = None if interview.rate is None else amount_for(interview.duration_minutes, interview.rate)
    return interviews


@dataclass
class Totals:
    count: int = 0
    minutes: int = 0
    earned: Decimal = ZERO
    paid: Decimal = ZERO
    unpaid: Decimal = ZERO
    unpriced: int = 0  # unpaid interviews whose member has no rate yet

    @classmethod
    def of(cls, interviews):
        totals = cls()
        for interview in interviews:
            totals.add(interview)
        return totals

    def add(self, interview):
        self.count += 1
        self.minutes += interview.duration_minutes
        if interview.amount is None:
            self.unpriced += 1
            return
        self.earned += interview.amount
        if interview.is_paid:
            self.paid += interview.amount
        else:
            self.unpaid += interview.amount


@dataclass
class Group:
    label: str
    interviews: list = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)


def group_for_display(period, interviews):
    """Chronological groups: by day for a week, by pay week for a month."""
    groups = {}
    for interview in sorted(interviews, key=attrgetter("date", "start_time")):
        if period.kind == WEEK:
            key = interview.date
            label = f"{interview.date:%A, %b} {interview.date.day}"
        else:
            week = Period.week_of(interview.date)
            key = week.start
            label = format_range(max(week.start, period.start), min(week.end, period.end), with_year=False)
        group = groups.get(key)
        if group is None:
            group = groups[key] = Group(label)
        group.interviews.append(interview)
        group.totals.add(interview)
    return list(groups.values())


def totals_by_user(interviews):
    """``{user_id: Totals}`` for the given priced interviews."""
    result = defaultdict(Totals)
    for interview in interviews:
        result[interview.user_id].add(interview)
    return result


def totals_by_member(interviews):
    """``[(member, Totals)]`` sorted by name; interviews need ``user`` loaded."""
    members = {interview.user_id: interview.user for interview in interviews}
    totals = totals_by_user(interviews)
    return sorted(
        ((members[user_id], member_totals) for user_id, member_totals in totals.items()),
        key=lambda row: row[0].display_name.lower(),
    )


@dataclass
class WeekSummary:
    period: Period
    totals: Totals = field(default_factory=Totals)
    member_ids: set = field(default_factory=set)

    @property
    def member_count(self):
        return len(self.member_ids)


def summarize_weeks(interviews):
    """Per-pay-week totals, oldest week first."""
    weeks = {}
    for interview in interviews:
        start = week_start(interview.date)
        summary = weeks.get(start)
        if summary is None:
            summary = weeks[start] = WeekSummary(Period.week_of(interview.date))
        summary.totals.add(interview)
        summary.member_ids.add(interview.user_id)
    return [weeks[start] for start in sorted(weeks)]


def set_hourly_rate(member, rate, effective_from, set_by):
    HourlyRate.objects.update_or_create(
        user=member, effective_from=effective_from, defaults={"rate": rate, "set_by": set_by}
    )


class PayoutError(Exception):
    pass


CHANGED_SINCE_REVIEW = (
    "Those interviews changed since you opened this page (edited, deleted or already paid). "
    "Please review the week again."
)


@transaction.atomic
def record_payouts(*, period, interview_ids, expected_total, paid_by, note=""):
    """Mark exactly the reviewed interviews as paid, one payout per member.

    Fails if anything changed since the admin reviewed the amounts, so a payout
    always matches what was actually sent.
    """
    ids = set(interview_ids)
    interviews = list(
        Interview.objects.select_for_update()
        .filter(pk__in=ids, date__range=(period.start, period.end), payout__isnull=True)
        .order_by("user_id", "date", "start_time")
    )
    if not ids or len(interviews) != len(ids):
        raise PayoutError(CHANGED_SINCE_REVIEW)
    price_interviews(interviews)
    if any(interview.amount is None for interview in interviews):
        raise PayoutError("Set an hourly rate for everyone in this payment first.")
    if sum(interview.amount for interview in interviews) != expected_total:
        raise PayoutError(CHANGED_SINCE_REVIEW)

    payouts = []
    for user_id, group in groupby(interviews, key=attrgetter("user_id")):
        group = list(group)
        payout = Payout.objects.create(
            user_id=user_id,
            period_start=period.start,
            period_end=period.end,
            interview_count=len(group),
            total_minutes=sum(interview.duration_minutes for interview in group),
            amount=sum((interview.amount for interview in group), ZERO),
            note=note,
            paid_by=paid_by,
        )
        for interview in group:
            updated = Interview.objects.filter(pk=interview.pk, payout__isnull=True).update(
                payout=payout, paid_rate=interview.rate, paid_amount=interview.amount
            )
            if updated != 1:
                raise PayoutError(CHANGED_SINCE_REVIEW)
        payouts.append(payout)
    return payouts


@transaction.atomic
def undo_payout(payout):
    """Delete a payout and make its interviews unpaid again."""
    Interview.objects.filter(payout=payout).update(payout=None, paid_rate=None, paid_amount=None)
    payout.delete()


def mark_paid(interview, *, expected_amount, paid_by):
    """Record a payment for one interview (the amount the admin saw on screen)."""
    [payout] = record_payouts(
        period=Period.week_of(interview.date),
        interview_ids=[interview.pk],
        expected_total=expected_amount,
        paid_by=paid_by,
    )
    return payout


@transaction.atomic
def mark_unpaid(interview):
    """Take one interview out of its payment; the payment shrinks, or goes if it's empty."""
    if interview.payout_id is None:
        return
    payout = Payout.objects.select_for_update().get(pk=interview.payout_id)
    Interview.objects.filter(pk=interview.pk).update(payout=None, paid_rate=None, paid_amount=None)
    remaining = payout.interviews.aggregate(
        count=Count("id"), minutes=Sum("duration_minutes"), amount=Sum("paid_amount")
    )
    if not remaining["count"]:
        payout.delete()
        return
    payout.interview_count = remaining["count"]
    payout.total_minutes = remaining["minutes"]
    payout.amount = remaining["amount"]
    payout.save(update_fields=["interview_count", "total_minutes", "amount"])
