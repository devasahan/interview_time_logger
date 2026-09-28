import os
from io import StringIO
from unittest import mock

from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
PASSWORD = "a-strong-test-password-42"


class SignUpTests(TestCase):
    def signup(self, **overrides):
        data = {
            "first_name": "Jane",
            "last_name": "Doe",
            "username": "jane",
            "email": "jane@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return self.client.post(reverse("accounts:signup"), data)

    def test_sign_up_creates_a_pending_account_and_logs_in(self):
        response = self.signup()
        self.assertRedirects(response, reverse("tracker:home"))
        user = User.objects.get(username="jane")
        self.assertFalse(user.is_approved)
        self.assertFalse(user.is_staff)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_email_must_be_unique(self):
        User.objects.create_user("existing", "Jane@Example.com", PASSWORD)
        response = self.signup()
        self.assertContains(response, "An account with this email already exists.")

    def test_username_must_be_unique_ignoring_case(self):
        User.objects.create_user("Jane", "other@example.com", PASSWORD)
        self.signup()
        self.assertFalse(User.objects.filter(username="jane").exists())


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("jane", "jane@example.com", PASSWORD)

    def test_login_with_username_or_email(self):
        self.assertEqual(authenticate(username="jane", password=PASSWORD), self.user)
        self.assertEqual(authenticate(username="JANE@example.com", password=PASSWORD), self.user)

    def test_wrong_password(self):
        self.assertIsNone(authenticate(username="jane", password="nope"))
        self.assertIsNone(authenticate(username="nobody", password=PASSWORD))

    def test_ambiguous_email_does_not_log_in(self):
        User.objects.create_user("jane2", "jane@example.com", PASSWORD)
        self.assertIsNone(authenticate(username="jane@example.com", password=PASSWORD))

    def test_deactivated_accounts_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(authenticate(username="jane", password=PASSWORD))


class EnsureAdminCommandTests(TestCase):
    def run_command(self, **env):
        with mock.patch.dict(os.environ, env, clear=False):
            call_command("ensure_admin", stdout=StringIO())

    def test_creates_the_admin_once(self):
        self.run_command(ADMIN_USERNAME="owner", ADMIN_PASSWORD=PASSWORD, ADMIN_EMAIL="owner@example.com")
        admin = User.objects.get(username="owner")
        self.assertTrue(admin.is_staff and admin.is_superuser and admin.check_password(PASSWORD))

        self.run_command(ADMIN_USERNAME="owner", ADMIN_PASSWORD="another-long-password-99")
        admin.refresh_from_db()
        self.assertTrue(admin.check_password(PASSWORD))  # never overwritten

    def test_skips_without_credentials(self):
        self.run_command(ADMIN_USERNAME="", ADMIN_PASSWORD="")
        self.assertFalse(User.objects.exists())

    def test_rejects_weak_passwords(self):
        with self.assertRaises(CommandError):
            self.run_command(ADMIN_USERNAME="owner", ADMIN_PASSWORD="12345")
        self.assertFalse(User.objects.exists())
