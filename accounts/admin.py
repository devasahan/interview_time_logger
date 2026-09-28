from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (("Interview logger", {"fields": ("is_approved",)}),)
    list_display = ("username", "email", "first_name", "last_name", "is_approved", "is_staff", "is_active")
    list_filter = ("is_approved", "is_staff", "is_active")
