# -*- coding: utf-8 -*-
from typing import Tuple

from django.conf import settings
from loguru import logger
from prefeitura_rio.integrations.sgrc import new_ticket
from prefeitura_rio.integrations.sgrc.exceptions import (
    SGRCMalformedBodyException,
    SGRCInvalidBodyException,
    SGRCBusinessRuleException,
    SGRCInternalErrorException,
    SGRCEquivalentTicketException,
    SGRCDuplicateTicketException,
)
from prefeitura_rio.integrations.sgrc.models import Address, NewTicket, Requester
import requests

from chatbot_webhooks.webhooks.utils import (
    get_ipp_info,
    google_find_place,
    google_geolocator,
)


def ai(request_data: dict) -> str:
    input_message: str = request_data["text"]
    response = requests.post(
        settings.CHATBOT_LAB_API_URL,
        headers={
            "Authorization": f"Bearer {settings.CHATBOT_LAB_API_KEY}",
        },
        json={
            "message": input_message,
            "chat_session_id": "e23bdc43-bb26-4273-a187-e3e23836e0c2",
            "contexts": ["cariocadigital"],
        },
    )
    try:
        response.raise_for_status()
    except Exception as exc:
        logger.error(f"Backend error: {exc}")
        logger.error(f"Message: {response.text}")
    response = response.json()
    logger.info(f"API response: {response}")
    return response["answer"]


def abrir_chamado_sgrc(request_data: dict) -> Tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    # Get classification code from Dialogflow
    codigo_servico_1746 = parameters["codigo_servico_1746"]

    # 1647 - Remoção de resíduos em logradouro
    if str(codigo_servico_1746) == "1647":
        # Build data models for opening a ticket
        requester = Requester(
            # name="",
            email=parameters["usuario_email"] if "usuario_email" in parameters else "",
            cpf=parameters["usuario_cpf"] if "usuario_cpf" in parameters else "",
        )
        address = Address(
            street=parameters["logradouro_nome"]
            if "logradouro_nome" in parameters
            else "",  # logradouro_nome
            street_code=parameters["logradouro_id_ipp"]
            if "logradouro_id_ipp" in parameters
            else "",  # logradouro_id_ipp
            neighborhood=parameters["logradouro_bairro"]
            if "logradouro_bairro" in parameters
            else "",  # logradouro_bairro
            neighborhood_code=parameters["logradouro_id_bairro_ipp"]
            if "logradouro_id_bairro_ipp" in parameters
            else "",  # logradouro_id_bairro_ipp
            number=parameters["logradouro_numero"]
            if "logradouro_numero" in parameters
            else "",  # logradouro_numero
        )
        # Create new ticket
        try:
            ticket: NewTicket = new_ticket(
                classification_code=1647,
                description=parameters["1647_descricao"],
                address=address,
                requester=requester,
            )
            # Atributos do ticket
            parameters["solicitacao_protocolo"] = ticket.protocol_id
            parameters["solicitacao_criada"] = True
            parameters["solicitacao_retorno"] = "sem_erro"
            # ticket.ticket_id
        # except BaseSGRCException as exc:
        #     # Do something with the exception
        #     pass
        except SGRCBusinessRuleException as exc:
            logger.exception(exc)
            parameters["solicitacao_criada"] = False
            parameters["solicitacao_retorno"] = "erro_interno"
        except SGRCInvalidBodyException as exc:
            logger.exception(exc)
            parameters["solicitacao_criada"] = False
            parameters["solicitacao_retorno"] = "erro_interno"
        except SGRCMalformedBodyException as exc:
            logger.exception(exc)
            parameters["solicitacao_criada"] = False
            parameters["solicitacao_retorno"] = "erro_interno"
        except ValueError as exc:
            logger.exception(exc)
            parameters["solicitacao_criada"] = False
            parameters["solicitacao_retorno"] = "erro_interno"
        except SGRCDuplicateTicketException as exc:
            logger.exception(exc)
            parameters["solicitacao_criada"] = False
            parameters["solicitacao_retorno"] = "erro_ticket_duplicado"
        except SGRCEquivalentTicketException as exc:
            logger.exception(exc)
            parameters["solicitacao_criada"] = False
            parameters["solicitacao_retorno"] = "erro_ticket_duplicado"
        except SGRCInternalErrorException as exc:
            logger.exception(exc)
            parameters["solicitacao_criada"] = False
            parameters["solicitacao_retorno"] = "erro_sgrc"
        return message, parameters
    else:
        raise NotImplementedError("Classification code not implemented")


def localizador(request_data: dict) -> Tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    # Inicializa essa variável para a chave existir no dicionário
    parameters["logradouro_ponto_referencia_identificado"] = None
    # Checa se o usuario informou o numero da rua
    try:
        parameters["logradouro_numero"]
    except:  # noqa
        logger.warning("Não foi informado um número de logradouro")
        parameters["logradouro_numero"] = None

    # Checa se o usuario informou algum ponto de referencia
    try:
        parameters["logradouro_ponto_referencia"]
    except:  # noqa
        logger.warning("Não foi informado um ponto de referência")
        parameters["logradouro_ponto_referencia"] = None

    # Se existe numero, chama o geolocator
    if parameters["logradouro_numero"]:
        address_to_google = f"{parameters['logradouro_nome']['original']} {parameters['logradouro_numero']}, Rio de Janeiro - RJ"  # noqa
        parameters["logradouro_indicador_validade"] = google_geolocator(
            address_to_google, parameters
        )
    # Se não existe, é porque existe ao menos um ponto de referencia, então chama o find_place
    else:
        address_to_google = f"{parameters['logradouro_nome']['original']}, {parameters['logradouro_ponto_referencia']}, Rio de Janeiro - RJ"  # noqa
        parameters["logradouro_indicador_validade"] = google_find_place(
            address_to_google, parameters
        )

    parameters["logradouro_mensagem_confirmacao"] = ""
    # parameters["logradouro_mensagem_confirmacao"] += f'Logradouro: {parameters["logradouro_nome"]["original"]} \n' if parameters["logradouro_ponto_referencia"] else f'Logradouro: {parameters["logradouro_nome"]} \n ' # noqa
    parameters[
        "logradouro_mensagem_confirmacao"
    ] += f'Logradouro: {parameters["logradouro_nome"]} \n '
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Número:  {int(parameters["logradouro_numero"])}\n'
        if parameters["logradouro_numero"]
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Ponto de referência informado:  {parameters["logradouro_ponto_referencia"]}\n'
        if parameters["logradouro_ponto_referencia"]
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Ponto de referência identificado:  {parameters["logradouro_ponto_referencia_identificado"]}\n'  # noqa
        if parameters["logradouro_ponto_referencia_identificado"]
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Bairro:  {parameters["logradouro_bairro"]}\n'
        if "logradouro_bairro" in parameters
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'CEP:  {parameters["logradouro_cep"]}\n'
        if "logradouro_cep" in parameters
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Cidade:  {parameters["logradouro_cidade"]}, {parameters["logradouro_estado"]}\n'  # noqa
        if "logradouro_cidade" in parameters
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Latitude, Longitude:  {parameters["logradouro_latitude"]}, {parameters["logradouro_longitude"]}'  # noqa
        if "logradouro_latitude" in parameters
        else ""
    )

    return message, parameters


def identificador_ipp(request_data: dict) -> Tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    get_ipp_info(parameters)

    return message, parameters