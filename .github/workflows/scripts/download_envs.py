# -*- coding: utf-8 -*-
import json
from os import getenv
from sys import argv

import hvac


def get_vault_client() -> hvac.Client:
    """
    Returns a Vault client.
    """
    return hvac.Client(
        url=getenv("VAULT_ADDRESS").strip(),
        token=getenv("VAULT_TOKEN").strip(),
    )


def get_vault_secret(secret_path: str, client: hvac.Client = None) -> dict:
    """
    Returns a secret from Vault.
    """
    vault_client = client or get_vault_client()
    return vault_client.secrets.kv.read_secret_version(secret_path)["data"]["data"]


if __name__ == "__main__":
    if len(argv) != 2:
        raise ValueError("Usage: download_envs.py <secret_path>")

    secret_path = argv[1]

    secret = get_vault_secret(secret_path)

    with open(".env.json", "w") as f:
        json.dump(secret, f)
