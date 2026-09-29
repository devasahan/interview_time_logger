from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (("Interview logger", {"fields": ("is_approved", "team_role")}),)
    list_display = ("username", "email", "first_name", "last_name", "team_role", "is_approved", "is_staff", "is_active")
    list_filter = ("team_role", "is_approved", "is_staff", "is_active")
