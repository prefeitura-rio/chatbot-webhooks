# -*- coding: utf-8 -*-
from typing import Tuple

from django.conf import settings
from loguru import logger
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
    get_user_info,
    google_find_place,
    google_geolocator,
    mask_email,
    new_ticket,
    validate_CPF,
    validate_email,
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
    try:
        parameters = request_data["sessionInfo"]["parameters"]
        message = ""

        # Get classification code from Dialogflow
        codigo_servico_1746 = parameters["codigo_servico_1746"]

        # 1647 - Remoção de resíduos em logradouro
        if str(codigo_servico_1746) == "1647":
            # Build data models for opening a ticket
            requester = Requester(
                # name="",
                email=parameters["usuario_email"]
                if "usuario_email" in parameters
                else "",
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
                if "logradouro_numero" in parameters and parameters["logradouro_numero"]
                else "1",  # logradouro_numero
            )
            # Create new ticket
            try:
                logger.info("Endereço")
                logger.info(address)
                logger.info("--------------------")
                logger.info("Usuario")
                logger.info(requester)
                logger.info("--------------------")
                # Joins description with reference point
                if "logradouro_ponto_referencia_identificado" in parameters:
                    descricao_completa = (
                        f'{parameters["remocao_residuo_descricao"]}. Ponto de '
                        f'referência: {parameters["logradouro_ponto_referencia_identificado"]}'
                    )
                else:
                    descricao_completa = parameters["remocao_residuo_descricao"]

                ticket: NewTicket = new_ticket(
                    classification_code=1647,
                    description=descricao_completa,
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
            except Exception as exc:
                logger.exception(exc)
                parameters["solicitacao_criada"] = False
                parameters["solicitacao_retorno"] = "erro_interno"
            return message, parameters
        else:
            raise NotImplementedError("Classification code not implemented")
    except:  # noqa
        parameters = request_data["sessionInfo"]["parameters"]
        message = ""

        parameters["encaminhar_transbordo_agora"] = True
        return message, parameters


def localizador(request_data: dict) -> Tuple[str, dict]:
    try:
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
            f'Número:  {parameters["logradouro_numero"]}\n'
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
        # parameters["logradouro_mensagem_confirmacao"] += (
        #     f'Latitude, Longitude:  {parameters["logradouro_latitude"]}, {parameters["logradouro_longitude"]}'  # noqa
        #     if "logradouro_latitude" in parameters
        #     else ""
        # )

    except:  # noqa
        parameters = request_data["sessionInfo"]["parameters"]
        message = ""

        parameters["encaminhar_transbordo_agora"] = True

    return message, parameters


def identificador_ipp(request_data: dict) -> Tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    get_ipp_info(parameters)

    return message, parameters


def validador_cpf(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_cpf_valido"] = validate_CPF(parameters, form_parameters_list)

    return message, parameters, form_parameters_list


def validador_email(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_email_valido"] = validate_email(
        parameters, form_parameters_list
    )

    return message, parameters, form_parameters_list


def confirma_email(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]
    cpf = parameters["usuario_cpf"]
    email_dialogflow = str(parameters["usuario_email"]).strip()
    try:
        user_info = get_user_info(cpf)
    except:  # noqa
        parameters["usuario_email_confirmado"] = True
        parameters["usuario_email_cadastrado"] = None
        return message, parameters
    email_sgrc = str(user_info["email"]).strip()
    if email_dialogflow == email_sgrc:
        parameters["usuario_email_confirmado"] = True
        parameters["usuario_email_cadastrado"] = None
    else:
        parameters["usuario_email_confirmado"] = False
        parameters["usuario_email_cadastrado"] = mask_email(email_sgrc)
    return message, parameters


def definir_descricao_1647(request_data: dict) -> tuple[str, dict]:
    # logger.info(request_data)
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""
    ultima_mensagem_usuario = request_data["text"]

    logger.info(f"Ultima mensagem: \n {ultima_mensagem_usuario}")
    parameters["remocao_residuo_descricao"] = ultima_mensagem_usuario
    logger.info(parameters)

    return message, parameters


def reseta_parametros(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    for key in parameters:
        parameters[key] = None

    return message, parameters
