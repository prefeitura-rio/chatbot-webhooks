# -*- coding: utf-8 -*-
import json
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from loguru import logger

from chatbot_webhooks import config
from chatbot_webhooks.dependencies import validate_token
from chatbot_webhooks.webhooks.middleware import detect_intent_text

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(validate_token)])


@router.post("/ascsac/")
async def input_ascsac(request: Request) -> Response:
    """Input from ASCSAC."""
    request_id = uuid4()
    logger.info(f"Request ID: {request_id}")

    try:
        body_bytes: bytes = await request.body()
        logger.info(f"{request_id} - Request body: {body_bytes}")
    except:  # noqa: E722
        pass

    # Get the request body as JSON
    try:
        body_str = body_bytes.decode("utf-8")
        body_str = body_str.replace("\n", " ")
        body = json.loads(body_str)
    except:  # noqa: E722
        logger.error(f"Request {request_id} body is not valid JSON")
        return Response(content="Invalid request body", status_code=400)

    # Get the incoming message from the request body
    try:
        message: str = body["message"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a message")
        return Response(content="Malformed request", status_code=400)

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
        return Response(content="Malformed request", status_code=400)

    logger.info(f"{request_id} - Received message '{message}' from user '{session_id}'")
    if session_id == "":
        session_id = str(uuid4())
        logger.warning(f"{request_id} - Session ID not found. Using random UUID: {session_id}")

    # Get the answer from Dialogflow CX
    try:
        answer_messages: List[str] = await detect_intent_text(
            text=message, session_id=session_id, parameters={"phone": phone}
        )
        logger.info(f"{request_id} - Answers: {answer_messages}")
        answer_messages = [
            segment
            for msg in answer_messages
            for segment in msg.split("SIGNATURE_TYPE_DIVISION_MESSAGE")
        ]
    except Exception as exc:  # noqa
        logger.exception(f"{request_id} - An error occurred: {exc}")
        raise exc

    # Check if there are options to be presented to the user as buttons
    buttons = []
    files = []
    new_answer_messages = []
    order = []
    for answer_message in answer_messages:
        if answer_message.startswith(config.SIGNATURE_BUTTONS_MESSAGE):
            # Crop the signature
            answer_message = answer_message[len(config.SIGNATURE_BUTTONS_MESSAGE) :]  # noqa: E203
            # Get the buttons
            buttons = [option.strip() for option in answer_message.split(",")]
            order.append("button")
        elif answer_message.startswith(config.SIGNATURE_FILE_MESSAGE):
            # Crop the signature
            answer_message = answer_message[
                len(config.SIGNATURE_FILE_MESSAGE) :  # noqa: E203
            ].strip()
            # Get the filename and file
            file_content = answer_message.split(":")[-1].strip()
            filename = ":".join(answer_message.split(":")[:-1]).strip()
            files.append({"filename": filename, "content": file_content})
            order.append("file")
        else:
            new_answer_messages.append(answer_message)
            order.append("text")
    answer_messages = new_answer_messages

    # Return the answer
    return Response(
        content=json.dumps(
            {"answer_messages": answer_messages, "buttons": buttons, "files": files, "order": order}
        ),
        status_code=200,
    )


@router.post("/telegram/")
async def input_telegram(request: Request) -> Response:
    """Input from Telegram."""
    request_id = uuid4()
    logger.info(f"Request ID: {request_id}")

    try:
        body_bytes: bytes = await request.body()
        logger.info(f"{request_id} - Request body: {body_bytes}")
    except:  # noqa: E722
        pass

    # Get the request body as JSON
    try:
        body_str = body_bytes.decode("utf-8")
        body_str = body_str.replace("\n", " ")
        body = json.loads(body_str)
    except:  # noqa: E722
        logger.error(f"Request {request_id} body is not valid JSON")
        return Response(content="Invalid request body", status_code=400)

    # Get the incoming message from the request body
    try:
        message: str = body["message"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a message")
        return Response(content="Malformed request", status_code=400)

    # Get session ID from the request body
    try:
        session_id: str = body["session_id"]
    except Exception:  # noqa
        logger.error(f"Request {request_id} body does not contain a session ID")
        return Response(content="Malformed request", status_code=400)

    # Get the answer from Dialogflow CX
    try:
        answer_messages: List[str] = await detect_intent_text(text=message, session_id=session_id)
    except Exception as exc:  # noqa
        logger.exception(f"{request_id} - An error occurred: {exc}")
        raise exc

    # Return the answer
    logger.info(f"{request_id} - Answers: {answer_messages}")
    return Response(content=json.dumps({"answer_messages": answer_messages}), status_code=200)
