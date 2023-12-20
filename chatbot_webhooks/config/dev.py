# -*- coding: utf-8 -*-
from . import getenv_list_or_action, getenv_or_action
from .base import *  # noqa: F401, F403

# Database configuration
DATABASE_HOST = getenv_or_action("DATABASE_HOST", default="localhost")
DATABASE_PORT = getenv_or_action("DATABASE_PORT", default="5432")
DATABASE_USER = getenv_or_action("DATABASE_USER", default="postgres")
DATABASE_PASSWORD = getenv_or_action("DATABASE_PASSWORD", default="postgres")
DATABASE_NAME = getenv_or_action("DATABASE_NAME", default="postgres")

# CORS configuration
ALLOWED_ORIGINS = getenv_list_or_action("ALLOWED_ORIGINS", default=["*"])
ALLOWED_ORIGINS_REGEX = None
ALLOWED_METHODS = getenv_list_or_action("ALLOWED_METHODS", default=["*"])
ALLOWED_HEADERS = getenv_list_or_action("ALLOWED_HEADERS", default=["*"])
ALLOW_CREDENTIALS = getenv_or_action("ALLOW_CREDENTIALS", default="true").lower() == "true"

# Google Cloud Platform
# DialogFlow
GCP_PROJECT_ID = getenv_or_action("GCP_PROJECT_ID", action="warn")
GCP_SERVICE_ACCOUNT = getenv_or_action("GCP_SERVICE_ACCOUNT", action="warn")
DIALOGFLOW_LOCATION_ID = getenv_or_action("DIALOGFLOW_LOCATION_ID", action="warn")
DIALOGFLOW_AGENT_ID = getenv_or_action("DIALOGFLOW_AGENT_ID", action="warn")
DIALOGFLOW_ENVIRONMENT_ID = getenv_or_action("DIALOGFLOW_ENVIRONMENT_ID", action="warn")
DIALOGFLOW_LANGUAGE_CODE = getenv_or_action("DIALOGFLOW_LANGUAGE_CODE", action="warn")
SIGNATURE_BUTTONS_MESSAGE = "BUTTONOPTIONS:"
# Google Maps API
GMAPS_API_TOKEN = getenv_or_action("GMAPS_API_TOKEN", action="warn")

# ChatbotLab
CHATBOT_LAB_API_URL = getenv_or_action("CHATBOT_LAB_API_URL", action="warn")
CHATBOT_LAB_API_KEY = getenv_or_action("CHATBOT_LAB_API_KEY", action="warn")

# Chatbot Integrations
CHATBOT_INTEGRATIONS_URL = getenv_or_action("CHATBOT_INTEGRATIONS_URL", action="warn")
CHATBOT_INTEGRATIONS_KEY = getenv_or_action("CHATBOT_INTEGRATIONS_KEY", action="warn")
CHATBOT_PGM_ACCESS_KEY = getenv_or_action("CHATBOT_PGM_ACCESS_KEY", action="warn")
CHATBOT_PGM_API_URL = getenv_or_action("CHATBOT_PGM_API_URL", action="warn").rstrip("/")

# SGRC
SGRC_URL = getenv_or_action("SGRC_URL", action="warn")
SGRC_AUTHORIZATION_HEADER = getenv_or_action("SGRC_AUTHORIZATION_HEADER", action="warn")
SGRC_BODY_TOKEN = getenv_or_action("SGRC_BODY_TOKEN", action="warn")

# Discord
DISCORD_WEBHOOK_NEW_TICKET = getenv_or_action("DISCORD_WEBHOOK_NEW_TICKET", action="warn")
