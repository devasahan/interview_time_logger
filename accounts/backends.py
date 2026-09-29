from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """Lets people sign in with either their username or their email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)
        if not username or password is None:
            return None

        user = self._find_user(user_model, username.strip())
        if user is None:
            # Hash anyway so a missing account takes as long as a wrong password.
            user_model().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    @staticmethod
    def _find_user(user_model, identifier):
        manager = user_model._default_manager
        try:
            return manager.get(username=identifier)
        except user_model.DoesNotExist:
            pass
        lookup = "email__iexact" if "@" in identifier else "username__iexact"
        matches = list(manager.filter(**{lookup: identifier})[:2])
        # An ambiguous match (e.g. two accounts sharing an email) never signs in.
        return matches[0] if len(matches) == 1 else None
