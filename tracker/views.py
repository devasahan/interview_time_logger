"""Pages for team members: the home page (summary, interviews, payments) and logging interviews."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import InterviewForm
from .models import Interview
from .periods import WEEK, Period, parse_date
from .services import (
    ZERO,
    RateBook,
    Totals,
    chart_weeks,
    group_for_display,
    price_interviews,
    summarize_weeks,
    weekly_chart,
)
from .templatetags.tracker_tags import duration


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


def home_url(day=None, kind=WEEK):
    """The home page, scrolled to the interviews of the week (or month) around ``day``."""
    query = f"?{urlencode({'period': kind, 'date': day.isoformat()})}" if day else ""
    return f"{reverse('tracker:home')}{query}#interviews"


def safe_next(request, fallback):
    """The ``next`` URL from the request if it points back to this site."""
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


def period_context(period):
    """Template context for pages that switch between weeks and months."""
    today = timezone.localdate()
    return {
        "period": period,
        # Date used when switching between week and month tabs.
        "anchor": today if period.contains(today) else period.start,
    }


@login_required
def home(request):
    """Everything a member needs on one page: totals, earnings, interviews and payments."""
    if request.user.is_staff:
        return redirect("tracker:manage_overview")

    user = request.user
    today = timezone.localdate()
    week, month = Period.week_of(today), Period.month_of(today)
    period = Period.from_query(request.GET)
    rate_book = RateBook([user.pk])

    weeks = chart_weeks(today)
    summary_range = (min(week.start, month.start, weeks[0].start), max(week.end, month.end))
    in_range = price_interviews(user.interviews.filter(date__range=summary_range), rate_book)
    unpaid = price_interviews(user.interviews.filter(payout__isnull=True), rate_book)
    shown = price_interviews(
        user.interviews.filter(date__range=(period.start, period.end)).select_related(
            "interview_type", "payout"
        ),
        rate_book,
    )

    return render(
        request,
        "tracker/home.html",
        {
            "nav": "home",
            "today": today,
            "rate": rate_book.current_rate(user.pk),
            "week_totals": Totals.of(i for i in in_range if week.contains(i.date)),
            "month_totals": Totals.of(i for i in in_range if month.contains(i.date)),
            "unpaid_totals": Totals.of(unpaid),
            "upcoming": summarize_weeks(unpaid),
            "paid_total": user.payouts.aggregate(total=Sum("amount"))["total"] or ZERO,
            "last_payout": user.payouts.first(),
            "chart": weekly_chart(in_range, weeks),
            "totals": Totals.of(shown),
            "groups": group_for_display(period, shown),
            "show_actions": True,
            "payouts": Paginator(user.payouts.all(), 10).get_page(request.GET.get("page")),
            **period_context(period),
        },
    )


@login_required
def interview_create(request):
    if not request.user.can_log_interviews:
        messages.error(request, "Your account needs admin approval before you can log interviews.")
        return redirect("tracker:home")

    if request.method == "POST":
        form = InterviewForm(request.POST, owner=request.user)
        if form.is_valid():
            interview = form.save()
            messages.success(
                request,
                f"Logged {duration(interview.duration_minutes)} with {interview.interview_with}.",
            )
            if "add_another" in request.POST:
                return redirect(f"{reverse('tracker:interview_create')}?date={interview.date.isoformat()}")
            return redirect(home_url(interview.date))
    else:
        form = InterviewForm(
            owner=request.user,
            initial={"date": parse_date(request.GET.get("date")) or timezone.localdate()},
        )
    return render(
        request,
        "tracker/interview_form.html",
        {"nav": "log", "form": form, "cancel_url": home_url()},
    )


def _editable_interview(request, pk):
    """An interview the current user may change: their own, or anyone's for admins."""
    interviews = Interview.objects.select_related("user", "interview_type")
    if not request.user.is_staff:
        interviews = interviews.filter(user=request.user)
    return get_object_or_404(interviews, pk=pk)


def _back_url(request, interview):
    if interview.user_id == request.user.pk:
        fallback = home_url(interview.date)
    else:
        query = urlencode({"user": interview.user_id, "date": interview.date.isoformat()})
        fallback = f"{reverse('tracker:manage_interviews')}?{query}"
    return safe_next(request, fallback)


PAID_LOCKED = "This interview is already paid, so it can't be changed."


@login_required
def interview_edit(request, pk):
    interview = _editable_interview(request, pk)
    back = _back_url(request, interview)
    if interview.is_paid:
        messages.error(request, PAID_LOCKED)
        return redirect(back)

    if request.method == "POST":
        form = InterviewForm(request.POST, instance=interview, owner=interview.user)
        if form.is_valid():
            with transaction.atomic():
                # Re-check under a row lock so a payout can't slip in between.
                still_unpaid = (
                    Interview.objects.select_for_update().filter(pk=interview.pk, payout__isnull=True).exists()
                )
                if still_unpaid:
                    form.save()
            if not still_unpaid:
                messages.error(request, PAID_LOCKED)
            else:
                messages.success(request, "Interview updated.")
            return redirect(back)
    else:
        form = InterviewForm(instance=interview, owner=interview.user)
    return render(
        request,
        "tracker/interview_form.html",
        {
            "nav": "interviews" if request.user.is_staff else "home",
            "form": form,
            "interview": interview,
            "next": back,
            "cancel_url": back,
        },
    )


@login_required
def interview_delete(request, pk):
    interview = _editable_interview(request, pk)
    back = _back_url(request, interview)
    if interview.is_paid:
        messages.error(request, PAID_LOCKED)
        return redirect(back)

    if request.method == "POST":
        deleted, _ = Interview.objects.filter(pk=interview.pk, payout__isnull=True).delete()
        if deleted:
            messages.success(request, "Interview deleted.")
        else:
            messages.error(request, PAID_LOCKED)
        return redirect(back)

    return render(
        request,
        "tracker/confirm.html",
        {
            "nav": "interviews" if request.user.is_staff else "home",
            "title": "Delete this interview?",
            "message": "This can't be undone.",
            "details": [
                ("Member", interview.user.display_name),
                ("Date", f"{interview.date:%a, %b} {interview.date.day}, {interview.date.year}"),
                ("Time", f"{interview.start_time:%H:%M}–{interview.end_time:%H:%M} ({duration(interview.duration_minutes)})"),
                ("Interview with", interview.interview_with),
                ("Role", interview.role),
                ("Type", interview.interview_type.name),
            ],
            "confirm_label": "Delete interview",
            "next": back,
            "cancel_url": back,
        },
    )
