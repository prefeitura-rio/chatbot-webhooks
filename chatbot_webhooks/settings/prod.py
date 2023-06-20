# -*- coding: utf-8 -*-
from os import getenv

from .base import *  # noqa


def nonull_getenv(varname):
    value = getenv(varname)
    if value is None:
        raise ValueError(f"Environment variable {varname} must be set")
    return value


def get_admins():
    admins = getenv("ADMINS")
    if admins is None:
        return []
    return [admin.split(",") for admin in admins.split(";")]


DEBUG = False
SECRET_KEY = nonull_getenv("DJANGO_SECRET_KEY")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": nonull_getenv("DB_NAME"),
        "USER": nonull_getenv("DB_USER"),
        "PASSWORD": nonull_getenv("DB_PASSWORD"),
        "HOST": nonull_getenv("DB_HOST"),
        "PORT": nonull_getenv("DB_PORT"),
    }
}

ADMINS = get_admins()
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_HOST_USER = nonull_getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = nonull_getenv("EMAIL_HOST_PASSWORD")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = nonull_getenv("EMAIL_HOST_USER")
SERVER_EMAIL = nonull_getenv("EMAIL_HOST_USER")
