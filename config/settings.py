"""
Django settings for MaderLunch.

Bewusst eine Datei statt split-settings — bei der App-Größe einfacher zu lesen.
Alle Werte, die zwischen Umgebungen variieren, kommen aus ENV.

AUTH-PATCH 2026-05: django-allauth + Microsoft/Entra-Provider integriert.
Suchstring '# AUTH-PATCH' findet alle ergänzten Stellen.
"""
from pathlib import Path

from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent


# ─── Core ───────────────────────────────────────────────────────
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Hinter Forti-VIP (TLS-Offload)
BEHIND_TLS_PROXY = config("DJANGO_BEHIND_TLS_PROXY", default=False, cast=bool)
if BEHIND_TLS_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

# AUTH-PATCH: CSRF-Trusted-Origins für die öffentliche URL
CSRF_TRUSTED_ORIGINS = config(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default="",
    cast=Csv(),
)

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS erst aktivieren, wenn TLS sicher und stabil ist:
    # SECURE_HSTS_SECONDS = 31536000
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"


# ─── Apps ───────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",

    # AUTH-PATCH: allauth Voraussetzungen
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.microsoft",

    # MaderLunch-Apps
    "accounts",
    "lunch",
    "billing",
    "audit",
]

SITE_ID = 1  # AUTH-PATCH: für allauth Pflicht


# ─── Middleware ─────────────────────────────────────────────────

MIDDLEWARE = [
    "accounts.middleware_force_https.ForceHttpsForKnownHostsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "accounts.middleware_restrict_local_login.RestrictLocalLoginMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",

    # AUTH-PATCH: allauth Middleware
    "allauth.account.middleware.AccountMiddleware",
]

# ─── URLs / Templates / WSGI ────────────────────────────────────
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


# ─── Database ───────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="maderlunch"),
        "USER": config("POSTGRES_USER", default="maderlunch"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}


# ─── Auth ───────────────────────────────────────────────────────
# AUTH-PATCH: zwei Backends parallel — lokal + allauth (Entra)
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"


# ─── allauth Konfiguration (AUTH-PATCH) ─────────────────────────
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["username*", "email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"  # User werden von Managern/IT angelegt
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = False
ACCOUNT_PREVENT_ENUMERATION = True

ACCOUNT_ADAPTER = "accounts.adapters.MaderAccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.MaderEntraSocialAdapter"

SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_STORE_TOKENS = False

# Microsoft / Entra Provider — Single-Tenant
SOCIALACCOUNT_PROVIDERS = {
    "microsoft": {
        "APPS": [
            {
                "client_id": config("ENTRA_CLIENT_ID"),
                "secret": config("ENTRA_CLIENT_SECRET"),
                "settings": {
                    "tenant": config("ENTRA_TENANT_ID"),
                },
            },
        ],
    "SCOPE": ["User.Read", "GroupMember.Read.All", "openid", "profile", "email"],
        "AUTH_PARAMS": {
            "prompt": "select_account",
        },
    },
}

# ─── Login-Härtung ──────────────────────────────────────────────
# Lokaler Login (Username/Passwort) ist nur aus diesen Subnetzen erreichbar.
# Alle anderen Source-IPs werden auf den Microsoft-Login umgeleitet.
# Funktioniert nur, wenn die Middleware RestrictLocalLoginMiddleware aktiv ist.

LOCAL_LOGIN_ALLOWED_NETWORKS = [
    "10.75.0.0/21",   # Server-Admin-Workstations (MALE-SRVMGMT)
    "127.0.0.0/8",    # Container-internal (Health-Checks, etc.)
]

# ─── Internationalization ───────────────────────────────────────
LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True


# ─── Static / Media ─────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─── Logging — Auth-Adapter loggt auf DEBUG ─────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "concise": {"format": "{asctime} {levelname:7s} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "concise"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "accounts.adapters": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "allauth": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

FORCE_SCHEME_HTTPS_FOR_HOSTS = [
    "lunch.mader.eu",
]
