"""Réglages de Copronome, lus dans l'environnement.

Une instance = une copropriété : rien de propre à une copropriété n'est
écrit ici. Les valeurs viennent des variables COPRONOME_* (voir
env.exemple). Sans COPRONOME_DEBUG=1, la clé secrète et les hôtes
autorisés sont obligatoires : l'app refuse de démarrer plutôt que de
tourner avec un défaut faible.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(nom, defaut=None):
    return os.environ.get(f"COPRONOME_{nom}", defaut)


def env_liste(nom):
    return [v.strip() for v in env(nom, "").split(",") if v.strip()]


DEBUG = env("DEBUG") == "1"

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("COPRONOME_SECRET_KEY est obligatoire hors mode debug")
    SECRET_KEY = "dev-seulement-jamais-en-production"  # noqa: S105 — debug seulement

ALLOWED_HOSTS = env_liste("ALLOWED_HOSTS")
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = env_liste("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "copro",
    "acces",
    "incidents",
    "documents",
    "echeances",
    "agenda",
    "audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "copronome.middleware.EnTetesSecurite",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "acces.middleware.SecondFacteurObligatoire",
]

ROOT_URLCONF = "copronome.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "copronome" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "copronome.navigation.menu",
            ],
        },
    },
]

WSGI_APPLICATION = "copronome.wsgi.application"

# Base : Postgres en production, SQLite pour le développement et les tests.
if env("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "copronome"),
            "USER": env("DB_USER", "copronome"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(env("DATA_DIR", BASE_DIR / "data")) / "copronome.sqlite3",
        }
    }

# Cache partagé entre processus : le rate limit d'allauth s'y appuie
# (le cache mémoire par défaut serait propre à chaque worker).
# Table créée par `manage.py createcachetable`.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_copronome"}
}

# IP du client pour le rate limit d'allauth : derrière Caddy, REMOTE_ADDR est
# celle du proxy (tous les clients partageraient une limite). Nombre de proxys
# de confiance devant l'app : 1 avec le compose.yaml fourni, 0 sans proxy.
ALLAUTH_TRUSTED_PROXY_COUNT = int(env("TRUSTED_PROXY_COUNT", "0"))

AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
LOGIN_URL = "/compte/login/"
LOGIN_REDIRECT_URL = "/"

# Comptes : connexion par mail, inscription libre fermée (invitations).
ACCOUNT_ADAPTER = "acces.adapter.AdaptateurCompte"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = False

# Second facteur : passkey proposée par défaut, TOTP en secours (ADR, § 6).
MFA_SUPPORTED_TYPES = ["webauthn", "totp", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = DEBUG

# Mails : console en debug, relais SMTP authentifié sinon.
DEFAULT_FROM_EMAIL = env("EMAIL_FROM", "copronome@localhost")
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_HOST = env("EMAIL_HOST", "")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", "")
    EMAIL_USE_TLS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "copronome" / "static"]
STATIC_ROOT = Path(env("STATIC_ROOT", BASE_DIR / "staticfiles"))
MEDIA_ROOT = Path(env("MEDIA_ROOT", BASE_DIR / "media"))
# Aucun MEDIA_URL : les fichiers ne sont servis que par la vue documents:telecharger.
DOCUMENT_TAILLE_MAX = int(env("DOCUMENT_TAILLE_MAX_MO", "20")) * 1024 * 1024
DOCUMENTS_QUOTA = int(env("DOCUMENTS_QUOTA_MO", "2048")) * 1024 * 1024

# Sessions bornées : 14 jours, cookie inaccessible au JavaScript.
SESSION_COOKIE_AGE = 14 * 24 * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if not DEBUG:
    # Derrière Caddy, qui termine le TLS et pose X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env("SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"masque_jetons": {"()": "copronome.journal.MasqueJetons"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "filters": ["masque_jetons"]}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

# HSTS preload : engage tout le domaine auprès des navigateurs et se défait
# mal ; décision laissée à chaque instance, hors du code.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
