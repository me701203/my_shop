import os

from celery import Celery
from celery.schedules import crontab

# set the default Django settings module for the 'celery' program.
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myshop.settings")

# Use production settings for Celery
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myshop.settings.prod")

app = Celery("myshop")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
