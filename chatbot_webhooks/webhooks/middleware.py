# -*- coding: utf-8 -*-
from typing import Any, Dict, List

from google.cloud import dialogflowcx_v3 as dialogflow

from chatbot_webhooks import config
from chatbot_webhooks.webhooks.utils import get_credentials_from_env


async def build_session_async_client(
    project_id: str = config.GCP_PROJECT_ID,
    location_id: str = config.DIALOGFLOW_LOCATION_ID,
    agent_id: str = config.DIALOGFLOW_AGENT_ID,
    environment_id: str = config.DIALOGFLOW_ENVIRONMENT_ID,
) -> dialogflow.SessionsAsyncClient:
    project = f"projects/{project_id}"
    location = f"locations/{location_id}"
    agent = f"agents/{agent_id}"
    if environment_id is not None:
        agent += f"/environments/{environment_id}"
    agent_path = f"{project}/{location}/{agent}"
    client_options = None
    agent_components = dialogflow.AgentsAsyncClient.parse_agent_path(agent_path)
    location_id = agent_components["location"]
    if location_id != "global":
        api_endpoint = f"{location_id}-dialogflow.googleapis.com:443"
        client_options = {"api_endpoint": api_endpoint}
    return dialogflow.SessionsAsyncClient(
        client_options=client_options, credentials=await get_credentials_from_env()
    )


async def detect_intent_text(
    text: str,
    session_id: str,
    project_id: str = config.GCP_PROJECT_ID,
    location_id: str = config.DIALOGFLOW_LOCATION_ID,
    agent_id: str = config.DIALOGFLOW_AGENT_ID,
    environment_id: str = config.DIALOGFLOW_ENVIRONMENT_ID,
    language_code: str = config.DIALOGFLOW_LANGUAGE_CODE,
    session_client: dialogflow.SessionsAsyncClient = None,
    parameters: Dict[str, Any] = None,
) -> List[str]:
    if session_client is None:
        session_client = await build_session_async_client(
            project_id=project_id,
            location_id=location_id,
            agent_id=agent_id,
            environment_id=environment_id,
        )
    project = f"projects/{project_id}"
    location = f"locations/{location_id}"
    agent = f"agents/{agent_id}"
    if environment_id is not None:
        agent += f"/environments/{environment_id}"
    session = f"sessions/{session_id}"
    session_path = f"{project}/{location}/{agent}/{session}"
    text_input = dialogflow.TextInput(text=text)
    query_input = dialogflow.QueryInput(text=text_input, language_code=language_code)
    if parameters:
        query_params = dialogflow.QueryParameters(parameters=parameters)
        request = dialogflow.DetectIntentRequest(
            session=session_path, query_input=query_input, query_params=query_params
        )
    else:
        request = dialogflow.DetectIntentRequest(session=session_path, query_input=query_input)
    response = await session_client.detect_intent(request=request)
    response_messages = [" ".join(msg.text.text) for msg in response.query_result.response_messages]
    ret_messages = [msg for msg in response_messages if msg.strip() != ""]
    return ret_messages
