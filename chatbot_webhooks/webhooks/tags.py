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
from prefeitura_rio.integrations.sgrc.models import (
    Address,
    NewTicket,
    Requester,
    Phones,
)
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
    validate_name,
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

        # Build data models for opening a ticket ###

        # Get the correct string in both cases, when it was collected by dialogflow
        # and when it comes from api
        if "usuario_nome_cadastrado" in parameters and validate_name(parameters):
            if "original" in parameters["usuario_nome_cadastrado"]:
                usuario_nome_cadastrado = parameters["usuario_nome_cadastrado"][
                    "original"
                ]
            else:
                usuario_nome_cadastrado = parameters["usuario_nome_cadastrado"]
        else:
            usuario_nome_cadastrado = ""
        requester = Requester(
            email=parameters["usuario_email"] if "usuario_email" in parameters else "",
            cpf=parameters["usuario_cpf"] if "usuario_cpf" in parameters else "",
            name=usuario_nome_cadastrado,
            phones=Phones(parameters["usuario_telefone_cadastrado"])
            if "usuario_telefone_cadastrado" in parameters
            else "",
        ) 
        # Get street number from Dialogflow, defaults to 1
        street_number = (
            parameters["logradouro_numero"]
            if "logradouro_numero" in parameters and parameters["logradouro_numero"]
            else "1"
        )
        # Extract number from string
        street_number = "".join(filter(str.isdigit, street_number))
        # 1647 - Remoção de resíduos em logradouro
        if str(codigo_servico_1746) == "1647":
            # Considera o ponto de referência informado pelo usuário caso não tenha sido
            # identificado algum outro pelo Google
            if (
                "logradouro_ponto_referencia_identificado" in parameters
                and parameters["logradouro_ponto_referencia_identificado"]
            ):
                ponto_referencia = parameters[
                    "logradouro_ponto_referencia_identificado"
                ]
            elif (
                "logradouro_ponto_referencia" in parameters
                and parameters["logradouro_ponto_referencia"]
            ):
                ponto_referencia = parameters["logradouro_ponto_referencia"]
            else:
                ponto_referencia = ""

            address = Address(
                street=parameters["logradouro_nome"]
                if "logradouro_nome" in parameters
                else "",  # logradouro_nome
                street_code=parameters["logradouro_id_ipp"]
                if "logradouro_id_ipp" in parameters
                else "",  # logradouro_id_ipp
                neighborhood=parameters["logradouro_bairro_ipp"]
                if "logradouro_bairro_ipp" in parameters
                else "",  # logradouro_bairro
                neighborhood_code=parameters["logradouro_id_bairro_ipp"]
                if "logradouro_id_bairro_ipp" in parameters
                else "",  # logradouro_id_bairro_ipp
                number=street_number,
                locality=ponto_referencia,
                zip_code=parameters["logradouro_cep"]
                if "logradouro_cep" in parameters and parameters["logradouro_cep"]
                else "",
            )
            # Create new ticket
            try:
                logger.info("Serviço: Remoção de Resíduo em Logradouro")
                logger.info("Endereço")
                logger.info(address)
                logger.info("--------------------")
                logger.info("Usuario")
                logger.info(requester)
                logger.info("--------------------")
                # Joins description with reference point
                descricao_completa = parameters["servico_1746_descricao"]

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
        # 1647 - Poda de Árvore em Logradouro
        elif str(codigo_servico_1746) == "1614":
            # Considera o ponto de referência informado pelo usuário caso não tenha sido
            # identificado algum outro pelo Google
            if (
                "logradouro_ponto_referencia_identificado" in parameters
                and parameters["logradouro_ponto_referencia_identificado"]
            ):
                ponto_referencia = parameters[
                    "logradouro_ponto_referencia_identificado"
                ]
            elif (
                "logradouro_ponto_referencia" in parameters
                and parameters["logradouro_ponto_referencia"]
            ):
                ponto_referencia = parameters["logradouro_ponto_referencia"]
            else:
                ponto_referencia = ""

            address = Address(
                street=parameters["logradouro_nome"]
                if "logradouro_nome" in parameters
                else "",  # logradouro_nome
                street_code=parameters["logradouro_id_ipp"]
                if "logradouro_id_ipp" in parameters
                else "",  # logradouro_id_ipp
                neighborhood=parameters["logradouro_bairro_ipp"]
                if "logradouro_bairro_ipp" in parameters
                else "",  # logradouro_bairro
                neighborhood_code=parameters["logradouro_id_bairro_ipp"]
                if "logradouro_id_bairro_ipp" in parameters
                else "",  # logradouro_id_bairro_ipp
                number=street_number,
                locality=ponto_referencia,
                zip_code=parameters["logradouro_cep"]
                if "logradouro_cep" in parameters and parameters["logradouro_cep"]
                else "",
            )
            # Create new ticket
            try:
                logger.info("Serviço: Poda de Árvore em Logradouro")
                logger.info("Endereço")
                logger.info(address)
                logger.info("--------------------")
                logger.info("Usuario")
                logger.info(requester)
                logger.info("--------------------")
                # Joins description with reference point
                descricao_completa = parameters["servico_1746_descricao"]

                ticket: NewTicket = new_ticket(
                    classification_code=1614,
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
            try:
                parameters["logradouro_numero"] = str(parameters["logradouro_numero"]).split(".")[0]
            except:  # noqa
                pass
            address_to_google = f"{parameters['logradouro_nome']['original']} {parameters['logradouro_numero']}, Rio de Janeiro - RJ"  # noqa
            logger.info(f'Input geolocator: "{address_to_google}"')
            parameters["logradouro_indicador_validade"] = google_geolocator(
                address_to_google, parameters
            )
        # Se não existe, também chama o geolocator
        else:
            address_to_google = f"{parameters['logradouro_nome']['original']}, Rio de Janeiro - RJ"  # noqa
            logger.info(f'Input geolocator: "{address_to_google}"')
            parameters["logradouro_indicador_validade"] = google_geolocator(
                address_to_google, parameters
            )
        ### VERSÃO PONTO DE REFERÊNCIA EQUIVALENTE A NÚMERO ###    
        # # Se não existe, é porque existe ao menos um ponto de referencia, então chama o find_place
        # else:
        #     address_to_google = f"{parameters['logradouro_nome']['original']}, {parameters['logradouro_ponto_referencia']}, Rio de Janeiro - RJ"  # noqa
        #     logger.info(f'Input find_place: "{address_to_google}"')
        #     parameters["logradouro_indicador_validade"] = google_find_place(
        #         address_to_google, parameters
        #     )

    except:  # noqa
        parameters = request_data["sessionInfo"]["parameters"]
        message = ""

        parameters["encaminhar_transbordo_agora"] = True

    return message, parameters


def identificador_ipp(request_data: dict) -> Tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    get_ipp_info(parameters)

    # Formatando o logradouro_numero para o envio da mensagem ao cidadão
    if parameters["logradouro_numero"]:
        try:
            logradouro_numero = str(parameters["logradouro_numero"]).split(".")[0]
        except:  # noqa
            logradouro_numero = (
                parameters["logradouro_numero"]
                if "logradouro_numero" in parameters
                and parameters["logradouro_numero"] != "None"
                else ""
            )
            logger.info("logradouro_numero: falhou ao tentar pegar a parcela antes do `.`")
    else:
        logradouro_numero = ""
    
    print(f'logradouro_numero: {logradouro_numero}, tipo {type(logradouro_numero)}')

    # Priorioza o ponto de referência identificado pelo Google
    # mas considera o ponto de referência informado pelo usuário caso o Google não tenha identificado algum
    if (
        "logradouro_ponto_referencia_identificado" in parameters
        and parameters["logradouro_ponto_referencia_identificado"]
    ):
        ponto_referencia = parameters["logradouro_ponto_referencia_identificado"]
    elif (
        "logradouro_ponto_referencia" in parameters
        and parameters["logradouro_ponto_referencia"]
    ):
        ponto_referencia = parameters["logradouro_ponto_referencia"]
    else:
        ponto_referencia = ""

    # Início da geração da mensagem
    parameters["logradouro_mensagem_confirmacao"] = ""
    parameters[
        "logradouro_mensagem_confirmacao"
    ] += f'Logradouro: {parameters["logradouro_nome"]} \n'
    parameters["logradouro_mensagem_confirmacao"] += (
        f"Número:  {logradouro_numero}\n"
        if logradouro_numero != ""
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f"Ponto de referência:  {ponto_referencia}\n" if ponto_referencia != "" else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Bairro:  {parameters["logradouro_bairro_ipp"]}\n'
        if "logradouro_bairro_ipp" in parameters
        else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'CEP:  {parameters["logradouro_cep"]}\n'
        if "logradouro_cep" in parameters
        and parameters["logradouro_cep"]
        and parameters["logradouro_cep"] != "None"
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

    return message, parameters


def validador_cpf(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    #form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_cpf_valido"] = validate_CPF(parameters)

    return message, parameters#, form_parameters_list


def validador_email(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    #form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_email_valido"] = validate_email(parameters)

    return message, parameters#, form_parameters_list

def validador_nome(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    #form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_nome_valido"] = validate_name(parameters)

    # if not parameters["usuario_nome_valido"]:
    #     message += 'Desculpe, não consegui entender.\n\nVerifique se o nome digitado contém nome e sobrenome e tente novamente.\n\nCaso não queira se identificar, digite "avançar".'

    return message, parameters#, form_parameters_list


def confirma_email(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]
    cpf = parameters["usuario_cpf"]
    email_dialogflow = str(parameters["usuario_email"]).strip().lower()
    logger.info(f"Email informado pelo usuário: {email_dialogflow}")
    try:
        logger.info(f"Buscando informações do usuário no SGRC com CPF {cpf}")
        user_info = get_user_info(cpf)
    except:  # noqa
        logger.error(f"Erro ao buscar informações do usuário no SGRC com CPF {cpf}")
        parameters["usuario_email_confirmado"] = True
        parameters["usuario_email_cadastrado"] = None
        return message, parameters

    logger.info(f"Retorno do SGRC: {user_info}")
    email_sgrc = str(user_info["email"]).strip().lower() if user_info["email"] else ""
    nome_sgrc = str(user_info["name"]).strip() if user_info["name"] else ""
    if "phones" in user_info and user_info["phones"]:
        telefone_sgrc = (
            str(user_info["phones"][0]).strip() if user_info["phones"][0] else ""
        )
    else:
        telefone_sgrc = ""

    logger.info(f"E-mail do SGRC: {email_sgrc}")
    logger.info(f"E-mail informado pelo usuário: {email_dialogflow}")
    logger.info(f"E-mails são iguais? {email_dialogflow == email_sgrc}")
    logger.info(f"E-mail do SGRC é vazio? {not email_sgrc}")
    if (email_dialogflow == email_sgrc) or (not email_sgrc):
        parameters["usuario_email_confirmado"] = True
        parameters["usuario_email_cadastrado"] = None
        parameters["usuario_nome_cadastrado"] = nome_sgrc
        parameters["usuario_telefone_cadastrado"] = telefone_sgrc
    else:
        masked_email = mask_email(email_sgrc)
        logger.info(f"E-mail mascarado: {masked_email}")
        parameters["usuario_email_confirmado"] = False
        parameters["usuario_email_cadastrado"] = masked_email
        parameters["usuario_nome_cadastrado"] = nome_sgrc
        parameters["usuario_telefone_cadastrado"] = telefone_sgrc
    return message, parameters


def definir_descricao(request_data: dict) -> tuple[str, dict]:
    # logger.info(request_data)
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""
    ultima_mensagem_usuario = request_data["text"]

    logger.info(f"Ultima mensagem: \n {ultima_mensagem_usuario}")

    if parameters["codigo_servico_1746"] == "1647":
        logger.info("Descrição de Remoção de Resíduo em Logradouro")
        parameters["servico_1746_descricao"] = ultima_mensagem_usuario
    elif parameters["codigo_servico_1746"] == "1614":
        logger.info("Descrição de Poda de Árvore em Logradouro")
        parameters["servico_1746_descricao"] = ultima_mensagem_usuario

    logger.info(parameters)

    return message, parameters

def define_variavel_ultima_mensagem(request_data: dict) -> tuple[str, dict]:
    # logger.info(request_data)
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""
    ultima_mensagem_usuario = request_data["text"]

    logger.info(f"A variável {parameters['variavel_recebe_ultima_mensagem']} está recebendo o valor \
    da última mensagem enviada pelo usuário: \n {ultima_mensagem_usuario}")

    parameters[parameters["variavel_recebe_ultima_mensagem"]] = ultima_mensagem_usuario
    parameters["variavel_recebe_ultima_mensagem"] = None

    logger.info(parameters)

    return message, parameters

def reseta_parametros(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    for key in parameters:
        parameters[key] = None

    return message, parameters

def identifica_ambiente(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    parameters["ambiente"] = settings.SENTRY_ENVIRONMENT

    return message, parameters
