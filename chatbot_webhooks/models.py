# -*- coding: utf-8 -*-
from tortoise import fields
from tortoise.models import Model


class User(Model):
    id = fields.BigIntField(pk=True)
    username = fields.CharField(max_length=100, unique=True)
    is_active = fields.BooleanField(default=True)
    token = fields.UUIDField()
    token_expiry = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return f"{self.username}"
