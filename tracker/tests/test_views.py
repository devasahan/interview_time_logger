from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tracker.models import HourlyRate, Interview, InterviewType, Payout
from tracker.periods import Period

from .factories import PASSWORD, interview_type, make_admin, make_interview, make_user, set_rate


def last_week():
    return Period.week_of(timezone.localdate() - timedelta(days=7))


class AccessTests(TestCase):
    member_urls = [
        reverse("tracker:home"),
        reverse("tracker:interview_create"),
    ]
    admin_urls = [
        reverse("tracker:manage_overview"),
        reverse("tracker:manage_interviews"),
        reverse("tracker:manage_team"),
        reverse("tracker:manage_payroll"),
        reverse("tracker:manage_types"),
        reverse("tracker:manage_payroll_week", args=[last_week().start]),
    ]

    def test_anonymous_visitors_are_sent_to_login(self):
        for url in self.member_urls + self.admin_urls:
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}", msg_prefix=url)

    def test_members_cannot_open_admin_pages(self):
        self.client.force_login(make_user())
        for url in self.admin_urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_members_cannot_change_pay_status(self):
        member = make_user()
        set_rate(member, 20)
        interview = make_interview(member, day=timezone.localdate())
        self.client.force_login(member)
        response = self.client.post(
            reverse("tracker:manage_interview_status", args=[interview.pk]),
            {"status": "paid", "expected_amount": "20.00"},
        )
        self.assertEqual(response.status_code, 403)
        interview.refresh_from_db()
        self.assertFalse(interview.is_paid)

    def test_members_cannot_approve_anyone(self):
        pending = make_user("newbie", approved=False)
        self.client.force_login(make_user())
        response = self.client.post(reverse("tracker:manage_member_approve", args=[pending.pk]), {"rate": "99"})
        self.assertEqual(response.status_code, 403)
        pending.refresh_from_db()
        self.assertFalse(pending.is_approved)

    def test_members_cannot_touch_other_members_interviews(self):
        other = make_interview(make_user("sam"))
        self.client.force_login(make_user())
        for name in ("tracker:interview_edit", "tracker:interview_delete"):
            self.assertEqual(self.client.get(reverse(name, args=[other.pk])).status_code, 404)
        self.client.post(reverse("tracker:interview_delete", args=[other.pk]))
        self.assertTrue(Interview.objects.filter(pk=other.pk).exists())

    def test_admin_home_is_the_overview(self):
        self.client.force_login(make_admin())
        self.assertRedirects(self.client.get(reverse("tracker:home")), reverse("tracker:manage_overview"))

    def test_health_check(self):
        self.assertEqual(self.client.get("/healthz/").content, b"ok")


class MemberFlowTests(TestCase):
    def setUp(self):
        self.user = make_user()
        set_rate(self.user, 20)
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def form_data(self, **overrides):
        data = {
            "date": self.today.isoformat(),
            "start_time": "09:00",
            "end_time": "10:30",
            "interview_with": "Globex",
            "role": "Data Engineer",
            "interview_type": interview_type("HR").pk,
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_pending_members_cannot_log_interviews(self):
        pending = make_user("newbie", approved=False)
        self.client.force_login(pending)
        response = self.client.get(reverse("tracker:home"))
        self.assertContains(response, "waiting for approval")
        self.assertRedirects(self.client.get(reverse("tracker:interview_create")), reverse("tracker:home"))
        self.client.post(reverse("tracker:interview_create"), self.form_data())
        self.assertFalse(Interview.objects.exists())

    def test_log_an_interview(self):
        response = self.client.post(reverse("tracker:interview_create"), self.form_data())
        interview = Interview.objects.get()
        self.assertEqual((interview.user, interview.duration_minutes), (self.user, 90))
        self.assertRedirects(
            response, f"{reverse('tracker:home')}?period=week&date={self.today.isoformat()}#interviews"
        )
        home = self.client.get(response.url)
        self.assertContains(home, "Globex")
        self.assertContains(home, "$30.00")
        # Editing from the list comes back to the same spot on the page.
        self.assertContains(home, "%23interviews")

    def test_save_and_log_another_keeps_the_date(self):
        response = self.client.post(reverse("tracker:interview_create"), {**self.form_data(), "add_another": "1"})
        self.assertRedirects(response, f"{reverse('tracker:interview_create')}?date={self.today.isoformat()}")

    def test_invalid_times_show_an_error(self):
        response = self.client.post(reverse("tracker:interview_create"), self.form_data(end_time="09:00"))
        self.assertContains(response, "must be different from the start time")
        self.assertFalse(Interview.objects.exists())

    def test_double_submit_is_rejected_as_overlap(self):
        self.client.post(reverse("tracker:interview_create"), self.form_data())
        response = self.client.post(reverse("tracker:interview_create"), self.form_data())
        self.assertContains(response, "overlaps another logged interview")
        self.assertEqual(Interview.objects.count(), 1)

    def test_edit_and_delete_own_unpaid_interview(self):
        interview = make_interview(self.user, day=self.today)
        self.client.post(
            reverse("tracker:interview_edit", args=[interview.pk]),
            self.form_data(start_time="09:00", end_time="09:45"),
        )
        interview.refresh_from_db()
        self.assertEqual(interview.duration_minutes, 45)
        self.client.post(reverse("tracker:interview_delete", args=[interview.pk]))
        self.assertFalse(Interview.objects.exists())

    def test_paid_interviews_are_locked(self):
        interview = make_interview(self.user, day=self.today)
        payout = Payout.objects.create(
            user=self.user, period_start=self.today, period_end=self.today,
            interview_count=1, total_minutes=60, amount=Decimal("20"),
        )
        Interview.objects.filter(pk=interview.pk).update(payout=payout, paid_rate=20, paid_amount=20)
        self.client.post(reverse("tracker:interview_edit", args=[interview.pk]), self.form_data(end_time="12:00"))
        self.client.post(reverse("tracker:interview_delete", args=[interview.pk]))
        interview.refresh_from_db()
        self.assertEqual(interview.duration_minutes, 60)

    def test_home_shows_interviews_by_week_or_month(self):
        make_interview(self.user, day=self.today, start=time(9, 0), end=time(11, 0))
        week = self.client.get(reverse("tracker:home"))
        self.assertContains(week, Period.week_of(self.today).label)
        self.assertContains(week, "$40.00")
        month = self.client.get(reverse("tracker:home"), {"period": "month"})
        self.assertContains(month, Period.month_of(self.today).label)
        self.assertContains(month, "$40.00")

    def test_home_shows_what_is_still_to_be_paid(self):
        make_interview(self.user, day=self.today)
        home = self.client.get(reverse("tracker:home"))
        self.assertContains(home, "Coming up")
        self.assertContains(home, "$20.00")


class AdminFlowTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)
        self.week = last_week()

    def test_approve_from_the_team_page_in_one_step(self):
        newbie = make_user("newbie", approved=False)
        approve_url = reverse("tracker:manage_member_approve", args=[newbie.pk])
        self.assertContains(self.client.get(reverse("tracker:manage_team")), approve_url)

        response = self.client.post(approve_url, {"rate": "20"}, follow=True)
        self.assertRedirects(response, reverse("tracker:manage_team"))
        self.assertContains(response, "is approved at $20.00/h")
        newbie.refresh_from_db()
        self.assertTrue(newbie.is_approved)
        rate = HourlyRate.objects.get(user=newbie)
        self.assertEqual((rate.rate, rate.effective_from), (Decimal("20"), timezone.localdate()))

    def test_approving_without_a_rate_says_why(self):
        newbie = make_user("newbie", approved=False)
        response = self.client.post(
            reverse("tracker:manage_member_approve", args=[newbie.pk]), {"rate": ""}, follow=True
        )
        self.assertContains(response, "Enter an hourly rate, for example 20.00.")
        newbie.refresh_from_db()
        self.assertFalse(newbie.is_approved)

        # Same on the member page: the error shows next to the rate box.
        response = self.client.post(
            reverse("tracker:manage_member", args=[newbie.pk]),
            {"rate": "", "effective_from": timezone.localdate().isoformat()},
        )
        self.assertContains(response, "Enter an hourly rate, for example 20.00.")
        newbie.refresh_from_db()
        self.assertFalse(newbie.is_approved)

    def test_approve_a_new_member_by_setting_their_rate(self):
        newbie = make_user("newbie", approved=False)
        self.assertContains(self.client.get(reverse("tracker:manage_team")), "Waiting for approval")
        response = self.client.post(
            reverse("tracker:manage_member", args=[newbie.pk]),
            {"rate": "25.50", "effective_from": timezone.localdate().isoformat()},
        )
        self.assertRedirects(response, reverse("tracker:manage_member", args=[newbie.pk]))
        newbie.refresh_from_db()
        self.assertTrue(newbie.is_approved)
        self.assertEqual(HourlyRate.objects.get(user=newbie).rate, Decimal("25.50"))

    def test_rejects_negative_rates(self):
        member = make_user()
        response = self.client.post(
            reverse("tracker:manage_member", args=[member.pk]),
            {"rate": "-5", "effective_from": timezone.localdate().isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HourlyRate.objects.exists())

    def test_member_page_shows_the_rate_in_effect_and_the_next_change(self):
        member = make_user()
        today = timezone.localdate()
        set_rate(member, 20, today - timedelta(days=30))
        set_rate(member, 30, today + timedelta(days=7))
        response = self.client.get(reverse("tracker:manage_member", args=[member.pk]))
        self.assertEqual(response.context["rate"], Decimal("20"))
        self.assertEqual(response.context["rate_since"], today - timedelta(days=30))
        self.assertEqual(response.context["next_rate"].rate, Decimal("30"))
        self.assertContains(response, "$30.00/h from")

    def test_pay_a_week_then_undo(self):
        member = make_user()
        set_rate(member, 20)
        interview = make_interview(member, day=self.week.start, start=time(9, 0), end=time(10, 30))

        week_page = self.client.get(reverse("tracker:manage_payroll_week", args=[self.week.start]))
        self.assertContains(week_page, "Pay $30.00")

        pay_url = reverse("tracker:manage_payroll_pay", args=[self.week.start]) + f"?user={member.pk}"
        confirm = self.client.get(pay_url)
        self.assertContains(confirm, "Mark $30.00 as paid")
        response = self.client.post(
            pay_url, {"interview_ids": str(interview.pk), "expected_total": "30.00", "note": "Wise #123"}
        )
        self.assertRedirects(response, reverse("tracker:manage_payroll_week", args=[self.week.start]))
        payout = Payout.objects.get()
        self.assertEqual((payout.user, payout.amount, payout.paid_by), (member, Decimal("30.00"), self.admin))

        # The member sees it in their payment history.
        self.client.force_login(member)
        self.assertContains(self.client.get(reverse("tracker:home")), "Wise #123")

        self.client.force_login(self.admin)
        self.client.post(reverse("tracker:manage_payout_undo", args=[payout.pk]))
        self.assertFalse(Payout.objects.exists())
        interview.refresh_from_db()
        self.assertFalse(interview.is_paid)

    def test_change_an_interviews_pay_status_from_the_list(self):
        member = make_user()
        set_rate(member, 20)
        interview = make_interview(member, day=timezone.localdate(), start=time(9, 0), end=time(10, 30))
        interviews_url = reverse("tracker:manage_interviews")
        status_url = reverse("tracker:manage_interview_status", args=[interview.pk])
        self.assertContains(self.client.get(interviews_url), status_url)

        response = self.client.post(
            status_url, {"status": "paid", "expected_amount": "30.00", "next": interviews_url}
        )
        self.assertRedirects(response, interviews_url)
        interview.refresh_from_db()
        self.assertTrue(interview.is_paid)
        self.assertEqual(interview.payout.amount, Decimal("30.00"))

        # The member sees it as paid, but can't change it.
        self.client.force_login(member)
        home = self.client.get(reverse("tracker:home"))
        self.assertContains(home, "badge-paid")
        self.assertNotContains(home, status_url)

        self.client.force_login(self.admin)
        self.client.post(status_url, {"status": "unpaid", "next": interviews_url})
        interview.refresh_from_db()
        self.assertFalse(interview.is_paid)
        self.assertFalse(Payout.objects.exists())

    def test_pay_status_change_refuses_a_changed_amount(self):
        member = make_user()
        set_rate(member, 20)
        interview = make_interview(member, day=timezone.localdate())
        url = reverse("tracker:manage_interview_status", args=[interview.pk])
        self.client.post(url, {"status": "paid", "expected_amount": "99.00"})
        self.client.post(url, {"status": "paid", "expected_amount": "not-a-number"})
        interview.refresh_from_db()
        self.assertFalse(interview.is_paid)

    def test_stale_payment_is_refused(self):
        member = make_user()
        set_rate(member, 20)
        interview = make_interview(member, day=self.week.start)
        url = reverse("tracker:manage_payroll_pay", args=[self.week.start])
        response = self.client.post(url, {"interview_ids": str(interview.pk), "expected_total": "99.00"})
        self.assertRedirects(response, url)
        self.assertFalse(Payout.objects.exists())

    def test_member_without_rate_cannot_be_paid(self):
        member = make_user()
        make_interview(member, day=self.week.start)
        response = self.client.get(reverse("tracker:manage_payroll_pay", args=[self.week.start]))
        self.assertRedirects(response, reverse("tracker:manage_payroll_week", args=[self.week.start]))

    def test_deactivate_and_reactivate(self):
        member = make_user()
        url = reverse("tracker:manage_member_active", args=[member.pk])
        self.client.post(url)
        member.refresh_from_db()
        self.assertFalse(member.is_active)
        self.client.post(url)
        member.refresh_from_db()
        self.assertTrue(member.is_active)

    def test_cannot_deactivate_yourself(self):
        self.client.post(reverse("tracker:manage_member_active", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_fix_a_members_interview(self):
        member = make_user()
        interview = make_interview(member, day=timezone.localdate())
        data = {
            "date": interview.date.isoformat(), "start_time": "13:00", "end_time": "14:00",
            "interview_with": "Initech", "role": "QA", "interview_type": interview.interview_type_id,
        }
        self.client.post(reverse("tracker:interview_edit", args=[interview.pk]), data)
        interview.refresh_from_db()
        self.assertEqual(interview.interview_with, "Initech")

    def test_interview_types(self):
        self.client.post(reverse("tracker:manage_types"), {"name": "Panel", "is_active": "on"})
        self.assertTrue(InterviewType.objects.filter(name="Panel", is_active=True).exists())
        duplicate = self.client.post(reverse("tracker:manage_types"), {"name": "panel"})
        self.assertContains(duplicate, "already exists")
        panel = InterviewType.objects.get(name="Panel")
        self.client.post(reverse("tracker:manage_type_edit", args=[panel.pk]), {"name": "Panel Interview"})
        panel.refresh_from_db()
        self.assertEqual((panel.name, panel.is_active), ("Panel Interview", False))

    def test_all_admin_pages_render(self):
        member = make_user()
        set_rate(member, 20)
        make_interview(member, day=self.week.start)
        make_interview(member, day=timezone.localdate())
        make_user("pending", approved=False)
        urls = [
            reverse("tracker:manage_overview"),
            reverse("tracker:manage_interviews"),
            reverse("tracker:manage_interviews") + f"?user={member.pk}&period=month",
            reverse("tracker:manage_team"),
            reverse("tracker:manage_member", args=[member.pk]),
            reverse("tracker:manage_payroll"),
            reverse("tracker:manage_payroll_week", args=[self.week.start]),
            reverse("tracker:manage_payroll_pay", args=[self.week.start]),
            reverse("tracker:manage_types"),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_payroll_week_url_is_normalised_to_week_start(self):
        middle = self.week.start + timedelta(days=3)
        response = self.client.get(reverse("tracker:manage_payroll_week", args=[middle]))
        self.assertRedirects(response, reverse("tracker:manage_payroll_week", args=[self.week.start]))


class LoginFlowTests(TestCase):
    def test_member_logs_in_and_lands_on_dashboard(self):
        make_user("alex")
        response = self.client.post(reverse("accounts:login"), {"username": "alex", "password": PASSWORD})
        self.assertRedirects(response, reverse("tracker:home"))
