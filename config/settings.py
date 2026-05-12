"""
Django settings for MaderLunch.

Bewusst eine Datei statt split-settings — bei der App-Größe einfacher zu lesen.
Alle Werte, die zwischen Umgebungen variieren, kommen aus ENV.
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
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS erst aktivieren, wenn TLS sicher und stabil ist:
    # SECURE_HSTS_SECONDS = 31536000
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True

CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

# ─── Apps ───────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "axes",
    "django_htmx",
    # "mozilla_django_oidc",  # erst aktivieren, wenn OIDC_ENABLED=True

    # Lokale Apps
    "accounts",
    "lunch",
    "billing",
    "audit",
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
    "django_htmx.middleware.HtmxMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware",
    "axes.middleware.AxesMiddleware",  # muss letzte Auth-Middleware sein
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ─── Templates ──────────────────────────────────────────────────
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

# ─── Datenbank ──────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

# ─── Auth ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    # "accounts.auth_backends.EntraOIDCBackend",  # aktivieren, wenn OIDC_ENABLED=True
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "lunch:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# ─── Sessions ───────────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8h

# ─── django-axes (Brute-Force-Schutz) ───────────────────────────
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # Stunden
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_ON_SUCCESS = True

# ─── i18n / l10n ────────────────────────────────────────────────
LANGUAGE_CODE = config("DJANGO_LANGUAGE_CODE", default="de-de")
TIME_ZONE = config("DJANGO_TIME_ZONE", default="Europe/Berlin")
USE_I18N = True
USE_TZ = True

# ─── Static / Media ─────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ─── OIDC (Phase 2) ─────────────────────────────────────────────
OIDC_ENABLED = config("OIDC_ENABLED", default=False, cast=bool)
if OIDC_ENABLED:
    OIDC_RP_CLIENT_ID = config("OIDC_RP_CLIENT_ID")
    OIDC_RP_CLIENT_SECRET = config("OIDC_RP_CLIENT_SECRET")
    OIDC_TENANT_ID = config("OIDC_TENANT_ID")
    OIDC_OP_AUTHORIZATION_ENDPOINT = (
        f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/oauth2/v2.0/authorize"
    )
    OIDC_OP_TOKEN_ENDPOINT = (
        f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/oauth2/v2.0/token"
    )
    OIDC_OP_USER_ENDPOINT = "https://graph.microsoft.com/oidc/userinfo"
    OIDC_OP_JWKS_ENDPOINT = (
        f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/discovery/v2.0/keys"
    )
    OIDC_RP_SIGN_ALGO = "RS256"
    OIDC_RP_SCOPES = "openid email profile"
    OIDC_USE_PKCE = True

# ─── Default PK ─────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Logging ────────────────────────────────────────────────────
LOG_LEVEL = config("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": '{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "axes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
