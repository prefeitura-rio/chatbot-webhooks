# -*- coding: utf-8 -*-
from chatbot_webhooks import config

TORTOISE_ORM = {
    "connections": {
        "default": {
            "engine": "tortoise.backends.asyncpg",
            "credentials": {
                "host": config.DATABASE_HOST,
                "port": config.DATABASE_PORT,
                "user": config.DATABASE_USER,
                "password": config.DATABASE_PASSWORD,
                "database": config.DATABASE_NAME,
            },
        },
    },
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
