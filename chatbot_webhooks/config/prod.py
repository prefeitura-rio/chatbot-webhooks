# -*- coding: utf-8 -*-
from . import getenv_list_or_action, getenv_or_action
from .base import *  # noqa: F401, F403

# Database configuration
DATABASE_HOST = getenv_or_action("DATABASE_HOST", action="raise")
DATABASE_PORT = getenv_or_action("DATABASE_PORT", action="raise")
DATABASE_USER = getenv_or_action("DATABASE_USER", action="raise")
DATABASE_PASSWORD = getenv_or_action("DATABASE_PASSWORD", action="raise")
DATABASE_NAME = getenv_or_action("DATABASE_NAME", action="raise")

# CORS configuration
ALLOWED_ORIGINS = getenv_list_or_action("ALLOWED_ORIGINS", action="ignore")
ALLOWED_ORIGINS_REGEX = None
if not ALLOWED_ORIGINS and not ALLOWED_ORIGINS_REGEX:
    raise EnvironmentError("ALLOWED_ORIGINS or ALLOWED_ORIGINS_REGEX must be set.")
ALLOWED_METHODS = getenv_list_or_action("ALLOWED_METHODS", action="raise")
ALLOWED_HEADERS = getenv_list_or_action("ALLOWED_HEADERS", action="raise")
ALLOW_CREDENTIALS = getenv_or_action("ALLOW_CREDENTIALS", action="raise").lower() == "true"

# Sentry
SENTRY_ENABLE = True
SENTRY_DSN = getenv_or_action("SENTRY_DSN", action="raise")
SENTRY_ENVIRONMENT = getenv_or_action("SENTRY_ENVIRONMENT", action="raise")

# Google Cloud Platform
# DialogFlow
GCP_PROJECT_ID = getenv_or_action("GCP_PROJECT_ID")
GCP_SERVICE_ACCOUNT = getenv_or_action("GCP_SERVICE_ACCOUNT")
DIALOGFLOW_LOCATION_ID = getenv_or_action("DIALOGFLOW_LOCATION_ID")
DIALOGFLOW_AGENT_ID = getenv_or_action("DIALOGFLOW_AGENT_ID")
DIALOGFLOW_ENVIRONMENT_ID = getenv_or_action("DIALOGFLOW_ENVIRONMENT_ID")
DIALOGFLOW_LANGUAGE_CODE = getenv_or_action("DIALOGFLOW_LANGUAGE_CODE")
# Google Maps API
GMAPS_API_TOKEN = getenv_or_action("GMAPS_API_TOKEN")

# ChatbotLab
CHATBOT_LAB_API_URL = getenv_or_action("CHATBOT_LAB_API_URL")
CHATBOT_LAB_API_KEY = getenv_or_action("CHATBOT_LAB_API_KEY")

# Chatbot Integrations
CHATBOT_INTEGRATIONS_URL = getenv_or_action("CHATBOT_INTEGRATIONS_URL")
CHATBOT_INTEGRATIONS_KEY = getenv_or_action("CHATBOT_INTEGRATIONS_KEY")

# SGRC
SGRC_URL = getenv_or_action("SGRC_URL")
SGRC_AUTHORIZATION_HEADER = getenv_or_action("SGRC_AUTHORIZATION_HEADER")
SGRC_BODY_TOKEN = getenv_or_action("SGRC_BODY_TOKEN")

# Discord
DISCORD_WEBHOOK_NEW_TICKET = getenv_or_action("DISCORD_WEBHOOK_NEW_TICKET")
