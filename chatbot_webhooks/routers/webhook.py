# -*- coding: utf-8 -*-
import json
from typing import Any, Dict, Tuple, Union
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from loguru import logger

from chatbot_webhooks.dependencies import validate_token
from chatbot_webhooks.webhooks import tags

router = APIRouter(prefix="/webhook", tags=["webhook"], dependencies=[Depends(validate_token)])


@router.post("/")
async def webhook(request: Request) -> Response:
    """
    Handles the webhook requests from Dialogflow CX
    """
    request_id = uuid4()
    logger.info(f"Request ID: {request_id}")

    # Get the request body as JSON
    try:
        body_bytes: bytes = await request.body()
        body_str: str = body_bytes.decode("utf-8")
        body: dict = json.loads(body_str)
    except Exception:  # noqa
        logger.error(f"Request {request_id} body is not valid JSON")
        return Response(content="Invalid request body", status_code=400)

    # Get the tag from the request body
    try:
        tag: str = body["fulfillmentInfo"]["tag"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a tag")
        return Response(content="Malformed request", status_code=400)

    # See if we can find a webhook for this tag
    logger.info(f"{request_id} - Tag: {tag}. Calling webhook function")
    webhook_func = getattr(tags, tag, None)
    if webhook_func is None or not callable(webhook_func):
        logger.error(f"{request_id} - Tag '{tag}' is not implemented")
        return Response(content="Tag is invalid", status_code=400)

    # Call the webhook function
    try:
        response: Union[str, Tuple[str, Dict[str, Any]]] = await webhook_func(body)
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
            return Response(content="Webhook response is invalid.", status_code=400)
    else:
        # Raise malformed request
        logger.error(f"{request_id} - Webhook response is invalid.")
        return Response(content="Webhook response is invalid.", status_code=400)

    # Ref: https://cloud.google.com/dialogflow/cx/docs/reference/rest/v3/WebhookResponse
    # Build response
    if form_parameters:
        return Response(
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
        return Response(
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
