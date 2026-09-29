from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from tracker.views import healthz

admin.site.site_header = f"{settings.BRAND_NAME} admin"
admin.site.site_title = f"{settings.BRAND_NAME} admin"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("healthz/", healthz, name="healthz"),
    path("", include("tracker.urls")),
]
