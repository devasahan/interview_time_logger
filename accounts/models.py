from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A team member. Admins are users with ``is_staff``."""

    is_approved = models.BooleanField(
        default=False,
        help_text="Approved members can log interviews. New sign-ups wait for an admin.",
    )

    class Meta:
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def can_log_interviews(self):
        return self.is_active and (self.is_approved or self.is_staff)

    @property
    def status(self):
        if not self.is_active:
            return "deactivated"
        if self.is_staff:
            return "admin"
        if self.is_approved:
            return "active"
        return "pending"
