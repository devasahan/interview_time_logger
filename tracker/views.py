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

from .forms import BidForm, InterviewForm, WorkForm
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


TIME_FORMS = {"interview": InterviewForm, "work": WorkForm}
HEADINGS = {
    "interview": ("Log an interview", "Edit interview"),
    "work": ("Log work", "Edit work"),
    "bids": ("Log bids", "Edit bids"),
}


def _saved_message(entry):
    if entry.is_bid_log:
        return f"Logged {entry.bids:,} bid{'' if entry.bids == 1 else 's'} for {entry.date:%a, %b} {entry.date.day}."
    if entry.is_interview:
        return f"Logged {duration(entry.duration_minutes)} with {entry.interview_with}."
    return f"Logged {duration(entry.duration_minutes)} on {entry.interview_with}."


def _log_form_page(request, form, kind, entry=None, **extra):
    template = "tracker/bid_form.html" if kind == "bids" else "tracker/interview_form.html"
    new_heading, edit_heading = HEADINGS[kind]
    return render(
        request,
        template,
        {
            "nav": "log" if entry is None else ("interviews" if request.user.is_staff else "home"),
            "form": form,
            "kind": kind,
            "heading": edit_heading if entry else new_heading,
            "interview": entry,
            **extra,
        },
    )


def _can_log(request):
    if request.user.can_log_interviews:
        return True
    messages.error(request, "Your account needs admin approval before you can log work.")
    return False


@login_required
def interview_create(request):
    """Log an interview, or developer work, depending on the member's role."""
    if not _can_log(request):
        return redirect("tracker:home")
    kind = request.user.work_kind
    if kind == "bids":
        return redirect(f"{reverse('tracker:bid_create')}?{request.GET.urlencode()}".rstrip("?"))

    form_class = TIME_FORMS[kind]
    if request.method == "POST":
        form = form_class(request.POST, owner=request.user)
        if form.is_valid():
            entry = form.save()
            messages.success(request, _saved_message(entry))
            if "add_another" in request.POST:
                return redirect(f"{reverse('tracker:interview_create')}?date={entry.date.isoformat()}")
            return redirect(home_url(entry.date))
    else:
        form = form_class(
            owner=request.user,
            initial={"date": parse_date(request.GET.get("date")) or timezone.localdate()},
        )
    return _log_form_page(request, form, kind, cancel_url=home_url())


@login_required
def bid_create(request):
    """Virtual assistants log how many bids they sent on a day."""
    if not _can_log(request):
        return redirect("tracker:home")
    if not request.user.logs_bids:
        return redirect("tracker:interview_create")

    if request.method == "POST":
        form = BidForm(request.POST, owner=request.user)
        if form.is_valid():
            entry = form.save()
            messages.success(request, _saved_message(entry))
            return redirect(home_url(entry.date))
    else:
        form = BidForm(
            owner=request.user,
            initial={"date": parse_date(request.GET.get("date")) or timezone.localdate()},
        )
    return _log_form_page(request, form, "bids", cancel_url=home_url())


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


PAID_LOCKED = "This work is already paid, so it can't be changed."


def _edit_entry(request, entry, form_class, kind):
    back = _back_url(request, entry)
    if entry.is_paid:
        messages.error(request, PAID_LOCKED)
        return redirect(back)

    if request.method == "POST":
        form = form_class(request.POST, instance=entry, owner=entry.user)
        if form.is_valid():
            with transaction.atomic():
                # Re-check under a row lock so a payout can't slip in between.
                still_unpaid = Interview.objects.select_for_update().filter(pk=entry.pk, payout__isnull=True).exists()
                if still_unpaid:
                    form.save()
            if not still_unpaid:
                messages.error(request, PAID_LOCKED)
            else:
                messages.success(request, {"bids": "Bids updated.", "work": "Work updated."}.get(kind, "Interview updated."))
            return redirect(back)
    else:
        form = form_class(instance=entry, owner=entry.user)
    return _log_form_page(request, form, kind, entry, next=back, cancel_url=back)


@login_required
def interview_edit(request, pk):
    entry = _editable_interview(request, pk)
    if entry.is_bid_log:
        return redirect(f"{reverse('tracker:bid_edit', args=[entry.pk])}?{request.GET.urlencode()}".rstrip("?"))
    return _edit_entry(request, entry, TIME_FORMS[entry.kind], entry.kind)


@login_required
def bid_edit(request, pk):
    entry = _editable_interview(request, pk)
    if not entry.is_bid_log:
        return redirect(f"{reverse('tracker:interview_edit', args=[entry.pk])}?{request.GET.urlencode()}".rstrip("?"))
    return _edit_entry(request, entry, BidForm, "bids")


def _entry_details(entry):
    date = f"{entry.date:%a, %b} {entry.date.day}, {entry.date.year}"
    details = [("Member", entry.user.display_name), ("Date", date)]
    if entry.is_bid_log:
        details.append(("Bids", f"{entry.bids:,}"))
        if entry.notes:
            details.append(("Notes", entry.notes))
        return details
    details.append(("Time", f"{entry.start_time:%H:%M}–{entry.end_time:%H:%M} ({duration(entry.duration_minutes)})"))
    if entry.is_interview:
        details += [("Interview with", entry.interview_with), ("Role", entry.role), ("Type", entry.interview_type.name)]
    else:
        details += [("Project", entry.interview_with), ("Task", entry.role)]
    return details


@login_required
def interview_delete(request, pk):
    interview = _editable_interview(request, pk)
    back = _back_url(request, interview)
    if interview.is_paid:
        messages.error(request, PAID_LOCKED)
        return redirect(back)

    noun = {"bids": "bids", "work": "work entry"}.get(interview.kind, "interview")
    if request.method == "POST":
        deleted, _ = Interview.objects.filter(pk=interview.pk, payout__isnull=True).delete()
        if deleted:
            messages.success(request, f"{noun.capitalize()} deleted.")
        else:
            messages.error(request, PAID_LOCKED)
        return redirect(back)

    return render(
        request,
        "tracker/confirm.html",
        {
            "nav": "interviews" if request.user.is_staff else "home",
            "title": "Delete these bids?" if interview.is_bid_log else f"Delete this {noun}?",
            "message": "This can't be undone.",
            "details": _entry_details(interview),
            "confirm_label": f"Delete {noun}",
            "next": back,
            "cancel_url": back,
        },
    )
