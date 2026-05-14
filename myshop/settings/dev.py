"""
Development Settings
"""

from .base import *

DEBUG = True

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Development email backend (console)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable Sentry in development
SENTRY_DSN = None

# Simple logging for development
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
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "orders": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
