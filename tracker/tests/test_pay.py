from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from tracker.models import Interview, Payout
from tracker.periods import Period
from tracker.services import (
    PayoutError,
    RateBook,
    Totals,
    amount_for,
    group_for_display,
    price_interviews,
    record_payouts,
    set_hourly_rate,
    undo_payout,
)

from .factories import make_admin, make_interview, make_user, set_rate

WEEK = Period.week_of(date(2026, 9, 21))


class AmountTests(TestCase):
    def test_amount_is_rounded_to_cents(self):
        self.assertEqual(amount_for(60, Decimal("20")), Decimal("20.00"))
        self.assertEqual(amount_for(50, Decimal("25")), Decimal("20.83"))
        self.assertEqual(amount_for(90, Decimal("15.50")), Decimal("23.25"))
        self.assertEqual(amount_for(1, Decimal("0.30")), Decimal("0.01"))  # 0.005 rounds half up


class RateBookTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_no_rate(self):
        self.assertIsNone(RateBook().rate_for(self.user.pk, date(2026, 9, 21)))

    def test_rate_history(self):
        set_rate(self.user, 20, date(2026, 9, 1))
        set_rate(self.user, 25, date(2026, 9, 15))
        book = RateBook([self.user.pk])
        self.assertEqual(book.rate_for(self.user.pk, date(2026, 8, 1)), Decimal("20"))  # first rate covers earlier work
        self.assertEqual(book.rate_for(self.user.pk, date(2026, 9, 14)), Decimal("20"))
        self.assertEqual(book.rate_for(self.user.pk, date(2026, 9, 15)), Decimal("25"))
        self.assertEqual(book.rate_for(self.user.pk, date(2026, 12, 1)), Decimal("25"))

    def test_setting_a_rate_for_the_same_day_replaces_it(self):
        admin = make_admin()
        set_hourly_rate(self.user, Decimal("20"), date(2026, 9, 1), admin)
        set_hourly_rate(self.user, Decimal("22"), date(2026, 9, 1), admin)
        self.assertEqual(self.user.rates.get().rate, Decimal("22"))


class PricingTests(TestCase):
    def setUp(self):
        self.user = make_user()
        set_rate(self.user, 30)

    def test_unpaid_interviews_use_current_rate_history(self):
        interview = make_interview(self.user, start=time(9, 0), end=time(10, 30))
        [priced] = price_interviews([interview])
        self.assertEqual((priced.rate, priced.amount), (Decimal("30"), Decimal("45.00")))

    def test_totals(self):
        make_interview(self.user, start=time(9, 0), end=time(10, 0))
        make_interview(self.user, start=time(11, 0), end=time(11, 30))
        stranger = make_user("sam")  # no rate yet
        make_interview(stranger, start=time(9, 0), end=time(10, 0))
        totals = Totals.of(price_interviews(Interview.objects.all()))
        self.assertEqual(totals.count, 3)
        self.assertEqual(totals.minutes, 150)
        self.assertEqual(totals.earned, Decimal("45.00"))
        self.assertEqual(totals.unpaid, Decimal("45.00"))
        self.assertEqual(totals.unpriced, 1)

    def test_groups_by_day_for_a_week_and_by_week_for_a_month(self):
        make_interview(self.user, day=date(2026, 9, 21))
        make_interview(self.user, day=date(2026, 9, 21), start=time(14, 0), end=time(15, 0))
        make_interview(self.user, day=date(2026, 9, 29))
        interviews = price_interviews(Interview.objects.all())

        week_groups = group_for_display(WEEK, [i for i in interviews if WEEK.contains(i.date)])
        self.assertEqual([g.label for g in week_groups], ["Monday, Sep 21"])
        self.assertEqual(week_groups[0].totals.count, 2)

        month_groups = group_for_display(Period.month_of(date(2026, 9, 1)), interviews)
        self.assertEqual([g.label for g in month_groups], ["Sep 21 – 27", "Sep 28 – 30"])


class PayoutTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.alex = make_user("alex")
        self.sam = make_user("sam")
        set_rate(self.alex, 20)
        set_rate(self.sam, 30)
        self.a1 = make_interview(self.alex, day=date(2026, 9, 21), start=time(9, 0), end=time(10, 0))
        self.a2 = make_interview(self.alex, day=date(2026, 9, 23), start=time(9, 0), end=time(9, 30))
        self.s1 = make_interview(self.sam, day=date(2026, 9, 22), start=time(9, 0), end=time(11, 0))

    def pay(self, interviews, expected_total, **kwargs):
        return record_payouts(
            period=WEEK,
            interview_ids=[i.pk for i in interviews],
            expected_total=Decimal(expected_total),
            paid_by=self.admin,
            **kwargs,
        )

    def test_one_payout_per_member_with_frozen_amounts(self):
        payouts = self.pay([self.a1, self.a2, self.s1], "90.00", note="Bank transfer")
        self.assertEqual(len(payouts), 2)
        alex_payout = Payout.objects.get(user=self.alex)
        self.assertEqual(
            (alex_payout.amount, alex_payout.interview_count, alex_payout.total_minutes), (Decimal("30.00"), 2, 90)
        )
        self.assertEqual((alex_payout.period_start, alex_payout.period_end), (WEEK.start, WEEK.end))
        self.assertEqual(alex_payout.note, "Bank transfer")
        self.a1.refresh_from_db()
        self.assertEqual((self.a1.paid_rate, self.a1.paid_amount), (Decimal("20.00"), Decimal("20.00")))

    def test_rate_changes_do_not_touch_paid_work(self):
        self.pay([self.a1], "20.00")
        set_hourly_rate(self.alex, Decimal("50"), date(2026, 1, 1), self.admin)  # retroactive change
        a1, a2 = price_interviews(Interview.objects.filter(pk__in=[self.a1.pk, self.a2.pk]).order_by("date"))
        self.assertEqual(a1.amount, Decimal("20.00"))  # paid: frozen
        self.assertEqual(a2.amount, Decimal("25.00"))  # unpaid: new rate

    def test_refuses_when_the_total_changed_since_review(self):
        with self.assertRaises(PayoutError):
            self.pay([self.a1, self.a2], "25.00")
        self.assertFalse(Payout.objects.exists())

    def test_refuses_already_paid_or_deleted_interviews(self):
        self.pay([self.a1], "20.00")
        with self.assertRaises(PayoutError):
            self.pay([self.a1, self.a2], "30.00")
        self.a2.delete()
        with self.assertRaises(PayoutError):
            self.pay([self.a2], "10.00")
        self.assertEqual(Payout.objects.count(), 1)

    def test_refuses_interviews_outside_the_week(self):
        other = make_interview(self.alex, day=date(2026, 9, 28))
        with self.assertRaises(PayoutError):
            self.pay([other], "20.00")

    def test_refuses_members_without_a_rate(self):
        newbie = make_user("newbie")
        interview = make_interview(newbie)
        with self.assertRaises(PayoutError):
            self.pay([interview], "0")

    def test_undo_makes_interviews_unpaid_again(self):
        [payout] = self.pay([self.s1], "60.00")
        undo_payout(payout)
        self.s1.refresh_from_db()
        self.assertIsNone(self.s1.payout)
        self.assertIsNone(self.s1.paid_amount)
        self.assertFalse(Payout.objects.exists())
