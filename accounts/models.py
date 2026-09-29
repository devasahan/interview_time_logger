from django.contrib.auth.models import AbstractUser
from django.db import models


class TeamRole(models.TextChoices):
    INTERVIEWER = "interviewer", "Interviewer"
    DEVELOPER = "developer", "Developer"
    VIRTUAL_ASSISTANT = "virtual_assistant", "Virtual assistant"


class User(AbstractUser):
    """A team member. Admins are users with ``is_staff``."""

    is_approved = models.BooleanField(
        default=False,
        help_text="Approved members can log interviews. New sign-ups wait for an admin.",
    )
    team_role = models.CharField(
        "role",
        max_length=20,
        choices=TeamRole.choices,
        blank=True,
        help_text="What the member does on the team. The admin picks it when approving them.",
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
    def logs_bids(self):
        """Virtual assistants log how many bids they sent each day and are paid per bid."""
        return self.team_role == TeamRole.VIRTUAL_ASSISTANT

    @property
    def work_kind(self):
        """What this member logs: "bids", "work" (developers) or "interview" (everyone else)."""
        if self.logs_bids:
            return "bids"
        if self.team_role == TeamRole.DEVELOPER:
            return "work"
        return "interview"

    @property
    def rate_unit(self):
        return "bid" if self.logs_bids else "h"

    @property
    def status(self):
        if not self.is_active:
            return "deactivated"
        if self.is_staff:
            return "admin"
        if self.is_approved:
            return "active"
        return "pending"
