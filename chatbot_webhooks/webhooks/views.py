# -*- coding: utf-8 -*-
from django.http import HttpRequest, HttpResponse

from chatbot_webhooks.webhooks.utils import authentication_required


@authentication_required
def hello_authenticated(request: HttpRequest) -> HttpResponse:
    return HttpResponse("Hello, authenticated user!")


def hello_unauthenticated(request: HttpRequest) -> HttpResponse:
    return HttpResponse("Hello, unauthenticated user!")
