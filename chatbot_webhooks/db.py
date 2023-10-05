# -*- coding: utf-8 -*-
from chatbot_webhooks import config

TORTOISE_ORM = {
    "connections": {"default": config.DATABASE_URL},
    "apps": {
        "chatbot_webhooks": {
            "models": [
                "aerich.models",
                "chatbot_webhooks.models",
            ],
            "default_connection": "default",
        },
    },
}
