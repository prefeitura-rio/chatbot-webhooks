# -*- coding: utf-8 -*-
from os import getenv

from .base import *  # noqa
from .base import getenv_or_action


def get_admins():
    admins = getenv("ADMINS")
    if admins is None:
        return []
    return [admin.split(",") for admin in admins.split(";")]


DEBUG = False
SECRET_KEY = getenv_or_action("DJANGO_SECRET_KEY")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": getenv_or_action("DB_NAME"),
        "USER": getenv_or_action("DB_USER"),
        "PASSWORD": getenv_or_action("DB_PASSWORD"),
        "HOST": getenv_or_action("DB_HOST"),
        "PORT": getenv_or_action("DB_PORT"),
    }
}

# E-mail configuration
ADMINS = get_admins()
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_HOST_USER = getenv_or_action("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = getenv_or_action("EMAIL_HOST_PASSWORD")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = getenv_or_action("EMAIL_HOST_USER")
SERVER_EMAIL = getenv_or_action("EMAIL_HOST_USER")

# Google Cloud Platform
GCP_PROJECT_ID = getenv_or_action("GCP_PROJECT_ID")
GCP_SERVICE_ACCOUNT = getenv_or_action("GCP_SERVICE_ACCOUNT")
DIALOGFLOW_LOCATION_ID = getenv_or_action("DIALOGFLOW_LOCATION_ID")
DIALOGFLOW_AGENT_ID = getenv_or_action("DIALOGFLOW_AGENT_ID")
DIALOGFLOW_ENVIRONMENT_ID = getenv_or_action("DIALOGFLOW_ENVIRONMENT_ID")
DIALOGFLOW_LANGUAGE_CODE = getenv_or_action("DIALOGFLOW_LANGUAGE_CODE")
