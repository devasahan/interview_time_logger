from django.conf import settings
from django.contrib.auth import get_user_model


def app(request):
    context = {"site_name": "Interview Time Logger", "currency_symbol": settings.CURRENCY_SYMBOL}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        context["pending_approvals"] = get_user_model().objects.filter(
            is_active=True, is_staff=False, is_approved=False
        ).count()
    return context
