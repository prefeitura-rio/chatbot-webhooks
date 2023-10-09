# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Tuple

import aiohttp
from loguru import logger
from prefeitura_rio.integrations.sgrc.exceptions import (
    SGRCBusinessRuleException,
    SGRCDuplicateTicketException,
    SGRCEquivalentTicketException,
    SGRCInternalErrorException,
    SGRCInvalidBodyException,
    SGRCMalformedBodyException,
)
from prefeitura_rio.integrations.sgrc.models import (
    Address,
    NewTicket,
    Phones,
    Requester,
)
from unidecode import unidecode

from chatbot_webhooks import config
from chatbot_webhooks.webhooks.utils import (
    get_ipp_info,
    get_user_info,
    google_geolocator,
    mask_email,
    new_ticket,
    pgm_api,
    validate_CPF,
    validate_email,
    validate_name,
)


async def ai(request_data: dict) -> str:
    input_message: str = request_data["text"]
    async with aiohttp.ClientSession() as session:
        async with session.post(
            config.CHATBOT_LAB_API_URL,
            headers={
                "Authorization": f"Bearer {config.CHATBOT_LAB_API_KEY}",
            },
            json={
                "message": input_message,
                "chat_session_id": "e23bdc43-bb26-4273-a187-e3e23836e0c2",
                "contexts": ["cariocadigital"],
            },
        ) as response:
            try:
                await response.raise_for_status()
            except Exception as exc:
                logger.error(f"Backend error: {exc}")
                logger.error(f"Message: {response.text}")
            response = await response.json()
            logger.info(f"API response: {response}")
            return response["answer"]


async def abrir_chamado_sgrc(request_data: dict) -> Tuple[str, dict]:
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
                usuario_nome_cadastrado = parameters["usuario_nome_cadastrado"]["original"]
            else:
                usuario_nome_cadastrado = parameters["usuario_nome_cadastrado"]
        else:
            usuario_nome_cadastrado = ""
        requester = Requester(
            email=parameters["usuario_email"]
            if ("usuario_email" in parameters and "usuario_cpf") in parameters
            else "",
            cpf=parameters["usuario_cpf"]
            if ("usuario_cpf" in parameters and "usuario_email") in parameters
            else "",
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
        #
        #  1647 - Remoção de resíduos em logradouro
        #
        if str(codigo_servico_1746) == "1647":
            # Considera o ponto de referência informado pelo usuário caso não tenha sido
            # identificado algum outro pelo Google
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

                ticket: NewTicket = await new_ticket(
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
        #
        #  1647 - Poda de Árvore em Logradouro
        #
        elif str(codigo_servico_1746) == "1614":
            # Considera o ponto de referência informado pelo usuário caso não tenha sido
            # identificado algum outro pelo Google
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

                ticket: NewTicket = await new_ticket(
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
        #
        # 1464 - Verificação de Ar Condicionado Inoperante em Ônibus
        #
        elif str(codigo_servico_1746) == "1464":
            # Define um endereço aleatório (do COR) só pra abrir o ticket
            address = Address(
                street="Rua Ulysses Guimarães",
                street_code="211144",
                neighborhood="Cidade Nova",
                neighborhood_code="8",
                number="300",
                locality="",
                zip_code="20211-225",
            )

            # Define parâmetros específicos desse serviço

            ar_condicionado_inoperante_data_ocorrencia = parameters[
                "ar_condicionado_inoperante_data_ocorrencia"
            ]

            # Verificar se a chave "past" está presente no dicionário
            if "past" in ar_condicionado_inoperante_data_ocorrencia:
                data_ocorrencia_dict = ar_condicionado_inoperante_data_ocorrencia["past"]
            else:
                data_ocorrencia_dict = ar_condicionado_inoperante_data_ocorrencia

            # Verificar se "startDateTime" e "endDateTime" estão presentes
            if "startDateTime" in data_ocorrencia_dict and "endDateTime" in data_ocorrencia_dict:
                start_datetime = data_ocorrencia_dict["startDateTime"]
                end_datetime = data_ocorrencia_dict["endDateTime"]
            elif "startDate" in data_ocorrencia_dict and "endDate" in data_ocorrencia_dict:
                start_datetime = data_ocorrencia_dict["startDate"]
                end_datetime = data_ocorrencia_dict["endDate"]
            else:
                # Se nenhum dos conjuntos de campos estiver presente, use o dicionário original
                start_datetime = data_ocorrencia_dict
                end_datetime = data_ocorrencia_dict

            # Criar objetos de data e hora a partir dos dados do dicionário
            start_dt = datetime(
                year=int(start_datetime["year"]),
                month=int(start_datetime["month"]),
                day=int(start_datetime["day"]),
                hour=int(start_datetime.get("hours", 0)),
                minute=int(start_datetime.get("minutes", 0)),
                second=int(start_datetime.get("seconds", 0)),
            )

            end_dt = datetime(
                year=int(end_datetime["year"]),
                month=int(end_datetime["month"]),
                day=int(end_datetime["day"]),
                hour=int(end_datetime.get("hours", 0)),
                minute=int(end_datetime.get("minutes", 0)),
                second=int(end_datetime.get("seconds", 0)),
            )

            # Calcular o ponto médio do intervalo
            middle_dt = start_dt + (end_dt - start_dt) / 2

            # Extrair a data e hora do ponto médio
            data_ocorrencia = middle_dt.strftime("%d/%m/%Y")
            hora_ocorrencia = middle_dt.strftime("%H:%M:%S")

            # Imprimir as variáveis
            logger.info(f"data_ocorrencia: {data_ocorrencia}")
            logger.info(f"hora_ocorrencia: {hora_ocorrencia}")

            numero_carro = parameters.get("ar_condicionado_inoperante_numero_onibus", None)

            specific_attributes = {
                "dataOcorrenc": data_ocorrencia,
                "horOcorrenc": hora_ocorrencia,
                "numelinhOnib": parameters["ar_condicionado_inoperante_numero_linha"],
                "numCarro": numero_carro,
            }
            # Create new ticket
            try:
                logger.info("Serviço: Verificação de Ar Condicionado Inoperante em Ônibus")
                logger.info("Endereço")
                logger.info(address)
                logger.info("Usuario")
                logger.info(requester)
                logger.info("--------------------")
                logger.info("Informações Específicas")
                logger.info(specific_attributes)
                logger.info("--------------------")
                # Joins description
                descricao_completa = parameters["servico_1746_descricao"]

                ticket: NewTicket = await new_ticket(
                    address=address,
                    classification_code=1464,
                    description=descricao_completa,
                    requester=requester,
                    specific_attributes=specific_attributes,
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
        #
        # 152 - Reparo de Luminária
        #
        elif str(codigo_servico_1746) == "152":
            logger.info(parameters)

            # Considera o ponto de referência informado pelo usuário caso não tenha sido
            # identificado algum outro pelo Google
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

            # Definindo parâmetros específicos do serviço
            if (
                parameters.get("reparo_luminaria_quadra_esportes", None) == 1.0
                or parameters["reparo_luminaria_localizacao"] == "Quadra de esportes"
            ):
                dentro_quadra_esporte = "1"
            else:
                dentro_quadra_esporte = "0"

            if (
                parameters.get("logradouro_indicador_praca", None)
                or parameters["reparo_luminaria_localizacao"] == "Praça"
            ):
                esta_na_praca = "1"
            else:
                esta_na_praca = "0"

            specific_attributes = {
                "defeitoLuminaria": parameters["reparo_luminaria_defeito_classificado"],
                "dentroQuadraEsporte": dentro_quadra_esporte,
                "estaNaPraca": esta_na_praca,
                "localizacaoLuminaria": parameters["reparo_luminaria_localizacao"],
                "nomePraca": "",
            }

            # Complementa a descrição dependendo da localização da luminária
            if parameters.get("logradouro_indicador_comunidade", None):
                descricao_completa = (
                    f'{parameters["servico_1746_descricao"]}. Dados do '
                    f'condomínio: {parameters["reparo_luminaria_dados_comunidade"]}'
                )
            else:
                descricao_completa = parameters["servico_1746_descricao"]

            # Create new ticket
            try:
                logger.info("Serviço: Reparo de Luminária")
                logger.info("Endereço")
                logger.info(address)
                logger.info("Usuario")
                logger.info(requester)
                logger.info("--------------------")
                logger.info("Informações Específicas")
                logger.info(specific_attributes)
                logger.info("--------------------")

                ticket: NewTicket = await new_ticket(
                    address=address,
                    classification_code=18131,
                    description=descricao_completa,
                    requester=requester,
                    specific_attributes=specific_attributes,
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


async def localizador(request_data: dict) -> Tuple[str, dict]:
    logger.info(request_data)
    try:
        parameters = request_data["sessionInfo"]["parameters"]
        message = ""

        # Inicializa essas variáveis para as chaves existirem no dicionário
        parameters["logradouro_ponto_referencia_identificado"] = None
        parameters["logradouro_numero"] = None
        parameters["logradouro_ponto_referencia"] = None

        address_to_google = f"{parameters['logradouro_nome']}, Rio de Janeiro - RJ"  # noqa
        logger.info(f'Input geolocator: "{address_to_google}"')
        parameters["logradouro_indicador_validade"] = await google_geolocator(
            address_to_google, parameters
        )

        # VERSÃO PONTO DE REFERÊNCIA EQUIVALENTE A NÚMERO #
        # # Se não existe, é porque existe ao menos um ponto de referencia, então chama o find_place
        # else:
        #     address_to_google = f"{parameters['logradouro_nome']['original']}, {parameters['logradouro_ponto_referencia']}, Rio de Janeiro - RJ"  # noqa
        #     logger.info(f'Input find_place: "{address_to_google}"')
        #     parameters["logradouro_indicador_validade"] = await google_find_place(
        #         address_to_google, parameters
        #     )

    except:  # noqa
        parameters = request_data["sessionInfo"]["parameters"]
        message = ""

        parameters["encaminhar_transbordo_agora"] = True

    return message, parameters


async def identificador_ipp(request_data: dict) -> Tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    await get_ipp_info(parameters)

    # Se ao final de todo o processo não foi possível identificar logradouro_id e
    # logradouro_id_bairro válidos na base do IPP, não podemos seguir
    if (
        parameters["logradouro_id_ipp"] is None
        or parameters["logradouro_id_ipp"] == ""
        or parameters["logradouro_id_bairro_ipp"] is None
        or parameters["logradouro_id_bairro_ipp"] == "0"
    ):
        parameters["logradouro_indicador_validade"] = False
        return message, parameters

    # Formatando o logradouro_numero para o envio da mensagem ao cidadão
    if parameters["logradouro_numero"]:
        try:
            logradouro_numero = str(parameters["logradouro_numero"]).split(".")[0]
        except:  # noqa
            logradouro_numero = (
                parameters["logradouro_numero"]
                if "logradouro_numero" in parameters and parameters["logradouro_numero"] != "None"
                else ""
            )
            logger.info("logradouro_numero: falhou ao tentar pegar a parcela antes do `.`")
    else:
        logradouro_numero = ""

    print(f"logradouro_numero: {logradouro_numero}, tipo {type(logradouro_numero)}")

    # Priorioza o ponto de referência identificado pelo Google
    # mas considera o ponto de referência informado pelo usuário caso o Google não tenha identificado algum
    if (
        "logradouro_ponto_referencia_identificado" in parameters
        and parameters["logradouro_ponto_referencia_identificado"]
    ):
        ponto_referencia = parameters["logradouro_ponto_referencia_identificado"]
    elif "logradouro_ponto_referencia" in parameters and parameters["logradouro_ponto_referencia"]:
        ponto_referencia = parameters["logradouro_ponto_referencia"]
    else:
        ponto_referencia = ""

    # Início da geração da mensagem
    parameters["logradouro_mensagem_confirmacao"] = ""
    parameters[
        "logradouro_mensagem_confirmacao"
    ] += f'Logradouro: {parameters["logradouro_nome"]} \n'
    parameters["logradouro_mensagem_confirmacao"] += (
        f"Número:  {logradouro_numero}\n" if logradouro_numero != "" else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f"Ponto de referência:  {ponto_referencia}\n" if ponto_referencia != "" else ""
    )
    parameters["logradouro_mensagem_confirmacao"] += (
        f'Bairro:  {parameters["logradouro_bairro_ipp"]}\n'
        if "logradouro_bairro_ipp" in parameters and parameters["logradouro_bairro_ipp"] is not None
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


async def validador_cpf(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_cpf_valido"] = validate_CPF(parameters)

    return message, parameters  # , form_parameters_list


async def validador_email(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_email_valido"] = validate_email(parameters)

    return message, parameters  # , form_parameters_list


async def validador_nome(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_nome_valido"] = validate_name(parameters)

    # if not parameters["usuario_nome_valido"]:
    #     message += 'Desculpe, não consegui entender.\n\nVerifique se o nome digitado contém nome e sobrenome e tente novamente.\n\nCaso não queira se identificar, digite "avançar".'

    return message, parameters  # , form_parameters_list


async def confirma_email(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]
    cpf = parameters["usuario_cpf"]
    email_dialogflow = str(parameters["usuario_email"]).strip().lower()
    logger.info(f"Email informado pelo usuário: {email_dialogflow}")
    try:
        logger.info(f"Buscando informações do usuário no SGRC com CPF {cpf}")
        user_info = await get_user_info(cpf)
    except:  # noqa
        logger.error(f"Erro ao buscar informações do usuário no SGRC com CPF {cpf}")
        parameters["usuario_email_confirmado"] = True
        parameters["usuario_email_cadastrado"] = None
        return message, parameters

    logger.info(f"Retorno do SGRC: {user_info}")
    email_sgrc = str(user_info["email"]).strip().lower() if user_info["email"] else ""
    nome_sgrc = str(user_info["name"]).strip() if user_info["name"] else ""
    if "phones" in user_info and user_info["phones"]:
        telefone_sgrc = str(user_info["phones"][0]).strip() if user_info["phones"][0] else ""
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


async def define_variavel_ultima_mensagem(request_data: dict) -> tuple[str, dict]:
    # logger.info(request_data)
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""
    ultima_mensagem_usuario = request_data["text"]

    logger.info(
        f"A variável {parameters['variavel_recebe_ultima_mensagem']} está recebendo o valor \
    da última mensagem enviada pelo usuário: \n {ultima_mensagem_usuario}"
    )

    parameters[parameters["variavel_recebe_ultima_mensagem"]] = ultima_mensagem_usuario
    parameters["variavel_recebe_ultima_mensagem"] = None

    logger.info(parameters)

    return message, parameters


async def reseta_parametros(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    for key in parameters:
        parameters[key] = None

    return message, parameters


async def identifica_ambiente(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    parameters["ambiente"] = config.SENTRY_ENVIRONMENT

    return message, parameters


async def contador_no_match(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    if "contador_no_match" not in parameters:
        parameters["contador_no_match"] = 1
    else:
        parameters["contador_no_match"] += 1

    return message, parameters


async def checa_endereco_especial(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    logradouro_nome = parameters["logradouro_nome"]
    ponto_referencia = parameters.get("logradouro_ponto_referencia", None)
    palavras_praca = ["praça", "praca", "largo"]
    palavras_comunidade = [
        "condominio",
        "vila",
        "loteamento",
        "comunidade",
        "conjunto habitacional",
    ]

    # Remover acentos e transformar para minúsculas
    logradouro_nome = unidecode(logradouro_nome).lower()
    ponto_referencia = unidecode(ponto_referencia).lower() if ponto_referencia else ""

    # Verificar se a string contém pelo menos uma das palavras-chave
    if any(palavra in logradouro_nome for palavra in palavras_praca):
        logger.info("Entendi que o local é uma praça ou próximo de uma")
        parameters["logradouro_indicador_praca"] = True
    else:
        logger.info("O local não é uma praça.")

    if any(palavra in logradouro_nome for palavra in palavras_comunidade) or any(
        palavra in ponto_referencia for palavra in palavras_comunidade
    ):
        logger.info("Entendi que o endereço é em uma comunidade ou similar.")
        parameters["logradouro_indicador_comunidade"] = True
    else:
        logger.info("O endereço não fica em uma comunidade ou similar.")

    parameters["reparo_luminaria_endereco_especial_executado"] = True

    return message, parameters


async def rlu_classifica_defeito(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    mapeia_defeito = {
        (1, "uma", None): "Apagada",
        (1, "grupo", "bloco"): "Bloco ou grupo de luminárias apagadas",
        (1, "grupo", "intercaladas"): "Várias luminárias intercaladas apagadas",
        (2, "uma", None): "Piscando",
        (2, "grupo", "bloco"): "Bloco ou grupo de luminárias piscando",
        (2, "grupo", "intercaladas"): "Bloco ou grupo de luminárias piscando",
        (3, "uma", None): "Acesa durante o dia",
        (3, "grupo", "bloco"): "Bloco ou grupo de luminárias acesas de dia",
        (3, "grupo", "intercaladas"): "Várias luminárias intercaladas acesas de dia",
        (4, None, None): "Pendurada",
        (5, None, None): "Danificada",
        (6, None, None): "Com ruído",
    }

    defeito = int(parameters["reparo_luminaria_defeito"])
    quantidade = parameters.get("reparo_luminaria_quantidade", None)
    inter_ou_bloco = parameters.get("reparo_luminaria_intercaladas_bloco", None)
    if inter_ou_bloco:
        inter_ou_bloco = "bloco" if str(inter_ou_bloco) == "1.0" else "intercaladas"

    logger.info(f"As seleções do usuário foram: {tuple([defeito, quantidade, inter_ou_bloco])}")
    parameters["reparo_luminaria_defeito_classificado"] = mapeia_defeito[
        tuple([defeito, quantidade, inter_ou_bloco])
    ]
    logger.info(
        f"O defeito classificado foi: {parameters['reparo_luminaria_defeito_classificado']}"
    )

    return message, parameters


async def da_consulta_protestos(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    mapeia_opcoes_consulta = {
        1: "inscricaoImobiliaria",
        2: "cda",
        3: "cpfCnpj",
    }

    parametros_entrada = {
        "origem_solicitação": 0,
        mapeia_opcoes_consulta[parameters["opcao_consulta_protesto"]]: parameters[
            "parametro_de_consulta"
        ],
    }

    registros = await pgm_api(endpoint="v2/cdas/protestadas", data=parametros_entrada)

    if "erro" in registros:
        parameters["api_resposta_sucesso"] = False
        if "BadRequest - Não foram encontradas informações de protesto." in registros["motivos"]:
            parameters["api_resposta_erro"] = False
            parameters["api_descricao_erro"] = "Não foram encontradas informações de protesto."
        else:
            parameters["api_resposta_erro"] = True

            # partes = mensagem_erro.split('BadRequest - ', 1)
            # # Verificar se há pelo menos duas partes após a divisão
            # if len(partes) >= 2:
            #     descricao_erro = partes[1]  # O segundo elemento após a divisão contém a descrição do erro
            #     descricao_erro = descricao_erro.strip()

            parameters[
                "api_descricao_erro"
            ] = "Ocorreu um erro na sua solicitação, por favor tente mais tarde."
    else:
        parameters["api_resposta_sucesso"] = True

        mensagem_cda_protestadas = ""

        # Monta mensagem
        for i, cda in enumerate(registros):
            ex_guia = (
                f'{cda["numExercicio"]}/{cda["guia"]}'
                if cda.get("guia", "") != ""
                else cda["numExercicio"]
            )
            mensagem_cda_protestadas += f'*{i+1}.*\t*{cda["cdaId"]}* (natureza {cda["naturezaDivida"]} - exerc./guia {ex_guia})'
            mensagem_cda_protestadas += (
                f'\n{cda["descricaoMovimentoProtesto"]} Em {cda["dataultimoMovimentoProtesto"]}'
            )
            if cda.get("numeroCartorio", "") != "" and cda.get("numeroCartorio", None):
                mensagem_cda_protestadas += (
                    f'\nCartório {cda["numeroCartorio"]} - Protocolo nº {cda["numeroProtocolo"]}'
                )
            else:
                pass
            mensagem_cda_protestadas += "\n\n" if (i + 1) < len(registros) else ""

        parameters["mensagem_cda_protestadas"] = mensagem_cda_protestadas

    return message, parameters
