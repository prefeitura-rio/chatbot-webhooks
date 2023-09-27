# -*- coding: utf-8 -*-
import json
from typing import Any, Dict, List, Tuple, Union
from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from loguru import logger
from twilio.twiml.messaging_response import MessagingResponse

from chatbot_webhooks.webhooks import tags
from chatbot_webhooks.webhooks.middleware import detect_intent_text
from chatbot_webhooks.webhooks.utils import authentication_required


@csrf_exempt
# @authentication_required
def input_twilio(request: HttpRequest) -> HttpResponse:
    """
    Handles input messages from Twilio
    """
    request_id = uuid4()
    logger.info(f"Request ID: {request_id}")

    try:
        logger.info(f"{request_id} - Request body: {request.body}")
    except Exception:  # noqa
        pass

    message = request.POST.get("Body", "")
    phone = request.POST.get("From", "")
    logger.info(f"{request_id} - Received message '{message}' from user '{phone}'")

    # Get the answer from Dialogflow CX
    try:
        answer_messages: List[str] = detect_intent_text(
            text=message,
            session_id=phone,
            project_id="rj-chatbot-dev",
            location_id="global",
            agent_id="e0ea81dd-fce0-4385-8555-30aefb3c29bc",
            environment_id=None,
        )
        logger.info(f"{request_id} - Answers: {answer_messages}")
    except Exception as exc:  # noqa
        logger.exception(f"{request_id} - An error occurred: {exc}")
        raise exc

    # Return the answer
    response = MessagingResponse()
    response.message("\n".join(answer_messages))
    return HttpResponse(content=str(response), status=200)


@csrf_exempt
@authentication_required
def input_ascsac(request: HttpRequest) -> HttpResponse:
    """
    Handles input messages from ASCSAC
    """
    request_id = uuid4()
    logger.info(f"Request ID: {request_id}")

    try:
        logger.info(f"{request_id} - Request body: {request.body}")
    except Exception:  # noqa
        pass

    # Get the request body as JSON
    try:
        body: str = request.body.decode("utf-8")
        body: str = body.replace("\n", " ")
        body: dict = json.loads(body)
    except Exception:  # noqa
        logger.error(f"Request {request_id} body is not valid JSON")
        return HttpResponse(content="Invalid request body", status=400)

    # Get the incoming message from the request body
    try:
        message: str = body["message"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a message")
        return HttpResponse(content="Malformed request", status=400)

    # Get user info from the request body
    try:
        cpf = None
        if "cpf" in body:
            cpf: str = body["cpf"]
        email = None
        if "email" in body:
            email: str = body["email"]
        phone = None
        if "phone" in body:
            phone: str = body["phone"]
        protocol = None
        if "protocol" in body:
            protocol: str = body["protocol"]
        session_id = ""
        if protocol:
            session_id = f"protocol-{protocol}"
        elif phone:
            session_id = f"phone-{phone}"
        elif cpf:
            session_id = f"cpf-{cpf}"
        elif email:
            session_id = f"email-{email}"
    except Exception:  # noqa
        logger.exception(f"Request {request_id} body does not contain user info")
        return HttpResponse(content="Malformed request", status=400)

    logger.info(f"{request_id} - Received message '{message}' from user '{session_id}'")
    if session_id == "":
        session_id = str(uuid4())
        logger.warning(
            f"{request_id} - Session ID not found. Using random UUID: {session_id}"
        )

    # Get the answer from Dialogflow CX
    try:
        answer_messages: List[str] = detect_intent_text(
            text=message, session_id=session_id, parameters={"phone": phone}
        )
        logger.info(f"{request_id} - Answers: {answer_messages}")
    except Exception as exc:  # noqa
        logger.exception(f"{request_id} - An error occurred: {exc}")
        raise exc

    # Check if there are options to be presented to the user as buttons
    buttons = []
    new_answer_messages = []
    for answer_message in answer_messages:
        if answer_message.startswith(settings.SIGNATURE_BUTTONS_MESSAGE):
            # Crop the signature
            answer_message = answer_message[len(settings.SIGNATURE_BUTTONS_MESSAGE) :]
            # Get the buttons
            buttons = [option.strip() for option in answer_message.split(",")]
        else:
            new_answer_messages.append(answer_message)
    answer_messages = new_answer_messages

    # Return the answer
    return HttpResponse(
        content=json.dumps({"answer_messages": answer_messages, "buttons": buttons}),
        status=200,
    )


@csrf_exempt
@authentication_required
def input_telegram(request: HttpRequest) -> HttpResponse:
    """
    Handles input messages from Telegram
    """
    request_id = uuid4()
    logger.info(f"Request ID: {request_id}")

    try:
        logger.info(f"{request_id} - Request body: {request.body}")
    except Exception:  # noqa
        pass

    # Get the request body as JSON
    try:
        body: str = request.body.decode("utf-8")
        body: str = body.replace("\n", " ")
        body: dict = json.loads(body)
    except Exception:  # noqa
        logger.error(f"Request {request_id} body is not valid JSON")
        return HttpResponse(content="Invalid request body", status=400)

    # Get the incoming message from the request body
    try:
        message: str = body["message"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a message")
        return HttpResponse(content="Malformed request", status=400)

    # Get session ID from the request body
    try:
        session_id: str = body["session_id"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a session ID")
        return HttpResponse(content="Malformed request", status=400)

    # Get the answer from Dialogflow CX
    try:
        answer_messages: List[str] = detect_intent_text(
            text=message, session_id=session_id
        )
    except Exception as exc:  # noqa
        logger.exception(f"{request_id} - An error occurred: {exc}")
        raise exc

    # Return the answer
    logger.info(f"{request_id} - Answers: {answer_messages}")
    return HttpResponse(
        content=json.dumps({"answer_messages": answer_messages}), status=200
    )


@csrf_exempt
@authentication_required
def webhook(request: HttpRequest) -> HttpResponse:
    """
    Handles the webhook requests from Dialogflow CX
    """
    request_id = uuid4()
    logger.info(f"Request ID: {request_id}")

    # Get the request body as JSON
    try:
        body: str = request.body.decode("utf-8")
        body: dict = json.loads(body)
    except Exception:  # noqa
        logger.error(f"Request {request_id} body is not valid JSON")
        return HttpResponse(content="Invalid request body", status=400)

    # Get the tag from the request body
    try:
        tag: str = body["fulfillmentInfo"]["tag"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a tag")
        return HttpResponse(content="Malformed request", status=400)

    # See if we can find a webhook for this tag
    logger.info(f"{request_id} - Tag: {tag}. Calling webhook function")
    webhook_func = getattr(tags, tag, None)
    if webhook_func is None or not callable(webhook_func):
        logger.error(f"{request_id} - Tag '{tag}' is not implemented")
        return HttpResponse(content="Tag is invalid", status=400)

    # Call the webhook function
    try:
        response: Union[str, Tuple[str, Dict[str, Any]]] = webhook_func(body)
    except Exception as exc:  # noqa
        logger.exception(f"{request_id} - An error occurred: {exc}")
        raise exc

    logger.info(f"{request_id} - Webhook response: {response}")
    if isinstance(response, str):
        response_text = response
        session_parameters = {}
    elif isinstance(response, tuple):
        response_text = response[0]
        session_parameters = response[1]
        try:
            form_parameters = response[2]
        except:  # noqa
            form_parameters = []
        if not isinstance(session_parameters, dict):
            # Raise malformed request
            logger.error(f"{request_id} - Webhook response is invalid.")
            return HttpResponse(content="Webhook response is invalid.", status=400)
    else:
        # Raise malformed request
        logger.error(f"{request_id} - Webhook response is invalid.")
        return HttpResponse(content="Webhook response is invalid.", status=400)

    # Ref: https://cloud.google.com/dialogflow/cx/docs/reference/rest/v3/WebhookResponse
    # Build response
    if form_parameters:
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
                    "pageInfo": {
                        "formInfo": {
                            "parameterInfo": form_parameters,
                        }
                    },
                    "sessionInfo": {
                        "parameters": session_parameters,
                    },
                    "payload": {"telephony": {"caller_id": "+18558363987"}},
                }
            )
        )
    else:
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
            )
        )
