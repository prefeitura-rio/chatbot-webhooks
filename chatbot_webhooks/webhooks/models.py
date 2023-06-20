# -*- coding: utf-8 -*-
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import models


class Token(models.Model):
    token = models.UUIDField(default=uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return str(self.token)
