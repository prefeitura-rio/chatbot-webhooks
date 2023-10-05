# -*- coding: utf-8 -*-
from argparse import ArgumentParser
from uuid import uuid4

from tortoise import Tortoise, run_async

from chatbot_webhooks.db import TORTOISE_ORM
from chatbot_webhooks.models import User


async def run(username: str, token: str = None):
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()

    await User.create(
        username=username,
        is_active=True,
        token=token or uuid4(),
    )
    await Tortoise.close_connections()


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--username", type=str, required=True)
    parser.add_argument("--token", type=str, required=True)
    args = parser.parse_args()
    run_async(run(args.username, args.token))
