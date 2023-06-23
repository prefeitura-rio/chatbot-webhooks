# -*- coding: utf-8 -*-
"""
Django settings for chatbot_webhooks project.

Generated by 'django-admin startproject' using Django 4.2.2.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

from os import getenv
from pathlib import Path

from loguru import logger


def getenv_or_action(key: str, *, action: str = "raise"):
    value = getenv(key)
    if value is None:
        if action == "raise":
            raise ValueError(f"Environment variable {key} must be set")
        elif action == "warn":
            logger.warning(f"Environment variable {key} is not set")
        elif action == "ignore":
            pass
        else:
            raise ValueError(f"Unknown action {action}")
    return value


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_ROOT = BASE_DIR / "static"


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-u(*u+kkjq&j2)j_^n**!79dyzxj&(_lu)pouy5%r_+#e*rwzxu"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "chatbot_webhooks.webhooks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    # "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "chatbot_webhooks.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "chatbot_webhooks.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Google Cloud Platform
# DialogFlow
GCP_PROJECT_ID = getenv_or_action("GCP_PROJECT_ID", action="warn")
GCP_SERVICE_ACCOUNT = getenv_or_action("GCP_SERVICE_ACCOUNT", action="warn")
DIALOGFLOW_LOCATION_ID = getenv_or_action("DIALOGFLOW_LOCATION_ID", action="warn")
DIALOGFLOW_AGENT_ID = getenv_or_action("DIALOGFLOW_AGENT_ID", action="warn")
DIALOGFLOW_ENVIRONMENT_ID = getenv_or_action("DIALOGFLOW_ENVIRONMENT_ID", action="warn")
DIALOGFLOW_LANGUAGE_CODE = getenv_or_action("DIALOGFLOW_LANGUAGE_CODE", action="warn")
# Google Maps API
GMAPS_API_TOKEN = getenv_or_action("GMAPS_API_TOKEN", action="warn")

# ChatbotLab
CHATBOT_LAB_API_URL = getenv_or_action("CHATBOT_LAB_API_URL", action="warn")
CHATBOT_LAB_API_KEY = getenv_or_action("CHATBOT_LAB_API_KEY", action="warn")

# SGRC
SGRC_URL = getenv_or_action("SGRC_URL", action="warn")
SGRC_AUTHORIZATION_HEADER = getenv_or_action("SGRC_AUTHORIZATION_HEADER", action="warn")
SGRC_BODY_TOKEN = getenv_or_action("SGRC_BODY_TOKEN", action="warn")
