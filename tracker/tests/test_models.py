from datetime import date, time
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from tracker.models import Interview, validate_time_slot

from .factories import make_bids, make_interview, make_user, make_work

TODAY = date(2026, 9, 28)


@mock.patch("tracker.models.timezone.localdate", return_value=TODAY)
class TimeSlotTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def check(self, day, start, end, exclude_pk=None):
        validate_time_slot(user_id=self.user.pk, day=day, start=start, end=end, exclude_pk=exclude_pk)

    def assertInvalid(self, *args, field=None, **kwargs):
        with self.assertRaises(ValidationError) as caught:
            self.check(*args, **kwargs)
        if field:
            self.assertIn(field, caught.exception.message_dict)

    def test_duration_is_computed_on_save(self, _):
        self.assertEqual(make_interview(self.user, start=time(9, 15), end=time(10, 45)).duration_minutes, 90)

    def test_interview_past_midnight_ends_next_day(self, _):
        interview = make_interview(self.user, start=time(23, 30), end=time(0, 45))
        self.assertEqual(interview.duration_minutes, 75)
        self.assertTrue(interview.ends_next_day)

    def test_valid_slot(self, _):
        self.check(TODAY, time(9, 0), time(10, 0))

    def test_same_start_and_end(self, _):
        self.assertInvalid(TODAY, time(9, 0), time(9, 0), field="end_time")

    def test_longer_than_twelve_hours(self, _):
        # 10:00 -> 09:00 would be 23 hours, almost certainly a typo.
        self.assertInvalid(TODAY, time(10, 0), time(9, 0), field="end_time")

    def test_future_dates_are_rejected(self, _):
        self.check(date(2026, 9, 29), time(9, 0), time(10, 0))  # one day of time-zone slack
        self.assertInvalid(date(2026, 9, 30), time(9, 0), time(10, 0), field="date")

    def test_ancient_dates_are_rejected(self, _):
        self.assertInvalid(date(1999, 1, 1), time(9, 0), time(10, 0), field="date")

    def test_overlap_is_rejected(self, _):
        make_interview(self.user, day=TODAY, start=time(9, 0), end=time(10, 0))
        self.assertInvalid(TODAY, time(9, 30), time(11, 0))
        self.assertInvalid(TODAY, time(8, 0), time(12, 0))

    def test_back_to_back_is_fine(self, _):
        make_interview(self.user, day=TODAY, start=time(9, 0), end=time(10, 0))
        self.check(TODAY, time(10, 0), time(11, 0))
        self.check(TODAY, time(8, 0), time(9, 0))

    def test_overlap_across_midnight(self, _):
        make_interview(self.user, day=date(2026, 9, 26), start=time(23, 0), end=time(1, 0))
        self.assertInvalid(date(2026, 9, 27), time(0, 30), time(1, 30))
        self.check(date(2026, 9, 27), time(1, 0), time(2, 0))

    def test_other_members_do_not_overlap(self, _):
        make_interview(make_user("sam"), day=TODAY, start=time(9, 0), end=time(10, 0))
        self.check(TODAY, time(9, 0), time(10, 0))

    def test_editing_ignores_itself(self, _):
        interview = make_interview(self.user, day=TODAY, start=time(9, 0), end=time(10, 0))
        self.check(TODAY, time(9, 0), time(10, 30), exclude_pk=interview.pk)


class EntryKindTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_kinds(self):
        self.assertEqual(make_interview(self.user).kind, "interview")
        self.assertEqual(make_work(self.user, day=date(2026, 9, 22)).kind, "work")
        bids = make_bids(self.user, bids=40)
        self.assertEqual((bids.kind, bids.duration_minutes, bids.rate_unit), ("bids", 0, "bid"))
        self.assertEqual(bids.description, "40 bids")

    def test_an_entry_has_times_or_bids_but_not_both(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Interview.objects.create(user=self.user, date=TODAY)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Interview.objects.create(user=self.user, date=TODAY, bids=5, start_time=time(9, 0), end_time=time(10, 0))

    def test_one_bid_entry_per_member_per_day(self):
        make_bids(self.user, day=TODAY)
        make_bids(make_user("other"), day=TODAY)  # other members are fine
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_bids(self.user, day=TODAY)

    @mock.patch("tracker.models.timezone.localdate", return_value=TODAY)
    def test_bid_entries_do_not_block_interview_times(self, _):
        make_bids(self.user, day=TODAY)
        validate_time_slot(user_id=self.user.pk, day=TODAY, start=time(9, 0), end=time(10, 0))
