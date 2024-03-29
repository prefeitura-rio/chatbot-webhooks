# -*- coding: utf-8 -*-
import base64
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Union
from itertools import cycle

import aiohttp
import geopandas as gpd
from async_googlemaps import AsyncClient
from google.oauth2 import service_account
from jellyfish import jaro_similarity
from loguru import logger
from prefeitura_rio.integrations.sgrc import Address, NewTicket, Requester
from prefeitura_rio.integrations.sgrc import async_new_ticket as async_sgrc_new_ticket
from shapely.geometry import Point

from chatbot_webhooks import config


async def get_ipp_street_code(parameters: dict) -> dict:
    THRESHOLD = 0.8
    logradouro_google = parameters["logradouro_nome"]
    logradouro_ipp = parameters["logradouro_nome_ipp"]
    logradouro_completo = f'{logradouro_google}, {parameters["logradouro_bairro_ipp"]}'

    # Corte a string para considerar apenas o nome da rua
    for i in range(0, len(logradouro_ipp)):
        if logradouro_ipp[i] not in "0123456789 -":
            logradouro_ipp = logradouro_ipp[i:]
            break

    logger.info(f"Logradouro IPP: {logradouro_ipp}")
    if (jaro_similarity(logradouro_google, logradouro_ipp) > THRESHOLD) and parameters[
        "logradouro_bairro_ipp"
    ] != " ":
        logger.info(
            f"Similaridade alta o suficiente: {jaro_similarity(logradouro_google, logradouro_ipp)}"
        )
        geocode_logradouro_ipp_url = str(
            "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Geocode/Geocode_Logradouros_WGS84/GeocodeServer/findAddressCandidates?"
            + f"Address={logradouro_completo}&Address2=&Address3=&Neighborhood=&City=&Subregion=&Region=&Postal=&PostalExt=&CountryCode=&SingleLine=&outFields=cl"
            + "&maxLocations=&matchOutOfRange=true&langCode=&locationType=&sourceCountry=&category=&location=&searchExtent=&outSR=&magicKey=&preferredLabelValues=&f=pjson"
        )
        logger.info(f"Geocode IPP URL: {geocode_logradouro_ipp_url}")
        return parameters
    else:
        if jaro_similarity(logradouro_google, logradouro_ipp) < THRESHOLD:
            logger.info(
                f"logradouro_nome retornado pelo Google significantemente diferente do retornado pelo IPP. Threshold: {jaro_similarity(logradouro_google, logradouro_ipp)}"
            )
            if parameters["logradouro_bairro_ipp"] == " ":
                logger.info(
                    "Além dos endereços serem muito diferentes, não há bairro IPP. Então vou considerar o bairro do Google."
                )
                logradouro_completo = f'{logradouro_google}, {parameters.get("logradouro_bairro", parameters["logradouro_bairro_ipp"])}'
        elif parameters["logradouro_bairro_ipp"] == " ":
            logger.info(
                f'Bairro IPP não identificado. Valor Bairro IPP: {parameters["logradouro_bairro_ipp"]}. Vou considerar o do Google.'
            )
            logger.info(
                "Atualizando o logradouro que vai ser geolocalizado para considerar o logradouro_ipp em vez do Google"
            )
            logradouro_completo = f'{logradouro_ipp}, {parameters.get("logradouro_bairro", parameters["logradouro_bairro_ipp"])}'
        # Call IPP api
        geocode_logradouro_ipp_url = str(
            "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Geocode/Geocode_Logradouros_WGS84/GeocodeServer/findAddressCandidates?"
            + f"Address={logradouro_completo}&Address2=&Address3=&Neighborhood=&City=&Subregion=&Region=&Postal=&PostalExt=&CountryCode=&SingleLine=&outFields=cl"
            + "&maxLocations=&matchOutOfRange=true&langCode=&locationType=&sourceCountry=&category=&location=&searchExtent=&outSR=&magicKey=&preferredLabelValues=&f=pjson"
        )
        logger.info(f"Geocode IPP URL: {geocode_logradouro_ipp_url}")

        async with aiohttp.ClientSession() as session:
            async with session.request(
                "GET",
                geocode_logradouro_ipp_url,
            ) as response:
                data = await response.json(content_type="text/plain")
        try:
            candidates = list(data["candidates"])
            logradouro_codigo = None
            logradouro_real = None

            if parameters["logradouro_bairro_ipp"] == " ":
                best_distance = 1000000000
                logger.info(
                    f'Não foi identificado um bairro, então o logradouro escolhido vai ser o mais próximo do lat/long retornado pelo Google, que é lat:{parameters["logradouro_latitude"]} long:{parameters["logradouro_longitude"]}'
                )
                for candidato in candidates:
                    distance = haversine_distance(
                        parameters["logradouro_latitude"],
                        parameters["logradouro_longitude"],
                        candidato["location"]["y"],
                        candidato["location"]["x"],
                    )
                    if (
                        distance < best_distance and "," in candidato["address"]
                    ):  # Só considera logradouros com bairro
                        logger.info(
                            f'Logradouro mais próximo encontrado: {candidato["address"]} com distância de {distance}'
                        )
                        best_distance = distance
                        logradouro_codigo = candidato["attributes"]["cl"]
                        logradouro_real = candidato["address"]
                logger.info(
                    f"Logradouro no IPP com maior semelhança: {logradouro_real}, cl: {logradouro_codigo}, distância: {best_distance} metros"
                )
            else:
                best_similarity = 0
                logger.info(
                    "Já existe um bairro, então o logradouro vai ser selecionado de acordo similaridade de texto"
                )
                for candidato in candidates:
                    similarity = jaro_similarity(candidato["address"], logradouro_completo)
                    if (
                        similarity > best_similarity and "," in candidato["address"]
                    ):  # Só considera logradouros com bairro
                        best_similarity = similarity
                        logradouro_codigo = candidato["attributes"]["cl"]
                        logradouro_real = candidato["address"]
                logger.info(
                    f"Logradouro no IPP com maior semelhança: {logradouro_real}, cl: {logradouro_codigo}, semelhança: {best_similarity}"
                )
            logger.info(
                f"Logradouro encontrado no Google, com bairro do IPP: {logradouro_completo}"
            )

            parameters["logradouro_id_ipp"] = logradouro_codigo
            parameters["logradouro_nome_ipp"] = logradouro_real.split(",")[0]
            try:
                best_candidate_bairro_nome_ipp = logradouro_real.split(",")[1][1:]
            except:  # noqa: E722
                logger.info("Logradouro no IPP com maior semelhança não possui bairro no nome")
                parameters["logradouro_bairro_ipp"] = None

            if (
                jaro_similarity(best_candidate_bairro_nome_ipp, parameters["logradouro_bairro_ipp"])
                > THRESHOLD
            ):
                logger.info(
                    f"Similaridade entre bairro atual e bairro do Logradouro no IPP com maior semelhança é alta o suficiente: {jaro_similarity(best_candidate_bairro_nome_ipp, parameters['logradouro_bairro_ipp'])}"
                )
                return parameters
            else:
                # Se o bairro do endereço com maior similaridade for diferente do que coletamos usando geolocalização,
                # pegamos o codigo correto buscando o nome do bairro desse endereço na base do IPP e pegando o codigo correspondente
                logger.info("Foi necessário atualizar o bairro")
                logger.info(
                    f'Bairro obtido anteriormente com geolocalização: {parameters["logradouro_bairro_ipp"]}'
                )
                url = get_integrations_url("neighborhood_id")

                payload = json.dumps({"name": best_candidate_bairro_nome_ipp})

                key = config.CHATBOT_INTEGRATIONS_KEY

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                }

                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        "POST", url, headers=headers, data=payload
                    ) as response:
                        response_json = await response.json(content_type=None)
                        parameters["logradouro_id_bairro_ipp"] = response_json["id"]
                        parameters["logradouro_bairro_ipp"] = response_json["name"]

                logger.info(
                    f'Bairro obtido agora com busca por similaridade: {parameters["logradouro_bairro_ipp"]}'
                )
        except:  # noqa: E722
            logger.info("Correspondência não exata entre endereço no Google e no IPP")
            return parameters


async def address_contains_street_number(address: str) -> bool:
    left_text = address.partition("Rio de Janeiro - RJ")[0]
    return bool(re.search(r"\d", left_text))


async def address_find_street_number(address: str) -> str:
    left_text = address.partition("Rio de Janeiro - RJ")[0]
    lista_numeros = re.findall(r"\d+", left_text)
    return lista_numeros[-1]


def fix_unicode(text: str) -> str:
    """
    This function fixes the unicode characters in the text that are not escaped.
    """
    regex = re.compile(r"u00([a-fA-F0-9]{2})")

    def replace(match):
        return chr(int(match.group(1), 16))

    return regex.sub(replace, text)


async def get_credentials_from_env() -> service_account.Credentials:
    """
    Gets credentials from env vars
    """
    info: dict = json.loads(base64.b64decode(config.GCP_SERVICE_ACCOUNT))
    return service_account.Credentials.from_service_account_info(info)


async def get_ipp_info(parameters: dict) -> bool:
    geocode_ipp_url = str(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Geocode/Geocode_Logradouros_WGS84/GeocodeServer/reverseGeocode?"  # noqa
        + f'location={parameters["logradouro_longitude"]}%2C{parameters["logradouro_latitude"]}'
        + "&langCode=&locationType=&featureTypes=&outSR=&preferredLabelValues=&f=pjson"
    )

    logger.info(f"Geocode IPP URL: {geocode_ipp_url}")

    async with aiohttp.ClientSession() as session:
        async with session.request(
            "GET",
            geocode_ipp_url,
        ) as response:
            data = await response.json(content_type="text/plain")

    try:
        parameters["logradouro_id_ipp"] = str(data["address"]["CL"])
        parameters["logradouro_id_bairro_ipp"] = str(data["address"]["COD_Bairro"])
        parameters["logradouro_nome_ipp"] = str(data["address"]["ShortLabel"])
        parameters["logradouro_bairro_ipp"] = str(data["address"]["Neighborhood"])

        logger.info(f'Codigo bairro IPP obtido: {parameters["logradouro_id_bairro_ipp"]}')
        logger.info(f'Nome bairro IPP obtido: {parameters["logradouro_bairro_ipp"]}')
    except:  # noqa: E722
        logger.info("Falha na API do IPP que identifica endereço através de lat/long.")
        logger.info("Retorno abaixo")
        logger.info(data)
        logger.info(
            "Inicializando as variáveis `logradouro_id_bairro_ipp` = 0 e `logradouro_nome_ipp` = ` `, \
            para que os próximos códigos de identificação de informações do IPP sejam executados"
        )
        parameters["logradouro_id_bairro_ipp"] = "0"
        parameters["logradouro_nome_ipp"] = " "

    try:
        ##########
        # O código abaixo estava causando mais problemas que ajudando, pois nem sempre o bairro identificado pelo Google
        # é o mesmo bairro cadastrado no IPP, e o SGRC só aceita o IPP. Então é melhor tentar achar o bairro por lá mesmo...
        ##########
        # # Se o codigo_bairro retornado for 0, pegamos o codigo correto buscando o nome do bairro informado pelo Google
        # # na base do IPP e pegando o codigo correspondente
        # if parameters["logradouro_id_bairro_ipp"] == "0":
        #     logger.info(
        #         "Situação dos parâmetros da conversa antes de chamar o endpoint neighborhood_id"
        #     )
        #     logger.info(parameters)
        #     url = get_integrations_url("neighborhood_id")
        #     payload = json.dumps(
        #         {
        #             "name": parameters["logradouro_bairro"]
        #             if "logradouro_bairro" in parameters
        #             else ""
        #         }
        #     )

        #     key = config.CHATBOT_INTEGRATIONS_KEY

        #     headers = {
        #         "Content-Type": "application/json",
        #         "Authorization": f"Bearer {key}",
        #     }
        #     async with aiohttp.ClientSession() as session:
        #         async with session.request("POST", url, headers=headers, data=payload) as response:
        #             json_response = await response.json(content_type=None)
        #             parameters["logradouro_id_bairro_ipp"] = json_response["id"]
        #             parameters["logradouro_bairro_ipp"] = json_response["name"]
        #     # Caso mesmo assim um bairro não tenha sido encontrado, define temporariamente um valor não nulo
        #     # para o bairro, de modo que o nome do bairro seja encontrado dentro da função get_ipp_street_code
        if not parameters["logradouro_bairro_ipp"] or parameters["logradouro_id_bairro_ipp"] == "0":
            # logger.info("neighborhood_id foi chamado e nenhum bairro foi encontrado")
            logger.info("Geolocalização do IPP não retornou bairro")
            parameters["logradouro_bairro_ipp"] = " "

        # logger.info(
        #     f"Após chamar o endpoint neighborhood_id o valor do logradouro_bairro_ipp é: {parameters['logradouro_bairro_ipp']}"
        # )

        # Checa se o nome de logradouro informado pelo Google é similar o suficiente do informado pelo IPP
        # Se forem muito diferentes, chama outra api do IPP para achar um novo logradouro e substitui o
        # logradouro_id_ipp pelo correspondente ao novo logradouro mais similar ao do Google
        logger.info("Chamando função que identifica o logradouro do IPP por similaridade de texto")
        parameters = await get_ipp_street_code(parameters)

        return True
    except:  # noqa
        logger.info(
            "Erro em alguma das funções: (get_ipp_street_code, get_integrations_url(`neighborhood_id`)"
        )
        parameters["abertura_manual"] = True
        return False


def get_integrations_url(endpoint: str) -> str:
    """
    Returns the URL of the endpoint in the integrations service.
    """
    base_url = config.CHATBOT_INTEGRATIONS_URL
    if base_url.endswith("/"):
        base_url = base_url[:-1]
    if endpoint.startswith("/"):
        endpoint = endpoint[1:]
    logger.info(f"Base URL: {base_url}")
    logger.info(f"Endpoint: {endpoint}")
    logger.info(f"URL: {base_url}/{endpoint}")
    return f"{base_url}/{endpoint}"


async def get_user_info(cpf: str) -> dict:
    """
    Returns user info from CPF.

    Args:
        cpf (str): CPF to be searched.

    Returns:
        dict: User info in the following format:
            {
                "id": 12345678,
                "name": "Fulano de Tal",
                "cpf": "12345678911",
                "email": "fulano@detal.com",
                "phones": [
                    "21999999999",
                ],
            }
    """
    url = get_integrations_url("person")
    key = config.CHATBOT_INTEGRATIONS_KEY
    payload = {"cpf": cpf}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                "POST", url, headers=headers, data=json.dumps(payload)
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        return data
    except Exception as exc:  # noqa
        logger.error(exc)
        raise Exception(f"Failed to get user info: {exc}") from exc


async def google_find_place(address: str, parameters: dict) -> bool:
    """
    Uses Google Maps API to get the formatted address using find_place and then call
    google_geolocator function
    """
    async with aiohttp.ClientSession() as maps_session:
        client = AsyncClient(maps_session, key=config.GMAPS_API_TOKEN)
        find_place_result = await client.find_place(
            address,
            "textquery",
            fields=["formatted_address", "name"],
            location_bias="rectangle:-22.74744540190159, -43.098580713057416|-23.100575987851833, -43.79779077663037",  # noqa
            language="pt",
        )

    if find_place_result["status"] == "OK":
        parameters["logradouro_ponto_referencia_identificado"] = find_place_result["candidates"][0][
            "name"
        ]
        logger.info("find_place OK")
        logger.info("FINDPLACE RESULT ABAIXO")
        logger.info(find_place_result)
        logger.info("-----")
        if await address_contains_street_number(
            find_place_result["candidates"][0]["formatted_address"]
        ):
            logger.info("Contém número da rua")
            logger.info(
                f'Input geolocator: "{find_place_result["candidates"][0]["formatted_address"]}"'
            )
            parameters["logradouro_numero_identificado_google"] = True
            return await google_geolocator(
                find_place_result["candidates"][0]["formatted_address"], parameters
            )
        else:
            logger.info("Não contém número da rua")
            parameters["logradouro_numero_identificado_google"] = False
            endereco_completo = f"{find_place_result['candidates'][0]['name']}, {find_place_result['candidates'][0]['formatted_address']}"  # noqa
            logger.info(f'Input geolocator: "{endereco_completo}"')
            return await google_geolocator(endereco_completo, parameters)
    else:
        logger.warning("find_place NOT OK")
        return False


async def google_geolocator(address: str, parameters: dict) -> bool:
    """
    Uses Google Maps API to get the formatted address using geocode
    """
    ACCEPTED_LOGRADOUROS = [
        "route",
        "establishment",
        "street_address",
        "town_square",
        "point_of_interest",
    ]

    async with aiohttp.ClientSession() as maps_session:
        client = AsyncClient(maps_session, key=config.GMAPS_API_TOKEN)
        geocode_result = await client.geocode(address)

    logger.info("GEOCODE RESULT ABAIXO")
    logger.info(geocode_result)
    logger.info("-----")

    # Retornar None caso não encontre nada
    if len(geocode_result) == 0:
        return False
        # raise ValueError(f"Address {address} not found")

    # Caso não identifique o endereço pelo nome, obtê-lo ao fazer o geocode reverso pelo lat,lng
    # obtido na primeira iteração
    if geocode_result[0]["formatted_address"] is None:
        logger.info("no geocode result")
        lat = geocode_result[0]["geometry"]["location"]["lat"]
        lng = geocode_result[0]["geometry"]["location"]["lng"]
        async with aiohttp.ClientSession() as maps_session:
            client = AsyncClient(maps_session, key=config.GMAPS_API_TOKEN)
            geocode_result = await client.reverse_geocode((lat, lng))

    # Ache o primeiro resultado que possui o nome do logradouro
    nome_logradouro_encontrado = False
    logger.info("Procurando resultado do geocode com nome do logradouro")
    for posicao, resultado in enumerate(geocode_result):
        logger.info(f"Item da posição {posicao}:")
        logger.info(resultado)
        for item in resultado["address_components"]:
            if [i for i in ACCEPTED_LOGRADOUROS if i in item["types"]]:
                parameters["logradouro_nome"] = item["long_name"]
                nome_logradouro_encontrado = True
                break
        if nome_logradouro_encontrado:
            break

    # Verifica se o Google conseguiu achar um logradouro
    if not nome_logradouro_encontrado:
        logger.info("Google não conseguiu encontrar um logradouro válido")
        return False

    logger.info("O item escolhido foi:")
    logger.info(resultado)

    # Procure as outras informações nesse resultado que possui o nome do logradouro
    logger.info("Itens dentro desse resultado:")
    # google_found_number = False
    # google_found_zip_code = False
    for item in resultado["address_components"]:
        logger.info(f'O item é "{item["long_name"]}"')
        logger.info(item["types"])
        if "street_number" in item["types"]:
            # google_found_number = True
            parameters["logradouro_numero"] = item["long_name"]
        elif [i for i in ACCEPTED_LOGRADOUROS if i in item["types"]]:
            parameters["logradouro_nome"] = item["long_name"]
        elif "sublocality" in item["types"] or "sublocality_level_1" in item["types"]:
            parameters["logradouro_bairro"] = item["long_name"]
        elif "postal_code" in item["types"]:
            # google_found_zip_code = True
            parameters["logradouro_cep"] = item["long_name"]
            cep_formatado = parameters["logradouro_cep"].replace("-", "")
            logger.info(f"O tamanho do CEP é de {len(cep_formatado)} caracteres")
            if len(cep_formatado) < 8:
                parameters["logradouro_cep"] = None
                logger.info("CEP deixado em branco, já que tem tamanho menor que 8")
        elif "administrative_area_level_2" in item["types"]:
            parameters["logradouro_cidade"] = item["long_name"]
        elif "administrative_area_level_1" in item["types"]:
            parameters["logradouro_estado"] = item["short_name"]

    # VERSÃO PONTO DE REFERÊNCIA EQUIVALENTE A NÚMERO #
    # Como agora aceitamos só o nome da rua antes de geolocalizar, existem ruas com mais de um CEP #
    # # If we don't find neither the number nor the zip code, we can't proceed
    # if not google_found_number and not google_found_zip_code:
    #     return False

    parameters["logradouro_latitude"] = resultado["geometry"]["location"]["lat"]
    parameters["logradouro_longitude"] = resultado["geometry"]["location"]["lng"]

    # Verifica se o endereço está fora do Rio de Janeiro, se for o caso, retorna endereço inválido
    # e Dialogflow vai avisar que só atendemos a cidade do Rio
    if "logradouro_cidade" in parameters:
        if parameters["logradouro_cidade"] != "Rio de Janeiro":
            logger.info("O município do endereço é diferente de Rio de Janeiro")
            parameters["logradouro_fora_do_rj"] = True
            return False
    else:
        logger.info("Não foi identificado um município para esse endereço")
        t0 = time.time()
        shape_rj = gpd.read_file(Path(__file__).parent.parent.parent / "shape_rj.geojson").iloc[0][
            "geometry"
        ]
        point = Point(
            float(parameters["logradouro_longitude"]),
            float(parameters["logradouro_latitude"]),
        )
        if not shape_rj.contains(point):
            logger.info("O endereço identificado está fora do Rio de Janeiro")
            logger.info(
                f"Demorou {int(time.time() - t0)} segundos para checar se o ponto está no shape"
            )
            parameters["logradouro_fora_do_rj"] = True
            return False
        logger.info(
            f"Demorou {int(time.time() - t0)} segundos para checar se o ponto está no shape. E está."
        )

    # VERSÃO PONTO DE REFERÊNCIA EQUIVALENTE A NÚMERO #
    # # Caso já tenha sido identificado que existe numero de logradouro no endereço retornado pelo find_place, mas
    # # o geolocator não tenha conseguido retorná-lo, raspamos a string para achar esse número.
    # if "logradouro_numero_identificado_google" in parameters:
    #     if (
    #         parameters["logradouro_numero_identificado_google"]
    #         and not parameters["logradouro_numero"]
    #     ):
    #         parameters["logradouro_numero"] = await address_find_street_number(address)
    #     parameters["logradouro_numero_identificado_google"] = None
    # else:
    #     pass

    # Pega a parcela do número que está antes do `.`, caso exista um `.`
    try:
        parameters["logradouro_numero"] = parameters["logradouro_numero"].split(".")[0]
    except:  # noqa
        logger.info("logradouro_numero: falhou ao tentar pegar a parcela antes do `.`")

    return True


async def form_info_update(parameter_list: list, parameter_name: str, parameter_value: any) -> list:
    indice = -1
    for i in range(0, len(parameter_list)):
        if parameter_list[i]["displayName"] == parameter_name:
            indice = i
            break
    if indice == -1:
        raise ValueError(f"Parameter {parameter_name} was not found in form parameter list")
    parameter_list[indice]["value"] = parameter_value

    return parameter_list


def mask_email(email: str, mask_chacacter: str = "x") -> str:
    """
    Mascara um e-mail para proteção do dado pessoal.

    Args:
        email (str): E-mail a ser mascarado
        mask_chacacter (str): Caracter a ser usado para mascarar o e-mail.

    Exemplos:
    >>> mask_email('admin@example.com')
    'a****@e******.com'
    >>> mask_email('fulanodetal@meuemail.com.br')
    'f**********@m********.com.br'
    """
    email = email.split("@")
    username = email[0]
    domain = email[1]
    username = username[0] + mask_chacacter * (len(username) - 2) + username[-1]
    domain_parts = domain.split(".")
    domain = ""
    for i in range(0, len(domain_parts) - 1):
        domain += domain_parts[i][0] + mask_chacacter * (len(domain_parts[i]) - 1) + "."
    domain = domain + ".".join(domain_parts[len(domain_parts) - 1 :])  # noqa
    return f"{username}@{domain}"


async def new_ticket(
    classification_code: str,
    description: str,
    address: Address = None,
    date_time: Union[datetime, str] = None,
    requester: Requester = None,
    occurrence_origin_code: str = "28",
    specific_attributes: Dict[str, Any] = None,
) -> NewTicket:
    """
    Creates a new ticket.

    Args:
        classification_code (str): The classification code.
        description (str): The description of the occurrence.
        address (Address): The address of the occurrence.
        date_time (Union[datetime, str], optional): The date and time of the occurrence. When
            converted to string, it must be in the following format: "%Y-%m-%dT%H:%M:%S". Defaults
            to `None`, which will be replaced by the current date and time.
        requester (Requester, optional): The requester information. Defaults to `None`, which will
            be replaced by an empty `Requester` object.
        occurrence_origin_code (str, optional): The occurrence origin code (e.g. "13" for
            "Web App"). Defaults to "28".

    Returns:
        NewTicket: The new ticket.

    Raises:
        BaseSGRCException: If an unexpected exception occurs.
        SGRCBusinessRuleException: If the request violates a business rule.
        SGRCDuplicateTicketException: If the request tries to create a duplicate ticket.
        SGRCEquivalentTicketException: If the request tries to create an equivalent ticket.
        SGRCInternalErrorException: If the request causes an internal error.
        SGRCInvalidBodyException: If the request body is invalid.
        SGRCMalformedBodyException: If the request body is malformed.
        ValueError: If any of the arguments is invalid.
    """
    try:
        new_ticket: NewTicket = await async_sgrc_new_ticket(
            classification_code=classification_code,
            description=description,
            address=address,
            date_time=date_time,
            requester=requester,
            occurrence_origin_code=occurrence_origin_code,
            specific_attributes=specific_attributes,
        )
        await send_discord_message(
            message=(
                "Novo chamado criado:\n"
                f"- Protocolo: {new_ticket.protocol_id}\n"
                f"- Chamado: {new_ticket.ticket_id}"
            ),
            webhook_url=config.DISCORD_WEBHOOK_NEW_TICKET,
        )
        return new_ticket
    except Exception as exc:  # noqa
        raise exc


async def send_discord_message(message: str, webhook_url: str) -> bool:
    """
    Envia uma mensagem para um canal do Discord através de um webhook.

    Parâmetros:
        message (str): Mensagem a ser enviada.
        webhook_url (str): URL do webhook.

    Retorno:
        bool:
            - Verdadeiro, caso a mensagem seja enviada com sucesso;
            - Falso, caso contrário.
    """
    try:
        data = {"content": message}
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=data) as response:
                if response.status == 204:
                    return True
                else:
                    return False
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem para o Discord: {e}")
        return False


def validate_CPF(parameters: dict, form_parameters_list: list = []) -> bool:
    """Efetua a validação do CPF, tanto formatação quando dígito verificadores.

    Parâmetros:
        cpf (str): CPF a ser validado

    Retorno:
        bool:
            - Falso, quando o CPF não possuir o formato 999.999.999-99;
            - Falso, quando o CPF não possuir 11 caracteres numéricos;
            - Falso, quando os dígitos verificadores forem inválidos;
            - Verdadeiro, caso contrário.

    Exemplos:

    >>> validate_CPF('529.982.247-25')
    True
    >>> validate_CPF('52998224725')
    False
    >>> validate_CPF('111.111.111-11')
    False
    """

    cpf = parameters["usuario_cpf"]

    # Obtém apenas os números do CPF, ignorando pontuações
    numbers = [int(digit) for digit in cpf if digit.isdigit()]

    # Verifica se o CPF possui 11 números ou se todos são iguais:
    if len(numbers) != 11 or len(set(numbers)) == 1:
        return False

    # Validação do primeiro dígito verificador:
    sum_of_products = sum(a * b for a, b in zip(numbers[0:9], range(10, 1, -1)))
    expected_digit = (sum_of_products * 10 % 11) % 10
    if numbers[9] != expected_digit:
        return False

    # Validação do segundo dígito verificador:
    sum_of_products = sum(a * b for a, b in zip(numbers[0:10], range(11, 1, -1)))
    expected_digit = (sum_of_products * 10 % 11) % 10
    if numbers[10] != expected_digit:
        return False

    cpf_formatado = "".join([str(item) for item in numbers])
    parameters["usuario_cpf"] = cpf_formatado
    # form_parameters_list = await form_info_update(
    #     form_parameters_list, "usuario_cpf", cpf_formatado
    # )

    return True


def validate_CPF2(numbers):
    # Validação do primeiro dígito verificador:
    sum_of_products = sum(a * b for a, b in zip(numbers[:9], range(10, 1, -1)))
    expected_digit = (sum_of_products * 10) % 11 % 10
    if numbers[9] != expected_digit:
        return False

    # Validação do segundo dígito verificador:
    sum_of_products = sum(a * b for a, b in zip(numbers[:10], range(11, 1, -1)))
    expected_digit = (sum_of_products * 10) % 11 % 10
    if numbers[10] != expected_digit:
        return False

    return True


def validate_CNPJ(cnpj: str) -> bool:
    LENGTH_CNPJ = 14
    if len(cnpj) != LENGTH_CNPJ:
        return False

    if cnpj in (c * LENGTH_CNPJ for c in "1234567890"):
        return False

    cnpj_r = cnpj[::-1]
    for i in range(2, 0, -1):
        cnpj_enum = zip(cycle(range(2, 10)), cnpj_r[i:])
        dv = sum(map(lambda x: int(x[1]) * x[0], cnpj_enum)) * 10 % 11
        if cnpj_r[(i - 1) : i] != str(dv % 10):  # noqa
            return False

    return True


def validate_cpf_cnpj(parameters: dict, form_parameters_list: list = []) -> bool:
    """Efetua a validação de CPF ou CNPJ."""

    # Obtém apenas os números do documento, ignorando pontuações
    documento = parameters["usuario_cpf"]
    numbers = [int(digit) for digit in documento if digit.isdigit()]
    # Verifica se o documento possui 11 ou 14 números
    if len(numbers) not in [11, 14] or len(set(numbers)) == 1:
        return False

    if len(numbers) == 11:  # CPF
        logger.info("É um CPF")
        return validate_CPF(parameters)

    elif len(numbers) == 14:  # CNPJ
        logger.info("É um CNPJ")
        return validate_CNPJ("".join(map(str, numbers)))

    return False


def validate_email(parameters: dict, form_parameters_list: list = []) -> bool:
    """
    Valida se a escrita do email está correta ou não,
    i.e., se está conforme o padrão dos nomes de email e
    do domínio.
    Retorna, True: se estiver ok! E False: se não.

    Ex: validate_email("email@dominio")
    """
    email = parameters["usuario_email"]
    regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(regex, email) is not None


def validate_name(parameters: dict, form_parameters_list: list = []) -> bool:
    """
    Valida se a string informada tem nome e um sobrenome válido,
    ou seja, possui um espaço (' ') no meio da string
    e tem um sobrenome com no mínimo 2 caracteres.
    Retorna, True: se estiver ok! E False: se não.

    Ex: validade_name("gabriel gazola")
    """
    nome = parameters["usuario_nome_cadastrado"]
    logger.info(nome)
    try:
        nome_quebrado = nome.split(" ")
        logger.info(nome_quebrado)
        if len(nome_quebrado) >= 2 and any(len(element) >= 2 for element in nome_quebrado[1:]):
            return True
        else:
            return False
    except:  # noqa: E722
        logger.info(
            f"Parâmetro usuario_nome_cadastrado tem valor: {nome} e tipo {type(nome)}. Não foi possível fazer a validação, logo, inválido."
        )
        return False


async def internal_request(
    url: str,
    method: str = "GET",
    request_kwargs: dict = {},
) -> aiohttp.ClientResponse:
    """
    Uses chatbot-integrations for making requests through the internal network.

    Args:
        url (str): The URL to be requested.
        method (str, optional): The HTTP method. Defaults to "GET".
        request_kwargs (dict, optional): The request kwargs. Defaults to {}.

    Returns:
        aiohttp.ClientResponse: The response object.
    """
    integrations_url = get_integrations_url("request")
    payload = json.dumps(
        {
            "url": url,
            "method": method,
            "request_kwargs": request_kwargs,
        }
    )
    key = config.CHATBOT_INTEGRATIONS_KEY
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.request(
            "POST", integrations_url, headers=headers, data=payload
        ) as response:
            return await response.json(content_type=None)


async def pgm_api(endpoint: str = "", data: dict = {}) -> dict:
    # Pegando o token de autenticação
    auth_response = await internal_request(
        url=config.CHATBOT_PGM_API_URL + "/security/token",
        method="POST",
        request_kwargs={
            "verify": False,
            "headers": {},
            "data": {
                "grant_type": "password",
                "Consumidor": "chatbot",
                "ChaveAcesso": config.CHATBOT_PGM_ACCESS_KEY,
            },
        },
    )
    if "access_token" not in auth_response:
        raise Exception("Failed to get PGM access token")
    token = f'Bearer {auth_response["access_token"]}'
    logger.info("Token de autenticação obtido com sucesso")

    # Fazer uma solicitação POST
    response = await internal_request(
        url=config.CHATBOT_PGM_API_URL + f"/{endpoint}",
        method="POST",
        request_kwargs={
            "verify": False,
            "headers": {"Authorization": token},
            "data": data,
        },
    )

    # Imprimir o conteúdo das respostas
    logger.info("Resposta da solicitação POST:")
    logger.info(response)

    if response is None:
        logger.info(
            "A API não retornou nada. Valor esperado para o endpoint de cadastro de usuários."
        )
        return {"success": True}
    elif response["success"]:
        logger.info("A API retornou registros.")
        return response["data"]
    else:
        logger.info(
            f'Algo deu errado durante a solicitação, segue justificativa: {response["data"][0]["value"]}'
        )
        motivos = ""
        for item in response["data"]:
            if motivos:
                motivos += "\n\n"
            motivos += item["value"]
        return {"erro": True, "motivos": motivos}

    # guias_protestadas = response_json["data"]

    # for i, guia in enumerate(guias_protestadas):
    #     print(i+1)
    #     print(guia)
    #     print("/n/n")


async def get_user_protocols(person_id: str) -> dict:
    """
    Returns user protocols from person_id.

    Args:
        person_id (str): id to be searched.

    Returns:
        dict
    """
    url = get_integrations_url("protocols")
    key = config.CHATBOT_INTEGRATIONS_KEY
    payload = {"person_id": person_id}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                "POST", url, headers=headers, data=json.dumps(payload)
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        return data
    except Exception as exc:  # noqa
        logger.error(exc)
        raise Exception(f"Failed to get user protocols: {exc}") from exc


async def rebi_combinacoes_permitidas(combinação_usuario: list) -> tuple[bool, str, list]:
    COMBINACOES_VALIDAS = [
        [6, 0, 0],
        [5, 1, 0],
        [0, 2, 0],
        [0, 2, 1],
        [0, 0, 1],
    ]

    # rotulos = ["pequenos", "grandes", "especiais"]
    # unidades = ["unidades", "unidades", "unidades"]

    combinacoes_validas = []

    for combinação_valida in COMBINACOES_VALIDAS:
        permitido = True
        justificativa = ""

        for i in range(len(combinação_valida)):
            if combinação_usuario[i] > combinação_valida[i]:
                permitido = False
                justificativa = ""

                if all(
                    (user_val > 0) == (valid_val > 0)
                    for user_val, valid_val in zip(combinação_usuario, combinação_valida)
                ):
                    if i == 0:
                        justificativa += (
                            "O limite para itens pequenos é de 6 items distintos ao solicitar só itens pequenos."
                            " Quando solicitados juntamente a itens grandes, o limite é de 5 itens pequenos e 1 grande."
                        )
                    elif i == 1:
                        justificativa += (
                            "O limite para itens grandes é de 2 items distintos ao solicitar só itens grandes ou com mais 1 item especial. "
                            "Quando solicitados juntamente a itens pequenos, o limite é de 5 itens pequenos e 1 grande."
                        )
                    elif i == 2:
                        justificativa += (
                            "O limite para itens especiais é de 1 item e não podem ser solicitados juntamente a itens pequenos, apenas grandes."
                            " Nesse caso o limite é de 2 itens grandes e 1 especial."
                        )
                elif combinação_usuario[0] > 0 and combinação_usuario[2] > 0:
                    justificativa += (
                        "Itens pequenos não podem ser solicitados juntamente à itens especiais."
                    )

                break

        if permitido:
            permitido_adicionar = [
                (valid_val - user_val)
                for user_val, valid_val in zip(combinação_usuario, combinação_valida)
            ]
            combinacoes_validas.append(permitido_adicionar)

    if combinacoes_validas:
        return True, "", combinacoes_validas
    else:
        return False, justificativa, [0, 0, 0]


def haversine_distance(lat1, lon1, lat2, lon2):
    # Converte strings para floats, se necessário
    lat1 = float(lat1) if isinstance(lat1, str) else lat1
    lon1 = float(lon1) if isinstance(lon1, str) else lon1
    lat2 = float(lat2) if isinstance(lat2, str) else lat2
    lon2 = float(lon2) if isinstance(lon2, str) else lon2

    # Raio médio da Terra em quilômetros
    R = 6371.0

    # Converte as coordenadas de graus para radianos
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Diferenças entre as coordenadas
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Fórmula de Haversine
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Distância em quilômetros
    distance_km = R * c

    # Distância em metros
    distance_m = distance_km * 1000
    return distance_m


async def get_address_protocols(address_data: dict) -> dict:
    """
    Returns user protocols from person_id.

    Args:
        address_data (dict): address to be searched.

    Returns:
        dict: User info in the following format:
            {
                "id": 12345678,
                "name": "Fulano de Tal",
                "cpf": "12345678911",
                "email": "fulano@detal.com",
                "phones": [
                    "21999999999",
                ],
            }
    """
    url = get_integrations_url("address_protocols")
    key = config.CHATBOT_INTEGRATIONS_KEY

    try:
        neighborhood_id = int(address_data["neighborhood_id"])
    except:  # noqa
        logger.info("Failed to convert neighborhood_id to int. Defaulted to 0 instead")
        neighborhood_id = 0

    try:
        street_id = int(address_data["street_id"])
    except:  # noqa
        logger.info("Failed to convert street_id to int. Defaulted to 0 instead")
        street_id = 0

    payload = {
        "neighborhood_id": neighborhood_id,
        "street_id": street_id,
        "number": address_data["number"],
        "complement": address_data["complement"],
        "min_date": address_data["min_date"],
    }
    logger.info(payload)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                "POST", url, headers=headers, data=json.dumps(payload)
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        return data
    except Exception as exc:  # noqa
        logger.error(exc)
        raise Exception(f"Failed to get address protocols: {exc}") from exc
