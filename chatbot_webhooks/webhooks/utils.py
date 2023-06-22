# -*- coding: utf-8 -*-
import base64
import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from google.oauth2 import service_account

from chatbot_webhooks.webhooks.models import Token


def authentication_required(view_func):
    """
    A decorator that checks whether the request is authenticated. It does so by checking the
    following conditions:
    - The request has an Authorization header with a Bearer token in it, the token is valid and
        the token is active.
    """

    def wrapper(request: HttpRequest, *args, **kwargs):
        # Check if the Authorization header is present
        if "Authorization" not in request.headers:
            return HttpResponse(status=401)
        # Check if the Authorization header has a Bearer token
        auth_header = request.headers["Authorization"]
        if not auth_header.startswith("Bearer "):
            return HttpResponse(status=401)
        # Check if the token is valid and active
        token = auth_header.split(" ")[1]
        try:
            token_obj = Token.objects.get(token=token)
        except Token.DoesNotExist:
            return HttpResponse(status=401)
        if not token_obj.is_active:
            return HttpResponse(status=401)
        # If all checks pass, call the view function
        return view_func(request, *args, **kwargs)

    return wrapper


def get_credentials_from_env() -> service_account.Credentials:
    """
    Gets credentials from env vars
    """
    info: dict = json.loads(base64.b64decode(settings.GCP_SERVICE_ACCOUNT))
    return service_account.Credentials.from_service_account_info(info)
