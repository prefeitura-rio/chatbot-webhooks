# -*- coding: utf-8 -*-
from copy import copy
from datetime import datetime, timedelta
from typing import Tuple

import aiohttp
from loguru import logger
import pandas as pd
from prefeitura_rio.integrations.sgrc.exceptions import SGRCBusinessRuleException
from prefeitura_rio.integrations.sgrc.exceptions import SGRCDuplicateTicketException
from prefeitura_rio.integrations.sgrc.exceptions import SGRCEquivalentTicketException
from prefeitura_rio.integrations.sgrc.exceptions import SGRCInternalErrorException
from prefeitura_rio.integrations.sgrc.exceptions import SGRCInvalidBodyException
from prefeitura_rio.integrations.sgrc.exceptions import SGRCMalformedBodyException
from prefeitura_rio.integrations.sgrc.models import Address
from prefeitura_rio.integrations.sgrc.models import NewTicket
from prefeitura_rio.integrations.sgrc.models import Phones
from prefeitura_rio.integrations.sgrc.models import Requester
from unidecode import unidecode

from chatbot_webhooks import config
from chatbot_webhooks.webhooks.utils import get_address_protocols
from chatbot_webhooks.webhooks.utils import get_ipp_info
from chatbot_webhooks.webhooks.utils import get_user_info
from chatbot_webhooks.webhooks.utils import get_user_protocols
from chatbot_webhooks.webhooks.utils import google_geolocator
from chatbot_webhooks.webhooks.utils import mask_email
from chatbot_webhooks.webhooks.utils import new_ticket
from chatbot_webhooks.webhooks.utils import pgm_api
from chatbot_webhooks.webhooks.utils import validate_CPF
from chatbot_webhooks.webhooks.utils import validate_email
from chatbot_webhooks.webhooks.utils import validate_name
from chatbot_webhooks.webhooks.utils import validate_cpf_cnpj
from chatbot_webhooks.webhooks.utils import rebi_combinacoes_permitidas


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
                response.raise_for_status()
            except Exception as exc:
                logger.error(f"Backend error: {exc}")
                logger.error(f"Message: {response.text}")
            response = await response.json(content_type=None)
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

            # Verificar se "year", "month" e "day" estão presentes no dicionário, senão, use a data de hoje
            if (
                "year" not in start_datetime
                or "month" not in start_datetime
                or "day" not in start_datetime
            ):
                data_atual = datetime.now()
                start_datetime["year"] = data_atual.year
                start_datetime["month"] = data_atual.month
                start_datetime["day"] = data_atual.day
                end_datetime["year"] = data_atual.year
                end_datetime["month"] = data_atual.month
                end_datetime["day"] = data_atual.day

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

            # Foi usado "Quadra de esportes" pra ajudar o cidadão a entender e preencher melhor os parâmetros
            # mas o valor correto para a api é "Quadra"
            if parameters["reparo_luminaria_localizacao"] == "Quadra de esportes":
                parameters["reparo_luminaria_localizacao"] = "Quadra"

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

            # Define a descrição do serviço
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
        #
        # 182 - Reparo de Buraco, Deformamento ou Afundamento em Pista
        #
        elif str(codigo_servico_1746) == "182":
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
            specific_attributes = {
                "riscoAcidente": "Indefinido",
            }

            # Definindo a descrição do serviço
            descricao_completa = parameters["servico_1746_descricao"]

            # Create new ticket
            try:
                logger.info("Serviço: Reparo de Buraco, Deformamento ou Afundamento em Pista")
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
                    classification_code=182,
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
        # 3581 - Fiscalização de estacionamento irregular de veículo
        #
        elif str(codigo_servico_1746) == "3581":
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

            # As opções de tipo de estacionamento que a API aceita
            tipo_estacionamento_opcoes = {
                "Sobre a calçada": "402 - Sobre a calçada",
                "Em via pública": "403 - Em via pública",
                "Em frente a portão de garagem": "405 - Em frente a portão de garagem",
                "Em local com placa de proibido estacionar": "401 - Em local com placa de proibido estacionar",
                "Em ponto de táxi": "411 - Em ponto de táxi",
                "Em vaga de portadores de necessidades especiais": "404 - Em vaga de portadores de necessidades especiais",
                "Em local de carga e descarga": "406 - Em local de carga e descarga",
                "Em ciclovia": "417 - Em ciclovia",
            }
            tipo_estacionamento = tipo_estacionamento_opcoes[
                parameters["estacionamento_irregular_local"]
            ]

            placa_veiculo = parameters.get("estacionamento_irregular_placa_veiculo", None)

            # Definindo parâmetros específicos do serviço
            specific_attributes = {
                "tipoEstacionamento": tipo_estacionamento,
                "placa": placa_veiculo,
            }

            try:
                logger.info("Serviço: Fiscalização de estacionamento irregular de veículo")
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
                    classification_code=3581,
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
        # 3802 - Reparo de sinal de trânsito apagado
        #
        elif str(codigo_servico_1746) == "3802":
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

            # As opções de lampadas pagadas que a API aceita
            lampadas_apagadas_opcoes = {
                "uma": "Uma lâmpada apenas",
                "duas": "Duas lâmpadas",
                "todas": "Todas as lâmpadas do sinal",
            }

            lampadas_apagadas = lampadas_apagadas_opcoes[parameters["rsta_quantidades_lampadas"]]

            todo_cruzamento_piscando = parameters.get("rsta_cruzamento_piscando", "0")

            cruzamento = (
                "Rua 1: "
                + parameters.get("rsta_dados_cruzamento_1", "Não fica em cruzamento")
                + ". Rua 2 ou Ponto de Referência: "
                + parameters.get("rsta_dados_cruzamento_2", "Não fica em cruzamento")
            )

            # Definindo parâmetros específicos do serviço
            specific_attributes = {
                "quantasLampadasSinal": lampadas_apagadas,
                "nomeViasCruzamento": cruzamento,
                "todoCruzamentoPiscando": todo_cruzamento_piscando,
            }

            try:
                logger.info("Serviço: Reparo de sinal de trânsito apagado")
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
                    classification_code=3802,
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
        # 1607 - Remoção de Entulho e Bens Inservíveis
        #
        elif str(codigo_servico_1746) == "1607":
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
                complement=parameters.get("endereco_complemento", ""),
                locality=ponto_referencia,
                zip_code=parameters["logradouro_cep"]
                if "logradouro_cep" in parameters and parameters["logradouro_cep"]
                else "",
                address_type=parameters.get(
                    "endereco_tipo", "Casa"
                ),  # Se tiver sido capturado pelo fluxo, informado. Se não, é padronizado como Casa.
            )

            # Definindo parâmetros específicos do serviço
            specific_attributes = {}

            descricao = "MATERIAIS A REMOVER: "
            for item, quantidade in zip(
                parameters.get("rebi_material_nome_informado", []),
                parameters.get("rebi_material_quantidade_informada", []),
            ):
                try:
                    qtd = int(float(quantidade))
                except ValueError:
                    qtd = quantidade
                if descricao != "MATERIAIS A REMOVER: ":
                    descricao += ", "
                descricao += f"{item} - {qtd}"

            informacoes_complementares = parameters.get("rebi_informacoes_complementares", None)
            if informacoes_complementares:
                descricao += f". INFORMAÇÕES COMPLEMENTARES: {informacoes_complementares}"
            else:
                descricao += "."

            try:
                logger.info("Serviço: Remoção de Entulho e Bens Inservíveis")
                logger.info("Endereço")
                logger.info(address)
                logger.info("Usuario")
                logger.info(requester)
                logger.info("--------------------")
                logger.info("Informações Específicas")
                logger.info(descricao)
                logger.info("--------------------")
                # Joins description

                ticket: NewTicket = await new_ticket(
                    address=address,
                    classification_code=1607,
                    description=descricao,
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
        parameters.get("logradouro_id_ipp", None) is None
        or parameters.get("logradouro_id_ipp", None) == ""
        or parameters.get("logradouro_id_bairro_ipp", None) is None
        or parameters.get("logradouro_id_bairro_ipp", None) == "0"
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

    logger.info(f"logradouro_numero: {logradouro_numero}, tipo {type(logradouro_numero)}")

    # Formatando o logradouro_id_bairro_ipp para o envio da mensagem ao cidadão
    if parameters["logradouro_id_bairro_ipp"]:
        try:
            logradouro_id_bairro_ipp = str(parameters["logradouro_id_bairro_ipp"]).split(".")[0]
        except:  # noqa
            logradouro_id_bairro_ipp = (
                parameters["logradouro_id_bairro_ipp"]
                if "logradouro_id_bairro_ipp" in parameters
                and parameters["logradouro_id_bairro_ipp"] != "None"
                else ""
            )
            logger.info("logradouro_id_bairro_ipp: falhou ao tentar pegar a parcela antes do `.`")
    else:
        logradouro_id_bairro_ipp = ""

    logger.info(
        f"logradouro_id_bairro_ipp: {logradouro_id_bairro_ipp}, tipo {type(logradouro_id_bairro_ipp)}"
    )
    parameters["logradouro_id_bairro_ipp"] = logradouro_id_bairro_ipp

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
    ### RETIRANDO O CEP DAS INFORMAÇÕES A PEDIDO DO MALHEIRO
    # parameters["logradouro_mensagem_confirmacao"] += (
    #     f'CEP:  {parameters["logradouro_cep"]}\n'
    #     if "logradouro_cep" in parameters
    #     and parameters["logradouro_cep"]
    #     and parameters["logradouro_cep"] != "None"
    #     else ""
    # )
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


async def validador_cpf_cnpj(request_data: dict) -> tuple[str, dict, list]:
    parameters = request_data["sessionInfo"]["parameters"]
    # form_parameters_list = request_data["pageInfo"]["formInfo"]["parameterInfo"]
    message = ""

    parameters["usuario_cpf_cnpj_valido"] = validate_cpf_cnpj(parameters)

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

    # Define caracteres não aceitos no SGRC e que é melhor que sejam retirados dos inputs do usuário
    mapping_table = str.maketrans({"<": "", ">": ""})

    # use translate() method to replace characters
    ultima_mensagem_usuario = ultima_mensagem_usuario.translate(mapping_table)

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
        "1": "inscricaoImobiliaria",
        "2": "cda",
        "3": "cpfCnpj",
    }

    parametros_entrada = {
        "origem_solicitação": 0,
        mapeia_opcoes_consulta[parameters["opcao_consulta_protesto"]]: parameters[
            "parametro_de_consulta"
        ],
    }

    registros = await pgm_api(endpoint="v2/cdas/protestadas", data=parametros_entrada)

    # Tratamento padrão para erros
    if "erro" in registros:
        parameters["api_resposta_sucesso"] = False
        parameters["api_descricao_erro"] = registros["motivos"]
        return message, parameters

    # API retornou registros
    parameters["api_resposta_sucesso"] = True

    mensagem_cda_protestadas = ""

    # Monta mensagem
    for i, cda in enumerate(registros):

        if cda.get("numExercicio", "") != "" and cda.get("numExercicio", "") != None:
            ex_guia = (
                f'{cda["numExercicio"]}/{cda["guia"]}'
                if cda.get("guia", "") != ""
                else cda["numExercicio"]
            )
            exercicio_guia = f" - exerc./guia {ex_guia}"
        else:
            exercicio_guia = ""

        mensagem_cda_protestadas += (
            f'*{i+1}. *\t*{cda["cdaId"]}* (natureza {cda["naturezaDivida"]}{exercicio_guia})'
        )
        mensagem_cda_protestadas += f'\nFase de Cobrança: {cda["faseCobranca"]}, Situação: {cda["situacao"]}, Saldo Total da Dívida: {cda["saldoTotal"]}'
        if cda.get("numeroCartorio", "") != "" and cda.get("numeroCartorio", None):
            mensagem_cda_protestadas += (
                f'\nCartório {cda["numeroCartorio"]} - Protocolo nº {cda["numeroProtocolo"]}'
            )
        else:
            pass
        mensagem_cda_protestadas += "\n\n" if (i + 1) < len(registros) else ""

    parameters["mensagem_cda_protestadas"] = mensagem_cda_protestadas

    return message, parameters


async def da_consulta_debitos_contribuinte(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    logger.info(parameters)

    mapeia_opcoes_consulta = {
        "Inscrição Imobiliária": "inscricaoImobiliaria",
        "Certidão da Dívida Ativa": "cda",
        "CPF/CNPJ": "cpfCnpj",
        "Execução Fiscal": "numeroExecucaoFiscal",
    }

    mapeia_variaveis = {
        "Inscrição Imobiliária": "codigo_inscricao_imobiliaria",
        "Certidão da Dívida Ativa": "numero_certidao_divida_ativa",
        "CPF/CNPJ": "cpf_cnpj_contribuinte",
        "Execução Fiscal": "numero_execucao_fiscal",
    }

    if parameters["da1_tipo_de_consulta"] in [
        "Inscrição Imobiliária",
        "Certidão da Dívida Ativa",
        "CPF/CNPJ",
        "Execução Fiscal",
    ]:
        parametros_entrada = {
            "origem_solicitação": 0,
            mapeia_opcoes_consulta[parameters["da1_tipo_de_consulta"]]: parameters[
                mapeia_variaveis[parameters["da1_tipo_de_consulta"]]
            ],
        }
    else:
        parametros_entrada = {
            "origem_solicitação": 0,
            "anoAutoInfracao": parameters["ano_auto_infracao"],
            "numeroAutoInfracao": parameters["numero_auto_infracao"],
        }

    registros = await pgm_api(endpoint="v2/cdas/dividas-contribuinte", data=parametros_entrada)

    # Tratamento padrão para erros
    if "erro" in registros:
        parameters["api_resposta_sucesso"] = False
        parameters["api_descricao_erro"] = registros["motivos"]
        return message, parameters

    # API retornou registros
    parameters["api_resposta_sucesso"] = True

    mapeia_descricoes = {
        "Inscrição Imobiliária": "Inscrição Imobiliária",
        "Certidão da Dívida Ativa": "Certidão de Dívida Ativa",
        "CPF/CNPJ": "CPF/CNPJ",
        "Execução Fiscal": "Número de Execução Fiscal",
        "Auto de Infração": "Nº e Ano do Auto de Infração",
    }

    indice = 0
    itens_pagamento = dict()
    msg = ""
    # Cabeçalho da Mensagem
    if parameters["da1_tipo_de_consulta"] in [
        "Inscrição Imobiliária",
        "Certidão da Dívida Ativa",
        "CPF/CNPJ",
        "Execução Fiscal",
    ]:
        msg += f'{mapeia_descricoes[parameters["da1_tipo_de_consulta"]]}: {parameters[mapeia_variaveis[parameters["da1_tipo_de_consulta"]]]}'
    else:
        msg += f'{mapeia_descricoes[parameters["da1_tipo_de_consulta"]]}: {parameters["numero_auto_infracao"]} {parameters["ano_auto_infracao"]}'
    # Endereço do Imóvel
    if parameters["da1_tipo_de_consulta"] == "Inscrição Imobiliária":
        msg += f'\nEndereço do Imóvel: {registros["enderecoImovel"]}'
    msg += f'\nData de Vencimento: {registros["dataVencimento"]}'
    if (
        len(registros["debitosNaoParceladosComSaldoTotal"]["cdasNaoAjuizadasNaoParceladas"]) > 0
        or len(registros["debitosNaoParceladosComSaldoTotal"]["efsNaoParceladas"]) > 0
    ):
        msg += f'\n\nDébitos não parcelados - Saldo Total da Dívida {registros["debitosNaoParceladosComSaldoTotal"]["saldoTotalNaoParcelado"]}'
        if len(registros["debitosNaoParceladosComSaldoTotal"]["cdasNaoAjuizadasNaoParceladas"]) > 0:
            # CDAS AQUI
            msg += "\n\nCDAs não parceladas"
            cdas = []
            for i, cda in enumerate(
                registros["debitosNaoParceladosComSaldoTotal"]["cdasNaoAjuizadasNaoParceladas"]
            ):
                indice += 1
                itens_pagamento[indice] = cda["cdaId"]
                msg += f'\n*{indice}.*\t*Certidão {cda["cdaId"]}* - Saldo {cda["valorSaldoTotal"]}'
                cdas.append(cda["cdaId"])
            parameters["lista_cdas"] = cdas
        if len(registros["debitosNaoParceladosComSaldoTotal"]["efsNaoParceladas"]) > 0:
            # EFS AQUI
            msg += "\n\nEFs não parceladas"
            efs = []
            for i, ef in enumerate(
                registros["debitosNaoParceladosComSaldoTotal"]["efsNaoParceladas"]
            ):
                indice += 1
                itens_pagamento[indice] = ef["numeroExecucaoFiscal"]
                msg += f'\n*{indice}.*\t*Execução Fiscal {ef["numeroExecucaoFiscal"]}* - Saldo {ef["saldoExecucaoFiscalNaoParcelada"]}'
                efs.append(ef["numeroExecucaoFiscal"])
            parameters["lista_efs"] = efs
    if len(registros["guiasParceladasComSaldoTotal"]["guiasParceladas"]) > 0:
        # GUIAS AQUI
        msg += "\n\nGuias de parcelamento vigentes"
        guias = []
        for i, guia in enumerate(registros["guiasParceladasComSaldoTotal"]["guiasParceladas"]):
            indice += 1
            itens_pagamento[indice] = guia["numero"]
            msg += f'\n*{indice}.*\t*Guia nº {guia["numero"]}* - Data do Último Pagamento: {guia["dataUltimoPagamento"]}'
            guias.append(guia["numero"])
        parameters["lista_guias"] = guias

    parameters["dicionario_itens"] = itens_pagamento
    parameters["total_itens_pagamento"] = indice
    parameters["mensagem_divida_contribuinte"] = msg
    parameters["lista_efs"] = (
        parameters.get("lista_efs", []) if parameters.get("lista_efs", None) is not None else []
    )
    parameters["lista_cdas"] = (
        parameters.get("lista_cdas", []) if parameters.get("lista_cdas", None) is not None else []
    )
    parameters["lista_guias"] = (
        parameters.get("lista_guias", []) if parameters.get("lista_guias", None) is not None else []
    )

    try:
        parameters["guias_quantidade_total"] = len(parameters.get("lista_guias", []))
    except:
        parameters["guias_quantidade_total"] = 0

    try:
        qtd_efs = len(parameters.get("lista_efs", []))

    except:
        qtd_efs = 0
    try:
        qtde_cdas = len(parameters.get("lista_cdas", []))
    except:
        qtde_cdas = 0

    parameters["efs_cdas_quantidade_total"] = qtd_efs + qtde_cdas

    # Definindo parâmetros salto_total parcelado e não parcelado
    parameters["total_nao_parcelado"] = len(
        registros["debitosNaoParceladosComSaldoTotal"]["efsNaoParceladas"]
    ) + len(registros["debitosNaoParceladosComSaldoTotal"]["cdasNaoAjuizadasNaoParceladas"])

    parameters["total_parcelado"] = len(
        registros["guiasParceladasComSaldoTotal"]["guiasParceladas"]
    )

    return message, parameters


async def da_emitir_guia_pagamento_a_vista(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    logger.info(parameters)

    cdas = []
    efs = []
    if parameters.get("todos_itens_informados", None):
        itens_informados = [str(i) for i in range(1, int(parameters["total_itens_pagamento"]) + 1)]
    else:
        if type(parameters["itens_informados"]) == list:
            itens_informados = [
                str(int(sequencial)) for sequencial in parameters["itens_informados"]
            ]
        else:
            itens_informados = str(int(parameters["itens_informados"]))

    try:
        for sequencial in itens_informados:
            if parameters["dicionario_itens"][sequencial] in parameters.get("lista_cdas", []):
                cdas.append(parameters["dicionario_itens"][sequencial])
            elif parameters["dicionario_itens"][sequencial] in parameters.get("lista_efs", []):
                efs.append(parameters["dicionario_itens"][sequencial])

        parametros_entrada = {
            "origem_solicitação": 0,
            "cdas": cdas,
            "efs": efs,
        }
    except:  # noqa
        # Usuário informou sequenciais inválidos
        parameters["da_1_opcao_informada_invalida"] = True
        return message, parameters

    registros = await pgm_api(endpoint="v2/guiapagamento/emitir/avista", data=parametros_entrada)

    # Tratamento padrão para erros
    if "erro" in registros:
        parameters["api_resposta_sucesso"] = False
        parameters["api_descricao_erro"] = registros["motivos"]
        return message, parameters

    # API retornou registros
    parameters["api_resposta_sucesso"] = True
    message_parts = []
    dicionario_guias_pagamento_a_vista = dict()

    for i, item in enumerate(registros):
        dicionario_guias_pagamento_a_vista[i] = item
        barcode = item["codigoDeBarras"]
        pdf_file = item["pdf"]
        base64_data = item["arquivoBase64"]

        item_message = (
            f"Link: {pdf_file}"
            f"\n"
            f"Código de barras: {barcode}"
            # "SIGNATURE_TYPE_DIVISION_MESSAGE"
            # f"FILE:{pdf_file}:{base64_data}"
            # "SIGNATURE_TYPE_DIVISION_MESSAGE"
        )

        message_parts.append(item_message)

    message = "\n\n".join(message_parts)
    logger.info(message)

    return message, parameters


async def da_emitir_guia_regularizacao(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    logger.info(parameters)

    guias = []

    if parameters.get("todos_itens_informados", None):
        itens_informados = [str(i) for i in range(1, int(parameters["total_itens_pagamento"]) + 1)]
    else:
        if type(parameters["itens_informados"]) == list:
            # Caso em que o usuario pode informar mais de um item
            itens_informados = [
                str(int(sequencial)) for sequencial in parameters["itens_informados"]
            ]
        else:
            # Caso em que o usuario só possui um item
            itens_informados = str(int(parameters["itens_informados"]))

    try:
        for sequencial in itens_informados:
            if parameters["dicionario_itens"][sequencial] in parameters.get("lista_guias", []):
                guias.append(parameters["dicionario_itens"][sequencial])

        parametros_entrada = {
            "origem_solicitação": 0,
            "guias": guias,
        }
    except:  # noqa
        # Usuário informou sequenciais inválidos
        parameters["da_1_opcao_informada_invalida"] = True
        return message, parameters

    registros = await pgm_api(
        endpoint="v2/guiapagamento/emitir/regularizacao", data=parametros_entrada
    )

    # Tratamento padrão para erros
    if "erro" in registros:
        parameters["api_resposta_sucesso"] = False
        parameters["api_descricao_erro"] = registros["motivos"]
        return message, parameters

    # API retornou registros
    parameters["api_resposta_sucesso"] = True
    message_parts = []
    dicionario_guias_pagamento_a_vista = dict()

    for i, item in enumerate(registros):
        dicionario_guias_pagamento_a_vista[i] = item
        barcode = item["codigoDeBarras"]
        pdf_file = item["pdf"]
        base64_data = item["arquivoBase64"]

        item_message = (
            f"Link: {pdf_file}"
            f"\n"
            f"Código de barras: {barcode}"
            # "SIGNATURE_TYPE_DIVISION_MESSAGE"
            # f"FILE:{pdf_file}:{base64_data}"
            # "SIGNATURE_TYPE_DIVISION_MESSAGE"
        )

        message_parts.append(item_message)

    message = "\n\n".join(message_parts)

    return message, parameters


async def da_cadastro(request_data: dict) -> tuple[str, dict]:
    parameters = request_data["sessionInfo"]["parameters"]
    message = ""

    logger.info(parameters)

    try:
        parametros_entrada = {
            "cpfCnpj": parameters["usuario_cpf"],
            "celular": parameters["usuario_telefone"],
            "correioEletronico": parameters["usuario_email"],
        }
    except:  # noqa
        # Informações chegaram inválidas
        parameters["api_resposta_sucesso"] = False
        parameters[
            "api_descricao_erro"
        ] = "Houve um erro na coleta de dados e não será possível realizar o seu cadastro no momento. Por favor, tente mais tarde."
        return message, parameters

    registros = await pgm_api(endpoint="v2/notificacao/atualizar", data=parametros_entrada)

    logger.info(registros)

    # Tratamento padrão para erros
    if "erro" in registros:
        parameters["api_resposta_sucesso"] = False
        parameters["api_descricao_erro"] = registros["motivos"]
        return message, parameters

    # API retornou registros
    parameters["api_resposta_sucesso"] = True
    logger.info("Cadastro realizado com sucesso")

    return message, parameters


async def rebi_elegibilidade_abertura_chamado(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]
    cpf = parameters["usuario_cpf"]

    try:
        logger.info(f"Buscando informações do usuário no SGRC com CPF {cpf}")
        user_info = await get_user_info(cpf)
    except Exception as e:  # noqa
        logger.error(f"Erro ao buscar informações do usuário no SGRC com CPF {cpf}")
        if "message='NOT FOUND'" in str(e):
            parameters["rebi_elegibilidade_abertura_chamado"] = True
            logger.info("Usuário não encontrado na base de usuários.")
            return message, parameters
        parameters["rebi_elegibilidade_abertura_chamado"] = False
        parameters["rebi_elegibilidade_abertura_chamado_justificativa"] = "erro_desconhecido"
        return message, parameters

    logger.info(f"Retorno do SGRC: {user_info}")

    if not user_info["id"]:
        parameters["rebi_elegibilidade_abertura_chamado"] = True
        logger.info("Usuário não encontrado na base de usuários.")
        return message, parameters

    person_id = user_info["id"]

    try:
        logger.info(f"Buscando tickets do usuário no SGRC com CPF {cpf} e person_id {person_id}")
        user_protocols = await get_user_protocols(person_id)
    except:  # noqa
        logger.error(
            f"Erro ao buscar informações do usuário no SGRC com CPF {cpf} e person_id {person_id}"
        )
        parameters["rebi_elegibilidade_abertura_chamado"] = False
        parameters["rebi_elegibilidade_abertura_chamado_justificativa"] = "erro_desconhecido"
        return message, parameters

    logger.info(user_protocols)

    STATUS_TIPO_ABERTO = [
        "Aberto",
        "Em Andamento",
        "Em andamento privado",
        "Encaminhado à Comlurb - resíduo",
        "Pendente",
    ]

    for protocol in user_protocols:
        tickets = protocol["tickets"]
        for ticket in tickets:
            # Se o serviço é Remoção de Entulho
            if str(ticket["classification"]) == "1607":
                if ticket["status"] in STATUS_TIPO_ABERTO:
                    parameters["rebi_elegibilidade_abertura_chamado"] = False
                    parameters[
                        "rebi_elegibilidade_abertura_chamado_justificativa"
                    ] = "chamado_aberto"
                    logger.info(f"Já existe um ticket aberto: {ticket}")
                    return message, parameters
                else:
                    hoje = datetime.now().date()
                    data_fim = datetime.strptime(ticket["end_date"], "%Y-%m-%d").date()
                    if (hoje - data_fim).days <= 12:
                        parameters["rebi_elegibilidade_abertura_chamado"] = False
                        parameters[
                            "rebi_elegibilidade_abertura_chamado_justificativa"
                        ] = "chamado_fechado_12_dias"
                        logger.info(
                            f"Um ticket desse subtipo foi fechado há {logger.info((hoje - data_fim).days)} dias, valor menor que 12: {ticket}"
                        )
                        return message, parameters

    # Se não, passou em todos os critérios
    parameters["rebi_elegibilidade_abertura_chamado"] = True

    return message, parameters


async def rebi_tratador_lista_itens(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]

    current_materiais_nome = copy(parameters.get("rebi_material_nome_informado", None))
    logger.info(current_materiais_nome)
    current_materiais_quantidade = copy(parameters.get("rebi_material_quantidade_informada", None))
    logger.info(current_materiais_quantidade)
    new_materiais_nomes = [parameters.get("rebi_material_nome", "").lower()]
    logger.info(new_materiais_nomes)
    new_materiais_quantidade = [parameters["rebi_material_quantidade"]]
    logger.info(new_materiais_quantidade)
    parameters["rebi_material_nome_novo"] = copy(new_materiais_nomes)
    logger.info(parameters["rebi_material_nome_novo"])
    parameters["rebi_material_quantidade_novo"] = copy(new_materiais_quantidade)
    logger.info(parameters["rebi_material_quantidade_novo"])

    # Se estamos adicionando itens a listas já existentes
    if current_materiais_nome and current_materiais_quantidade:
        for i, (new_name, new_qtd) in enumerate(zip(new_materiais_nomes, new_materiais_quantidade)):
            if new_name in current_materiais_nome:
                logger.info(f"O item {new_name} já foi informado antes, somarei as quantidades.")
                j = current_materiais_nome.index(new_name)
                logger.info(
                    f"A quantidade do item {new_name} passou de {current_materiais_quantidade[j]} para {current_materiais_quantidade[j] + new_qtd}"
                )
                current_materiais_quantidade[j] += new_qtd
            else:
                logger.info(f"O item {new_name} é novo, então está sendo somado às listas.")
                current_materiais_nome.append(new_name)
                current_materiais_quantidade.append(new_qtd)

        logger.info(current_materiais_nome)
        logger.info(current_materiais_quantidade)

        parameters["rebi_material_nome"] = current_materiais_nome
        parameters["rebi_material_quantidade"] = current_materiais_quantidade

    return message, parameters


async def rebi_avaliador_combinacoes_itens(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]
    if type(parameters.get("rebi_material_nome", "")) == list:
        materiais_nomes = [nome.lower() for nome in parameters["rebi_material_nome"]]
    else:
        materiais_nomes = [parameters.get("rebi_material_nome", "").lower()]
    if type(parameters["rebi_material_quantidade"]) == list:
        materiais_quantidade = parameters["rebi_material_quantidade"]
    else:
        materiais_quantidade = [parameters["rebi_material_quantidade"]]

    GRUPOS_CODIGO_NOME = {1: "pequeno", 2: "grande", 3: "especial"}

    GRUPOS_CODIGO_NOME_PLURAL = {1: "pequenos", 2: "grandes", 3: "especiais"}

    GRUPOS_CODIGO_EXEMPLOS = {
        1: "luminárias, aspiradores, vaso de planta, etc.",
        2: "camas de casal, fogões, sofá, etc.",
        3: "entulho, tanque de concreto, armário de 4 portas, etc.",
    }

    material_info = {
        "id": {
            0: 3,
            1: 5,
            2: 6,
            3: 7,
            4: 8,
            5: 9,
            6: 10,
            7: 11,
            8: 12,
            9: 13,
            10: 14,
            11: 15,
            12: 16,
            13: 17,
            14: 18,
            15: 19,
            16: 20,
            17: 21,
            18: 22,
            19: 23,
            20: 24,
            21: 25,
            22: 26,
            23: 27,
            24: 28,
            25: 29,
            26: 30,
            27: 31,
            28: 32,
            29: 33,
            30: 34,
            31: 35,
            32: 36,
            33: 37,
            34: 38,
            35: 39,
            36: 40,
            37: 41,
            38: 42,
            39: 43,
            40: 44,
            41: 45,
            42: 46,
            43: 47,
            44: 48,
            45: 49,
            46: 50,
            47: 51,
            48: 52,
            49: 53,
            50: 54,
            51: 55,
            52: 56,
            53: 57,
            54: 58,
        },
        "nome": {
            0: "ar condicionado",
            1: "armário de alumínio de cozinha/banheiro",
            2: "armário de 4 portas duplex/guarda roupa",
            3: "aspirador de pó",
            4: "banheira",
            5: "bicicleta/velocípede",
            6: "boiler",
            7: "cadeiras/bancos",
            8: "caixonete de porta/janela",
            9: "canos/tubos/trilhos de cortina",
            10: "cama de casal",
            11: "cama de solteiro",
            12: "carpete/tapete/passadeira/colchonete",
            13: "cofre",
            14: "colchão de casal",
            15: "colchão de solteiro",
            16: "computador / impressora",
            17: "entulho",
            18: "escada",
            19: "espelho/quadro/persiana",
            20: "exaustor/sugar/coifa",
            21: "estante/rack",
            22: "fogão",
            23: "forno de microondas/elétrico",
            24: "galhadas",
            25: "garrafas de cerveja / vidro",
            26: "geladeira/freezer",
            27: "gesso / azulejos /cerâmicas",
            28: "grade de madeira ou ferro",
            29: "latão de 200 litros",
            30: "latas/baldes/bacias",
            31: "livros/revistas/jornais/papelão",
            32: "luminária",
            33: "madeiras/caixote/estrados/vulcapiso",
            34: "máquina de lavar roupas/louças",
            35: "máquina de costura",
            36: "mesa",
            37: "outros",
            38: "pedras",
            39: "pias/bancadas/cubas",
            40: "porta/janela/basculante",
            41: "sofá/poltrona",
            42: "tábua de passar roupas",
            43: "tacos",
            44: "tanque de lavagem plástico/louça",
            45: "tanque de concreto",
            46: "telha de aluminio",
            47: "telha de amianto",
            48: "telha francesa/tijolo",
            49: "tronco de árvore",
            50: "vaso de planta com terra",
            51: "vaso sanitário/bidê/lavatório",
            52: "aquecedor/cx descarga",
            53: "aparelho de som/tv/vídeo/vitrola",
            54: "armário peq até 3 portas/cômoda",
        },
        "limite_itens": {
            0: 1,
            1: 2,
            2: 1,
            3: 2,
            4: 1,
            5: 2,
            6: 1,
            7: 6,
            8: 5,
            9: 5,
            10: 1,
            11: 2,
            12: 5,
            13: 1,
            14: 1,
            15: 2,
            16: 2,
            17: 150,
            18: 1,
            19: 6,
            20: 2,
            21: 1,
            22: 1,
            23: 1,
            24: 12,
            25: 5,
            26: 1,
            27: 10,
            28: 4,
            29: 1,
            30: 10,
            31: 5,
            32: 5,
            33: 5,
            34: 1,
            35: 2,
            36: 2,
            37: 5,
            38: 10,
            39: 3,
            40: 4,
            41: 2,
            42: 2,
            43: 150,
            44: 2,
            45: 150,
            46: 5,
            47: 20,
            48: 150,
            49: 5,
            50: 2,
            51: 3,
            52: 2,
            53: 2,
            54: 1,
        },
        "unidade_medida": {
            0: "unidade",
            1: "unidades",
            2: "unidade desmontada",
            3: "unidades",
            4: "unidade",
            5: "unidades",
            6: "unidade",
            7: "unidades",
            8: "amarrados de até 1,5 m",
            9: "amarrados de até 1,5 m",
            10: "unidade desmontada",
            11: "unidades desmontadas",
            12: "rolos",
            13: "unidade até 60 kg",
            14: "unidade",
            15: "unidades",
            16: "unidades",
            17: "sacos plásticos de até 20 litros",
            18: "unidade",
            19: "unidades",
            20: "unidades",
            21: "unidade desmontada",
            22: "unidade",
            23: "unidade",
            24: "amarrados",
            25: "caixas/engradados até 10kg",
            26: "unidade",
            27: "amarrados/caixas até 10kg",
            28: "unidades",
            29: "unidade",
            30: "latas até 20 litros",
            31: "caixas/sacos/amarrados de até 10 kg",
            32: "unidades",
            33: "amarrados até 1,5m",
            34: "unidade",
            35: "unidades",
            36: "unidades",
            37: "unidades",
            38: "unidades até 10 kg",
            39: "unidades",
            40: "unidades",
            41: "unidades",
            42: "unidades",
            43: "sacos plásticos de até 20 litros",
            44: "unidades",
            45: "sacos plásticos de até 20 litros",
            46: "unidades",
            47: "pedaços até 10 kg",
            48: "unidades",
            49: "unidades de até 10 kg",
            50: "unidades",
            51: "unidades",
            52: "unidades",
            53: "unidades",
            54: "unidade desmontada",
        },
        "grupo": {
            0: 2,
            1: 1,
            2: 3,
            3: 1,
            4: 2,
            5: 1,
            6: 2,
            7: 1,
            8: 1,
            9: 1,
            10: 2,
            11: 1,
            12: 1,
            13: 2,
            14: 2,
            15: 1,
            16: 1,
            17: 3,
            18: 2,
            19: 1,
            20: 1,
            21: 2,
            22: 2,
            23: 1,
            24: 1,
            25: 1,
            26: 2,
            27: 1,
            28: 1,
            29: 2,
            30: 1,
            31: 1,
            32: 1,
            33: 1,
            34: 2,
            35: 1,
            36: 1,
            37: 1,
            38: 1,
            39: 1,
            40: 1,
            41: 2,
            42: 1,
            43: 1,
            44: 1,
            45: 3,
            46: 1,
            47: 1,
            48: 1,
            49: 1,
            50: 1,
            51: 1,
            52: 1,
            53: 1,
            54: 1,
        },
    }
    material_info = pd.DataFrame.from_dict(material_info)

    # Setando variáveis
    materiais_todos = dict()
    parameters["rebi_combinacao_itens_valida"] = True
    contagem_grupos = [0, 0, 0]
    for nome, quantidade in zip(materiais_nomes, materiais_quantidade):
        logger.info(nome, quantidade)
        logger.info(material_info.loc[material_info["nome"] == nome])
        limite_itens = material_info.loc[material_info["nome"] == nome, "limite_itens"].values[0]
        grupo_item = material_info.loc[material_info["nome"] == nome, "grupo"].values[0]
        grupo_item_nome = GRUPOS_CODIGO_NOME[grupo_item]
        unidade_medida_item = material_info.loc[
            material_info["nome"] == nome, "unidade_medida"
        ].values[0]
        materiais_todos[nome] = {
            "informado": quantidade,
            "permitido": limite_itens,
            "unidade": unidade_medida_item,
            "valido": True,
            "grupo": grupo_item_nome,
            "grupo_numero": grupo_item,
        }
        contagem_grupos[grupo_item - 1] += 1
        if quantidade <= limite_itens:
            logger.info(
                f"Item {nome} informado em quantia permitida, {quantidade} <= {limite_itens}"
            )
            pass
        else:
            logger.info(
                f"Item {nome} informado em quantia não permitida, {quantidade} > {limite_itens}"
            )
            materiais_todos[nome]["valido"] = False
            parameters["rebi_combinacao_itens_valida"] = False
    # Novos materiais
    materiais_novos = {
        key: value
        for key, value in materiais_todos.items()
        if key in parameters["rebi_material_nome_novo"]
    }
    materiais_novos.update(
        {
            key: {
                **value,
                "informado": parameters["rebi_material_quantidade_novo"][
                    parameters["rebi_material_nome_novo"].index(key)
                ],
            }
            for key, value in materiais_novos.items()
        }
    )

    # Quantidades inválidas
    if not parameters["rebi_combinacao_itens_valida"]:
        msg = ""
        for key, value in materiais_todos.items():
            if not value["valido"]:
                if msg:  # Add line breaks
                    msg += "\n\n"
                msg += (
                    f'O limite para remoção de {key} é de {value["permitido"]} {value["unidade"]}.'
                    # f'Esse item é classificado como {value["grupo"]}'
                )
        parameters["rebi_justificativa_combinacao_invalida"] = (
            msg + "\n\nInforme uma quantidade de itens dentro desse limite."
        )
        return message, parameters

    # Combinação inválida
    logger.info(f"A combinação informada (pequenos, grandes, especiais) foi {contagem_grupos}")
    validez_combinacao, justificativa, permitido_adicionar = await rebi_combinacoes_permitidas(
        contagem_grupos
    )
    if not validez_combinacao:
        logger.info("Combinação inválida")
        logger.info(justificativa)
        descricao_dos_itens = ""
        for i, grupo in enumerate(GRUPOS_CODIGO_NOME_PLURAL.values()):
            first_item = True
            if descricao_dos_itens:  # Add line breaks
                descricao_dos_itens += "\n"
            else:
                descricao_dos_itens = "Você solicitou a retirada de:\n"

            for key, value in materiais_todos.items():
                if value["grupo_numero"] == (i + 1):
                    if first_item:
                        descricao_dos_itens += f"\nItens {grupo}:"
                        first_item = False
                    try:
                        valor = int(float(value["informado"]))
                    except ValueError:
                        valor = value["informado"]
                    descricao_dos_itens += f"\n- {key.capitalize()}: {valor}"
                else:
                    continue
            # descricao_dos_itens += f'{key.capitalize()}: {value["grupo"]}, Máximo de {value["permitido"]} {value["unidade"]}'
        parameters["rebi_combinacao_itens_valida"] = False
        msg_combinacao_invalida = ""
        for key, value in materiais_novos.items():
            if msg_combinacao_invalida:
                msg_combinacao_invalida += ", "
            else:
                msg_combinacao_invalida += "Você solicitou a retirada de "
            try:
                valor = int(float(value["informado"]))
            except ValueError:
                valor = value["informado"]
            msg_combinacao_invalida += (
                f'{valor} {value["unidade"]} de {key.capitalize()} (material {value["grupo"]})'
            )
        msg_combinacao_invalida += ", mas esse material *não pode ser incluído* junto com os materiais que já foram selecionados."
        parameters["rebi_justificativa_combinacao_invalida"] = msg_combinacao_invalida
        return message, parameters

    logger.info("Combinação válida")
    # Gerando mensagem de combinações disponíveis
    logger.info(permitido_adicionar)
    combinacoes_disponiveis = ""
    for comb in permitido_adicionar:
        if any(comb) > 0:
            if combinacoes_disponiveis:
                combinacoes_disponiveis += "\nOU"
            for grupo, valor in enumerate(comb):
                if (
                    combinacoes_disponiveis != "Você *ainda pode* adicionar:\n- "
                    and combinacoes_disponiveis
                    and valor >= 1
                ):
                    logger.info(
                        f"To entrando aqui com {grupo}, {valor} e {combinacoes_disponiveis}"
                    )
                    if any(comb[0:grupo]) >= 1:
                        combinacoes_disponiveis += " + "
                    else:
                        combinacoes_disponiveis += "\n- "
                elif not combinacoes_disponiveis:
                    combinacoes_disponiveis += "Você *ainda pode* adicionar:\n- "

                # if all(comb[0:grupo]) == 0 and valor >= 1:
                #     combinacoes_disponiveis += "- "

                if valor > 1:
                    combinacoes_disponiveis += (
                        f"{valor} itens de material {GRUPOS_CODIGO_NOME[grupo+1]}"
                    )
                elif valor == 1:
                    combinacoes_disponiveis += (
                        f"{valor} item de material {GRUPOS_CODIGO_NOME[grupo+1]}"
                    )
                # if grupo > 0 and any(comb[grupo + 1 :]) > 0:
                #     combinacoes_disponiveis += " + "
            parameters["rebi_combinacoes_disponiveis_texto"] = combinacoes_disponiveis
            parameters["rebi_eligibilidade_mais_itens"] = True
    if combinacoes_disponiveis == "":
        parameters["rebi_eligibilidade_mais_itens"] = False

    parameters["rebi_material_nome"] = materiais_nomes
    parameters["rebi_material_quantidade"] = materiais_quantidade

    msg_regras = ""
    for key, value in materiais_novos.items():
        if msg_regras:
            msg_regras += ", "
        try:
            valor = int(float(value["informado"]))
        except ValueError:
            valor = value["informado"]
        msg_regras += f'{valor} {value["unidade"]} de {key.capitalize()}'
        # msg_regras += f'\nA unidade de medida de {key} considerada pela COMLURB é *{value["unidade"]}* e o *limite é de {value["permitido"]} {value["unidade"]}*.'

    msg = ""
    for key, value in materiais_todos.items():
        if msg:  # Add line breaks
            msg += "\n"
        try:
            valor = int(float(value["informado"]))
        except ValueError:
            valor = value["informado"]
        msg += f'\n- {valor} {value["unidade"]} de {key.capitalize()} (material {value["grupo"]})'

    parameters["rebi_material_informado_regras"] = msg_regras
    parameters["rebi_material_informado_descricao"] = msg

    return message, parameters


async def rebi_confirma_adicao_itens(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]

    parameters["rebi_material_nome_informado"] = copy(parameters["rebi_material_nome"])
    parameters["rebi_material_quantidade_informada"] = copy(parameters["rebi_material_quantidade"])

    return message, parameters


async def rebi_define_texto(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]

    parameters["rebi_coleta_material_1"] = (
        "Por favor, informe o tipo de material a ser removido e a quantidade de itens\n"
        "\n"
        "Exemplos:\n"
        "- 1 geladeira\n"
        "- 2 aspiradores de pó\n"
        "- 10 sacos de 20 litros de entulho.\n"
        "\n"
        "Informe apenas *1 tipo* de material por vez. Depois você poderá acrescentar mais tipos de material."
    )

    parameters["rebi_coleta_material_2"] = (
        "Por favor, informe outro tipo de material e a quantidade de itens.\n"
        "\n"
        "Lembre-se de informar apenas *1 tipo* de material por vez. Depois você poderá acrescentar mais tipos de material até o limite estabelecido.\n"
        "\n"
        "Caso não queira adicionar mais nenhum item, responda AVANÇAR."
    )

    parameters["rebi_coleta_material_nomatch_1"] = (
        "Desculpe, não entendi.\n\n" + parameters["rebi_coleta_material_1"]
    )
    parameters["rebi_coleta_material_nomatch_2"] = (
        "Desculpe, não entendi.\n\n" + parameters["rebi_coleta_material_2"]
    )

    return message, parameters


async def rebi_checa_item_duplicado(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]
    ultima_mensagem_usuario = request_data["text"]

    duplicado = {
        "cama": ["cama", "camas"],
        "colchao": [
            "colchão",
            "colchao",
            "colchoes",
            "colchões",
            "colxao",
            "colxoes",
            "colxões",
            "colxão",
        ],
        "armario": ["armario", "armário", "armario", "armários"],
        "telha": ["telha", "telhas"],
        "tanque": ["tanque", "tanques"],
        "vaso": ["vaso", "vasos"],
    }

    if any(keyword in ultima_mensagem_usuario for keyword in duplicado["cama"]):
        message = "Você quis dizer Cama de solteiro ou Cama de casal?\n\nPor favor, informe qual é o tipo de material e a quantidade."
    elif any(keyword in ultima_mensagem_usuario for keyword in duplicado["colchao"]):
        message = "Você quis dizer Colchão de solteiro ou Colchão de casal?\n\nPor favor, informe qual é o tipo de material e a quantidade."
    elif any(keyword in ultima_mensagem_usuario for keyword in duplicado["armario"]):
        message = "Você quis dizer Armário de alumínio de cozinha, Armário de 4 portas/guarda-roupa ou Armário pequeno até 3 portas/cômoda?\n\nPor favor, informe qual é o tipo de material e a quantidade."
    elif any(keyword in ultima_mensagem_usuario for keyword in duplicado["telha"]):
        message = "Você quis dizer Telha de alumínio, Telha de amianto ou Telha francesa/tijolo?\n\nPor favor, informe qual é o tipo de material e a quantidade."
    elif any(keyword in ultima_mensagem_usuario for keyword in duplicado["tanque"]):
        message = "Você quis dizer Tanque de lavagem de plástico/louça ou Tanque de concreto?\n\nPor favor, informe qual é o tipo de material e a quantidade."
    elif any(keyword in ultima_mensagem_usuario for keyword in duplicado["vaso"]):
        message = "Você quis dizer Vaso de planta com terra ou Vaso sanitário/bidê/lavatório?\n\nPor favor, informe qual é o tipo de material e a quantidade."
    else:
        pass

    return message, parameters

async def rebi_elegibilidade_endereco_abertura_chamado(request_data: dict) -> tuple[str, dict]:
    message = ""
    parameters = request_data["sessionInfo"]["parameters"]

    neighborhood_id = parameters.get("logradouro_id_bairro_ipp", None)
    street_id = parameters.get("logradouro_id_ipp", None)
    number = parameters.get("logradouro_numero", None)
    complement = parameters.get("endereco_complemento", None)
    if complement == "Não se aplica":
        complement = None

    # Um ano atrás
    min_date = (datetime.now() - timedelta(days=365))
    # Formatando a data no formato "YYYY-MM-DD"
    min_date = min_date.strftime("%Y-%m-%d")
    #min_date = '2022-12-05'

    try:
        logger.info(f"Buscando tickets do endereço no SGRC com ID_BAIRRO {neighborhood_id}, ID_LOGRADOURO {street_id}, NUMERO {number}, COMPLEMENTO {complement} e com data de abertura superior a {min_date}")
        address = {
            "neighborhood_id": neighborhood_id,
            "street_id": street_id,
            "number": number,
            "complement": complement,
            "min_date": min_date,
        }
        address_tickets = await get_address_protocols(address)
    except:  # noqa
        logger.error(f"Erro ao buscar informações desse endereço")
        parameters["rebi_elegibilidade_endereco_abertura_chamado"] = False
        parameters["rebi_elegibilidade_endereco_abertura_chamado_justificativa"] = "erro_desconhecido"
        return message, parameters

    logger.info(address_tickets)

    STATUS_TIPO_ABERTO = [
        "Aberto",
        "Em Andamento",
        "Em andamento privado",
        "Encaminhado à Comlurb - resíduo",
        "Pendente",
    ]

    address_tickets = address_tickets[0]
    for ticket in address_tickets["tickets"]:
        if str(ticket["classification"]) == "1607":
            if ticket["status"] in STATUS_TIPO_ABERTO:
                parameters["rebi_elegibilidade_endereco_abertura_chamado"] = False
                parameters[
                    "rebi_elegibilidade_endereco_abertura_chamado_justificativa"
                ] = "chamado_aberto"
                logger.info(f"Já existe um ticket aberto: {ticket}")
                return message, parameters
            else:
                hoje = datetime.now().date()
                data_fim = datetime.strptime(ticket["end_date"], "%Y-%m-%d").date()
                if (hoje - data_fim).days <= 12:
                    parameters["rebi_elegibilidade_endereco_abertura_chamado"] = False
                    parameters[
                        "rebi_elegibilidade_endereco_abertura_chamado_justificativa"
                    ] = "chamado_fechado_12_dias"
                    logger.info(
                        f"Um ticket desse subtipo foi fechado há {logger.info((hoje - data_fim).days)} dias, valor menor que 12: {ticket}"
                    )
                    return message, parameters

    # Se não, passou em todos os critérios
    parameters["rebi_elegibilidade_endereco_abertura_chamado"] = True

    return message, parameters
