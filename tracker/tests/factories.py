from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model

from tracker.models import HourlyRate, Interview, InterviewType

PASSWORD = "a-strong-test-password-42"


def make_user(username="alex", *, approved=True, staff=False, **extra):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=PASSWORD,
        first_name=username.title(),
        is_approved=approved,
        is_staff=staff,
        **extra,
    )


def make_admin(username="boss"):
    return make_user(username, staff=True, is_superuser=True)


def set_rate(user, rate, effective_from=date(2026, 1, 1)):
    return HourlyRate.objects.create(user=user, rate=Decimal(str(rate)), effective_from=effective_from)


def interview_type(name="Technical"):
    return InterviewType.objects.get_or_create(name=name)[0]


def make_interview(user, day=date(2026, 9, 21), start=time(9, 0), end=time(10, 0), **extra):
    defaults = {
        "interview_with": "Acme Corp",
        "role": "Backend Engineer",
        "interview_type": interview_type(),
    }
    defaults.update(extra)
    return Interview.objects.create(user=user, date=day, start_time=start, end_time=end, **defaults)


def make_work(user, day=date(2026, 9, 21), start=time(9, 0), end=time(10, 0), **extra):
    """Developer work: a time range on a project, without an interview type."""
    defaults = {"interview_with": "Acme website", "role": "Build the sign-up page"}
    defaults.update(extra)
    return Interview.objects.create(user=user, date=day, start_time=start, end_time=end, **defaults)


def make_bids(user, day=date(2026, 9, 21), bids=40, **extra):
    """A virtual assistant's bids for one day."""
    return Interview.objects.create(user=user, date=day, bids=bids, **extra)
