"""
Django settings for Interview Time Logger.

Every deployment-specific value is read from environment variables. For local
development, copy ``.env.example`` to ``.env`` and adjust it.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "django-insecure-local-development-only"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. For local development copy .env.example "
            "to .env; in production set DJANGO_SECRET_KEY in your hosting environment."
        )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Hostnames that popular hosting platforms expose automatically.
for platform_host_var in ("RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PUBLIC_DOMAIN"):
    platform_host = os.environ.get(platform_host_var, "").strip()
    if platform_host:
        ALLOWED_HOSTS.append(platform_host)
        CSRF_TRUSTED_ORIGINS.append(f"https://{platform_host}")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tracker.context_processors.app",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database: SQLite locally, anything dj-database-url understands (e.g. Postgres)
# when DATABASE_URL is set.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {
    "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True),
}


# Authentication
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.UsernameOrEmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "tracker:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# Static files (served by WhiteNoise in production)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG or TESTING
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
# Tests run without collectstatic; don't let WhiteNoise warn about the missing folder.
WHITENOISE_AUTOREFRESH = DEBUG or TESTING

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# App settings
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "$")

# First day of the pay week: 0 = Monday ... 6 = Sunday. Pick it before the
# first payout; existing payouts keep the dates they were created with.
WEEK_START_DAY = int(os.environ.get("WEEK_START_DAY", "0"))
if not 0 <= WEEK_START_DAY <= 6:
    raise ImproperlyConfigured("WEEK_START_DAY must be between 0 (Monday) and 6 (Sunday).")


# HTTPS hardening. On by default in production; hosting platforms terminate TLS
# at a proxy that sets X-Forwarded-Proto.
USE_HTTPS = env_bool("DJANGO_USE_HTTPS", default=not DEBUG and not TESTING)
if USE_HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", default=True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))


# Log to stdout/stderr so errors show up in the hosting platform's logs.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "ERROR" if TESTING else os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
