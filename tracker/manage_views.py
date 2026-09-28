"""Admin pages: overview, team and rates, all interviews, payroll and interview types."""

from functools import wraps
from operator import attrgetter

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import InterviewTypeForm, PayoutForm, RateForm
from .models import HourlyRate, Interview, InterviewType, Payout
from .periods import Period, format_range
from .services import (
    ZERO,
    PayoutError,
    RateBook,
    Totals,
    group_for_display,
    price_interviews,
    record_payouts,
    set_hourly_rate,
    summarize_weeks,
    totals_by_member,
    totals_by_user,
    undo_payout,
)
from .templatetags.tracker_tags import money
from .views import period_context, safe_next

User = get_user_model()

STATUS_ORDER = {"pending": 0, "active": 1, "admin": 2, "deactivated": 3}


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _long_date(day):
    return f"{day:%b} {day.day}, {day.year}"


def _paid_between(start, end):
    return Payout.objects.filter(paid_at__date__range=(start, end)).aggregate(total=Sum("amount"))["total"] or ZERO


@staff_required
def overview(request):
    today = timezone.localdate()
    week, month = Period.week_of(today), Period.month_of(today)
    rate_book = RateBook()

    week_interviews = price_interviews(Interview.objects.filter(date__range=(week.start, week.end)), rate_book)
    unpaid = price_interviews(Interview.objects.filter(payout__isnull=True), rate_book)
    week_by_user, unpaid_by_user = totals_by_user(week_interviews), totals_by_user(unpaid)

    members = list(User.objects.filter(is_active=True, is_staff=False))
    rows = [
        {
            "member": member,
            "rate": rate_book.current_rate(member.pk),
            "week": week_by_user.get(member.pk, Totals()),
            "unpaid": unpaid_by_user.get(member.pk, Totals()),
        }
        for member in members
        if member.is_approved
    ]
    recent = price_interviews(
        Interview.objects.select_related("user", "interview_type", "payout").order_by("-created_at")[:8],
        rate_book,
    )
    return render(
        request,
        "manage/overview.html",
        {
            "nav": "overview",
            "today": today,
            "week": week,
            "week_totals": Totals.of(week_interviews),
            "unpaid_totals": Totals.of(unpaid),
            "unpaid_weeks": summarize_weeks(unpaid),
            "paid_this_month": _paid_between(month.start, month.end),
            "month": month,
            "rows": rows,
            "pending_members": [member for member in members if not member.is_approved],
            "recent": recent,
        },
    )


@staff_required
def team(request):
    week = Period.week_of(timezone.localdate())
    rate_book = RateBook()
    week_by_user = totals_by_user(
        price_interviews(Interview.objects.filter(date__range=(week.start, week.end)), rate_book)
    )
    unpaid_by_user = totals_by_user(price_interviews(Interview.objects.filter(payout__isnull=True), rate_book))
    members = sorted(User.objects.all(), key=lambda m: (STATUS_ORDER[m.status], m.display_name.lower()))
    rows = [
        {
            "member": member,
            "rate": rate_book.current_rate(member.pk),
            "week": week_by_user.get(member.pk, Totals()),
            "unpaid": unpaid_by_user.get(member.pk, Totals()),
        }
        for member in members
    ]
    return render(request, "manage/team.html", {"nav": "team", "rows": rows})


@staff_required
def member_detail(request, pk):
    member = get_object_or_404(User, pk=pk)
    today = timezone.localdate()

    form = RateForm(request.POST if request.method == "POST" else None)
    if form.is_bound and form.is_valid():
        rate, effective_from = form.cleaned_data["rate"], form.cleaned_data["effective_from"]
        set_hourly_rate(member, rate, effective_from, request.user)
        if not member.is_approved:
            member.is_approved = True
            member.save(update_fields=["is_approved"])
            messages.success(
                request,
                f"{member.display_name} is approved at {money(rate)}/h and can start logging interviews.",
            )
        else:
            messages.success(
                request, f"{member.display_name}'s rate is {money(rate)}/h from {_long_date(effective_from)}."
            )
        return redirect("tracker:manage_member", pk=member.pk)

    rate_book = RateBook([member.pk])
    current_rate = rate_book.current_rate(member.pk)
    if not form.is_bound:
        form = RateForm(initial={"rate": current_rate, "effective_from": today})

    week, month = Period.week_of(today), Period.month_of(today)
    in_range = price_interviews(
        member.interviews.filter(date__range=(min(week.start, month.start), max(week.end, month.end))),
        rate_book,
    )
    unpaid = price_interviews(member.interviews.filter(payout__isnull=True), rate_book)
    return render(
        request,
        "manage/member.html",
        {
            "nav": "team",
            "member": member,
            "rate": current_rate,
            "form": form,
            "rates": member.rates.select_related("set_by").order_by("-effective_from"),
            "week_totals": Totals.of(i for i in in_range if week.contains(i.date)),
            "month_totals": Totals.of(i for i in in_range if month.contains(i.date)),
            "unpaid_totals": Totals.of(unpaid),
            "unpaid_weeks": summarize_weeks(unpaid),
            "payouts": member.payouts.select_related("paid_by")[:10],
            "is_self": member.pk == request.user.pk,
        },
    )


@staff_required
@require_POST
def member_toggle_active(request, pk):
    member = get_object_or_404(User, pk=pk)
    if member.pk == request.user.pk:
        messages.error(request, "You can't deactivate your own account.")
    else:
        member.is_active = not member.is_active
        member.save(update_fields=["is_active"])
        if member.is_active:
            messages.success(request, f"{member.display_name} can sign in again.")
        else:
            messages.success(
                request, f"{member.display_name} was deactivated and can no longer sign in. Their history is kept."
            )
    return redirect("tracker:manage_member", pk=member.pk)


@staff_required
@require_POST
def member_delete_rate(request, pk, rate_pk):
    rate = get_object_or_404(HourlyRate, pk=rate_pk, user_id=pk)
    rate.delete()
    messages.success(request, f"Removed the {money(rate.rate)}/h rate from {_long_date(rate.effective_from)}.")
    return redirect("tracker:manage_member", pk=pk)


@staff_required
def interviews(request):
    period = Period.from_query(request.GET)
    queryset = Interview.objects.filter(date__range=(period.start, period.end)).select_related(
        "user", "interview_type", "payout"
    )
    selected = None
    member_id = _int_or_none(request.GET.get("user"))
    if member_id is not None:
        selected = get_object_or_404(User, pk=member_id)
        queryset = queryset.filter(user=selected)
    priced = price_interviews(queryset)
    return render(
        request,
        "tracker/history.html",
        {
            "nav": "interviews",
            "heading": selected.display_name if selected else "All interviews",
            "admin_view": True,
            "members": User.objects.all(),
            "selected_member": selected,
            "member_rows": [] if selected else totals_by_member(priced),
            "totals": Totals.of(priced),
            "groups": group_for_display(period, priced),
            "show_user": selected is None,
            "show_actions": True,
            **period_context(period),
        },
    )


@staff_required
def payroll(request):
    today = timezone.localdate()
    month = Period.month_of(today)
    unpaid = price_interviews(Interview.objects.filter(payout__isnull=True))
    return render(
        request,
        "manage/payroll.html",
        {
            "nav": "payroll",
            "weeks": list(reversed(summarize_weeks(unpaid))),
            "unpaid_totals": Totals.of(unpaid),
            "members_owed": len({interview.user_id for interview in unpaid}),
            "paid_this_month": _paid_between(month.start, month.end),
            "month": month,
            "current_week": Period.week_of(today),
            "payouts": Paginator(Payout.objects.select_related("user", "paid_by"), 25).get_page(
                request.GET.get("page")
            ),
        },
    )


@staff_required
def payroll_week(request, start):
    period = Period.week_of(start)
    if period.start != start:
        return redirect("tracker:manage_payroll_week", start=period.start)
    interviews = price_interviews(
        Interview.objects.filter(date__range=(period.start, period.end)).select_related(
            "user", "interview_type", "payout"
        )
    )
    return render(
        request,
        "manage/payroll_week.html",
        {
            "nav": "payroll",
            "period": period,
            "rows": totals_by_member(interviews),
            "totals": Totals.of(interviews),
            "interviews": sorted(interviews, key=attrgetter("date", "start_time")),
            "payouts": Payout.objects.filter(period_start=period.start).select_related("user", "paid_by"),
            "show_user": True,
            "show_actions": True,
        },
    )


@staff_required
def payroll_pay(request, start):
    period = Period.week_of(start)
    week_url = reverse("tracker:manage_payroll_week", args=[period.start])
    queryset = Interview.objects.filter(
        date__range=(period.start, period.end), payout__isnull=True
    ).select_related("user", "interview_type")
    member = None
    member_id = _int_or_none(request.GET.get("user"))
    if member_id is not None:
        member = get_object_or_404(User, pk=member_id)
        queryset = queryset.filter(user=member)

    interviews = sorted(price_interviews(queryset), key=attrgetter("date", "start_time"))
    payable = [interview for interview in interviews if interview.amount is not None]
    skipped = totals_by_member([interview for interview in interviews if interview.amount is None])
    if not payable:
        if skipped:
            names = ", ".join(m.display_name for m, _ in skipped)
            messages.error(request, f"Set an hourly rate for {names} before paying.")
        else:
            messages.info(request, "Everything in this week is already paid.")
        return redirect(week_url)
    total = sum((interview.amount for interview in payable), ZERO)

    if request.method == "POST":
        form = PayoutForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Something went wrong with that payment. Please review it and try again.")
            return redirect(request.get_full_path())
        try:
            payouts = record_payouts(
                period=period,
                interview_ids=form.cleaned_data["interview_ids"],
                expected_total=form.cleaned_data["expected_total"],
                paid_by=request.user,
                note=form.cleaned_data["note"].strip(),
            )
        except PayoutError as error:
            messages.error(request, str(error))
            return redirect(request.get_full_path())
        paid = sum((payout.amount for payout in payouts), ZERO)
        names = ", ".join(sorted(payout.user.display_name for payout in payouts))
        messages.success(request, f"Recorded {money(paid)} paid to {names} for {period.label}.")
        return redirect(week_url)

    form = PayoutForm(
        initial={"interview_ids": ",".join(str(interview.pk) for interview in payable), "expected_total": total}
    )
    groups = [
        {
            "member": group_member,
            "totals": group_totals,
            "interviews": [interview for interview in payable if interview.user_id == group_member.pk],
        }
        for group_member, group_totals in totals_by_member(payable)
    ]
    return render(
        request,
        "manage/pay_confirm.html",
        {
            "nav": "payroll",
            "period": period,
            "member": member,
            "groups": groups,
            "total": total,
            "skipped": skipped,
            "form": form,
            "week_url": week_url,
        },
    )


@staff_required
def payout_undo(request, pk):
    payout = get_object_or_404(Payout.objects.select_related("user"), pk=pk)
    back = safe_next(request, reverse("tracker:manage_payroll"))
    if request.method == "POST":
        undo_payout(payout)
        messages.success(
            request,
            f"Undid the {money(payout.amount)} payment to {payout.user.display_name}. "
            "Those interviews are unpaid again.",
        )
        return redirect(back)
    return render(
        request,
        "tracker/confirm.html",
        {
            "nav": "payroll",
            "title": "Undo this payment?",
            "message": (
                "The payment record is deleted and its interviews go back to “to be paid”. "
                "Use this when a payment was recorded by mistake."
            ),
            "details": [
                ("Member", payout.user.display_name),
                ("Week", format_range(payout.period_start, payout.period_end)),
                ("Amount", money(payout.amount)),
                ("Interviews", payout.interview_count),
                ("Paid on", _long_date(timezone.localtime(payout.paid_at).date())),
                ("Note", payout.note or "—"),
            ],
            "confirm_label": "Undo payment",
            "next": back,
            "cancel_url": back,
        },
    )


@staff_required
def interview_types(request):
    form = InterviewTypeForm(request.POST if request.method == "POST" else None)
    if form.is_bound and form.is_valid():
        interview_type = form.save()
        messages.success(request, f"Added the “{interview_type.name}” interview type.")
        return redirect("tracker:manage_types")
    types = InterviewType.objects.annotate(usage=Count("interviews")).order_by("-is_active", "name")
    return render(request, "manage/types.html", {"nav": "types", "form": form, "types": types})


@staff_required
def interview_type_edit(request, pk):
    interview_type = get_object_or_404(InterviewType, pk=pk)
    original_name = interview_type.name  # the form updates the instance while validating
    form = InterviewTypeForm(request.POST if request.method == "POST" else None, instance=interview_type)
    if form.is_bound and form.is_valid():
        form.save()
        messages.success(request, f"Saved “{interview_type.name}”.")
        return redirect("tracker:manage_types")
    return render(
        request,
        "manage/type_form.html",
        {"nav": "types", "form": form, "original_name": original_name, "usage": interview_type.interviews.count()},
    )
