"""Configuration PostgreSQL uniquement ; secrets et environnement explicites."""
import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from .database import database_settings
from .middleware import static_headers

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1" and ENVIRONMENT != "production"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise ImproperlyConfigured("Configurez DJANGO_SECRET_KEY (32 caractères minimum) dans .env.")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [v for v in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if v]
# Render fournit le nom exact du service ; aucune autorisation globale *.onrender.com.
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
if render_hostname:
    if len(render_hostname) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", render_hostname):
        raise ImproperlyConfigured("RENDER_EXTERNAL_HOSTNAME doit contenir un nom d’hôte sans protocole ni chemin.")
    ALLOWED_HOSTS.append(render_hostname)
    CSRF_TRUSTED_ORIGINS.append(f"https://{render_hostname}")
ALLOW_DEMO_DATA = os.environ.get("ALLOW_DEMO_DATA", "0") == "1" and ENVIRONMENT != "production"
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "erp", "connections", "billing",
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
    "config.middleware.PrivateResponseMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "erp.User"
DATABASES = {"default": database_settings(os.environ)}
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_ROOT = ROOT_DIR / "frontend" / "dist"
WHITENOISE_MAX_AGE = 31536000
WHITENOISE_ADD_HEADERS_FUNCTION = static_headers
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "erp.api.exception_handler",
    "COERCE_DECIMAL_TO_STRING": True,
}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = ENVIRONMENT == "production"
CSRF_COOKIE_SECURE = ENVIRONMENT == "production"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_FAILURE_VIEW = "config.views.csrf_failure"
SECURE_SSL_REDIRECT = ENVIRONMENT == "production"
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SECURE_HSTS_SECONDS = 31536000 if ENVIRONMENT == "production" else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = ENVIRONMENT == "production"
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Activer uniquement derrière un proxy privé qui écrase cet en-tête.
if os.environ.get("TRUST_HTTPS_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_048_576
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "WARNING"}}

# Les abonnements restent désactivés tant que l'opérateur n'a pas configuré
# son compte, ses prix et le webhook. Aucun tarif ni paiement réel par défaut.
BILLING_ENABLED = os.environ.get("BILLING_ENABLED", "0") == "1"
BILLING_PUBLIC_URL = os.environ.get("BILLING_PUBLIC_URL", "").rstrip("/")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_LIVE_MODE = os.environ.get("STRIPE_LIVE_MODE", "0") == "1"
STRIPE_API_VERSION = "2026-08-26.dahlia"
