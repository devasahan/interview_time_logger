from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import HourlyRate, Interview, InterviewType, Payout, validate_time_slot


@admin.register(InterviewType)
class InterviewTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)


@admin.register(HourlyRate)
class HourlyRateAdmin(admin.ModelAdmin):
    list_display = ("user", "rate", "effective_from", "set_by", "created_at")
    list_filter = ("user",)
    readonly_fields = ("set_by", "created_at")


class InterviewAdminForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        user, day = cleaned.get("user"), cleaned.get("date")
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if None not in (user, day, start, end):
            try:
                validate_time_slot(user_id=user.pk, day=day, start=start, end=end, exclude_pk=self.instance.pk)
            except ValidationError as error:
                self.add_error(None, error)
        return cleaned


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    form = InterviewAdminForm
    list_display = ("date", "user", "start_time", "end_time", "duration_minutes", "bids", "interview_with", "role", "interview_type", "payout")
    list_filter = ("interview_type", ("payout", admin.EmptyFieldListFilter), "user")
    list_select_related = ("user", "interview_type", "payout")
    search_fields = ("interview_with", "role", "notes", "user__username", "user__first_name", "user__last_name")
    date_hierarchy = "date"
    readonly_fields = ("duration_minutes", "payout", "paid_rate", "paid_amount", "created_at", "updated_at")


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    """Read-only: record and undo payments from the Payroll page so work entries stay in sync."""

    list_display = ("paid_at", "user", "period_start", "period_end", "interview_count", "total_minutes", "total_bids", "amount", "paid_by")
    list_filter = ("user",)
    list_select_related = ("user", "paid_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
