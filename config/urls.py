from django.contrib import admin
from django.urls import include, path

from tracker.views import healthz

admin.site.site_header = "Interview Time Logger admin"
admin.site.site_title = "Interview Time Logger admin"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("healthz/", healthz, name="healthz"),
    path("", include("tracker.urls")),
]
