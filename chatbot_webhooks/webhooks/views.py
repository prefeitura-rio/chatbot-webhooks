# -*- coding: utf-8 -*-
import json
from typing import Any, Dict, Tuple, Union
from uuid import uuid4

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from loguru import logger

from chatbot_webhooks.webhooks import tags
from chatbot_webhooks.webhooks.middleware import detect_intent_text
from chatbot_webhooks.webhooks.utils import authentication_required


@csrf_exempt
@authentication_required
def input_ascsac(request: HttpRequest) -> HttpResponse:
    """
    Handles input messages from ASCSAC
    """
    # Get the request body as JSON
    try:
        body: str = request.body.decode("utf-8")
        body: dict = json.loads(body)
    except Exception:  # noqa
        return HttpResponse(content="Invalid request body", status=400)

    # Get the incoming message from the request body
    try:
        message: str = body["message"]
    except Exception:  # noqa
        return HttpResponse(content="Malformed request", status=400)

    # Get user info from the request body
    try:
        cpf: str = body["cpf"]
        email: str = body["email"]
        phone: str = body["phone"]
        session_id = ""
        if phone:
            session_id = phone
        elif cpf:
            session_id = cpf
        elif email:
            session_id = email
    except Exception:  # noqa
        return HttpResponse(content="Malformed request", status=400)

    if session_id == "":
        session_id = str(uuid4())
        logger.warning(f"Session ID not found. Using random UUID: {session_id}")

    # Get the answer from Dialogflow CX
    try:
        answer: str = detect_intent_text(text=message, session_id=session_id)
    except Exception as exc:  # noqa
        logger.exception(exc)
        return HttpResponse(content="An error occurred", status=500)

    # Return the answer
    return HttpResponse(content=json.dumps({"answer": answer}), status=200)


@csrf_exempt
@authentication_required
def input_telegram(request: HttpRequest) -> HttpResponse:
    """
    Handles input messages from Telegram
    """
    # Get the request body as JSON
    try:
        body: str = request.body.decode("utf-8")
        body: dict = json.loads(body)
    except Exception:  # noqa
        return HttpResponse(content="Invalid request body", status=400)

    # Get the incoming message from the request body
    try:
        message: str = body["message"]
    except Exception:  # noqa
        return HttpResponse(content="Malformed request", status=400)

    # Get session ID from the request body
    try:
        session_id: str = body["session_id"]
    except Exception:  # noqa
        return HttpResponse(content="Malformed request", status=400)

    # Get the answer from Dialogflow CX
    try:
        answer: str = detect_intent_text(text=message, session_id=session_id)
    except Exception as exc:  # noqa
        logger.exception(exc)
        return HttpResponse(content="An error occurred", status=500)

    # Return the answer
    return HttpResponse(content=json.dumps({"answer": answer}), status=200)


@csrf_exempt
@authentication_required
def webhook(request: HttpRequest) -> HttpResponse:
    """
    Handles the webhook requests from Dialogflow CX
    """
    # Get the request body as JSON
    try:
        body: str = request.body.decode("utf-8")
        body: dict = json.loads(body)
    except Exception:  # noqa
        return HttpResponse(content="Invalid request body", status=400)

    # Get the tag from the request body
    try:
        tag: str = body["fulfillmentInfo"]["tag"]
    except Exception:  # noqa
        return HttpResponse(content="Malformed request", status=400)

    # See if we can find a webhook for this tag
    webhook_func = getattr(tags, tag, None)
    if webhook_func is None or not callable(webhook_func):
        logger.error(f"Tag '{tag}' is not implemented")
        return HttpResponse(content="Tag is invalid", status=400)

    # Call the webhook function
    try:
        response: Union[str, Tuple[str, Dict[str, Any]]] = webhook_func(body)
    except Exception as exc:  # noqa
        logger.exception(exc)
        return HttpResponse(content="An error occurred", status=500)

    # Parse response and return it
    if isinstance(response, str):
        response_text = response
        session_parameters = {}
    elif isinstance(response, tuple):
        response_text = response[0]
        session_parameters = response[1]
        if not isinstance(session_parameters, dict):
            # Raise malformed request
            return HttpResponse(content="Webhook response is invalid.", status=400)
    else:
        # Raise malformed request
        return HttpResponse(content="Webhook response is invalid.", status=400)

    # Ref: https://cloud.google.com/dialogflow/cx/docs/reference/rest/v3/WebhookResponse
    # Build response
    return HttpResponse(
        content=json.dumps(
            {
                "fulfillmentResponse": {
                    "messages": [
                        {
                            "text": {
                                "text": [
                                    response_text,
                                ]
                            }
                        }
                    ]
                },
                "sessionInfo": {
                    "parameters": session_parameters,
                },
                "payload": {"telephony": {"caller_id": "+18558363987"}},
            }
        ),
        status=200,
        content_type="application/json",
    )
