"""
Django settings for Vicinity.

The same file works in two places:
  - On your laptop: no environment variables needed. Uses SQLite and DEBUG mode.
  - On Render: set DATABASE_URL (PostgreSQL on Neon), DJANGO_SECRET_KEY, DJANGO_DEBUG=False,
    ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Read a local .env file if there is one (never committed to git)
load_dotenv(BASE_DIR / ".env")


# Reads a comma-separated environment variable into a list, e.g. "a.com,b.com"
def read_list_from_env(name, default):
    value = os.environ.get(name, default)
    result = []
    for item in value.split(","):
        item = item.strip()
        if item != "":
            result.append(item)
    return result


# ---- Security ------------------------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = read_list_from_env("ALLOWED_HOSTS", "localhost,127.0.0.1,.onrender.com")
CSRF_TRUSTED_ORIGINS = read_list_from_env("CSRF_TRUSTED_ORIGINS", "http://localhost:8000")

# Render (and most hosts) handle HTTPS in front of Django and tell us with this header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Django's default ("same-origin") sends no Referer to other sites. OpenStreetMap's tile servers
# require one and answer "Access blocked" without it, so send just our origin.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# ---- Apps and middleware -------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "areas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves CSS/JS in production
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---- Database ------------------------------------------------------------------------
# DATABASE_URL looks like: postgresql://user:password@host/dbname?sslmode=require
# Without it, a local SQLite file is used.

DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
        conn_max_age=600,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---- Login ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"


# ---- Language, time, static files ----------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# In production, WhiteNoise serves compressed files with a version hash in the name, so
# browsers can cache them forever. Locally and in tests, plain files are fine.
STATIC_BACKEND = "whitenoise.storage.CompressedManifestStaticFilesStorage"
if DEBUG or "test" in sys.argv:
    STATIC_BACKEND = "django.contrib.staticfiles.storage.StaticFilesStorage"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": STATIC_BACKEND},
}


# ---- REST API (Django REST Framework) ------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Scoring a new address calls free public map services, so it is rate limited
    "DEFAULT_THROTTLE_RATES": {
        "score": "20/hour",
        "suggest": "600/hour",
    },
}


# ---- Vicinity settings ---------------------------------------------------------------

# Identifies us to the free OpenStreetMap services (their usage policy asks for this)
VICINITY_USER_AGENT = os.environ.get(
    "VICINITY_USER_AGENT",
    "Vicinity/1.0 (neighbourhood livability score; https://github.com/stackvs18/vicinity)",
)

# How far a 15-minute walk reaches, in a straight line
VICINITY_RADIUS_METRES = 1200

# Re-use a computed area for this many days before fetching fresh map data
VICINITY_CACHE_DAYS = 30
