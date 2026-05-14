# myshop/settings_prod.py
"""
Production settings for myshop project.
Inherits from base settings.py and overrides security-critical settings.
"""

import environ
from pathlib import Path

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load production environment variables
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env.prod")  # ← Explicitly load .env.prod
from .settings import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

# SECURITY: Strong secret key from environment
SECRET_KEY = env("SECRET_KEY")

# SECURITY: Allowed hosts must be explicitly set in production
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# SECURITY: HTTPS enforcement
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)

# SECURITY: HTTP Strict Transport Security
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=True)

# SECURITY: Additional headers
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True  # No need for Django 4.0+
X_FRAME_OPTIONS = "DENY"

# SECURITY: Proxy headers (if behind nginx/load balancer)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Database connection pooling for production (optional but recommended)
DATABASES["default"]["CONN_MAX_AGE"] = 600

# Static files - ensure collectstatic has been run
STATIC_ROOT = BASE_DIR / "staticfiles"

# Logging for production
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "orders": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Email configuration for production
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="webshop@example.com")

# Cache - production Redis configuration
CACHES["default"]["LOCATION"] = env("REDIS_URL", default="redis://127.0.0.1:6379/1")

# Celery - production broker
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")

# Rate limiting configuration
RATELIMIT_VIEW = "shop.views.ratelimited_error"  # Optional custom handler
