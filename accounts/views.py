from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import LoginForm, SignUpForm


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class SignUpView(FormView):
    template_name = "accounts/signup.html"
    form_class = SignUpForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("tracker:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="accounts.backends.UsernameOrEmailBackend")
        messages.success(
            self.request,
            "Welcome aboard! An admin will approve your account and set your hourly "
            "rate, then you can start logging interviews.",
        )
        return redirect("tracker:home")


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("tracker:home")
    extra_context = {"nav": "password"}

    def form_valid(self, form):
        messages.success(self.request, "Your password was changed.")
        return super().form_valid(form)
