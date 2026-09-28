from django.urls import path, register_converter

from . import manage_views, views
from .converters import IsoDateConverter

register_converter(IsoDateConverter, "isodate")

app_name = "tracker"

urlpatterns = [
    # Team members
    path("", views.home, name="home"),
    path("interviews/", views.history, name="history"),
    path("interviews/new/", views.interview_create, name="interview_create"),
    path("interviews/<int:pk>/edit/", views.interview_edit, name="interview_edit"),
    path("interviews/<int:pk>/delete/", views.interview_delete, name="interview_delete"),
    path("payments/", views.payments, name="payments"),
    # Admin
    path("manage/", manage_views.overview, name="manage_overview"),
    path("manage/interviews/", manage_views.interviews, name="manage_interviews"),
    path("manage/team/", manage_views.team, name="manage_team"),
    path("manage/team/<int:pk>/", manage_views.member_detail, name="manage_member"),
    path("manage/team/<int:pk>/active/", manage_views.member_toggle_active, name="manage_member_active"),
    path(
        "manage/team/<int:pk>/rates/<int:rate_pk>/delete/",
        manage_views.member_delete_rate,
        name="manage_member_rate_delete",
    ),
    path("manage/payroll/", manage_views.payroll, name="manage_payroll"),
    path("manage/payroll/<isodate:start>/", manage_views.payroll_week, name="manage_payroll_week"),
    path("manage/payroll/<isodate:start>/pay/", manage_views.payroll_pay, name="manage_payroll_pay"),
    path("manage/payouts/<int:pk>/undo/", manage_views.payout_undo, name="manage_payout_undo"),
    path("manage/types/", manage_views.interview_types, name="manage_types"),
    path("manage/types/<int:pk>/", manage_views.interview_type_edit, name="manage_type_edit"),
]
