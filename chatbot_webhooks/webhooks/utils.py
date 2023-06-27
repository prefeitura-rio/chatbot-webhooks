# -*- coding: utf-8 -*-
import base64
import json
import re

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from google.oauth2 import service_account
import googlemaps
from loguru import logger
import requests

from chatbot_webhooks.webhooks.models import Token


def address_contains_street_number(address: str) -> bool:
    left_text = address.partition("Rio de Janeiro - RJ")[0]
    return bool(re.search(r"\d", left_text))


def address_find_street_number(address: str) -> str:
    left_text = address.partition("Rio de Janeiro - RJ")[0]
    lista_numeros = re.findall(r"\d+", left_text)
    return lista_numeros[-1]


def authentication_required(view_func):
    """
    A decorator that checks whether the request is authenticated. It does so by checking the
    following conditions:
    - The request has an Authorization header with a Bearer token in it, the token is valid and
        the token is active.
    """

    def wrapper(request: HttpRequest, *args, **kwargs):
        # Check if the Authorization header is present
        if "Authorization" not in request.headers:
            return HttpResponse(status=401)
        # Check if the Authorization header has a Bearer token
        auth_header = request.headers["Authorization"]
        if not auth_header.startswith("Bearer "):
            return HttpResponse(status=401)
        # Check if the token is valid and active
        token = auth_header.split(" ")[1]
        try:
            token_obj = Token.objects.get(token=token)
        except Token.DoesNotExist:
            return HttpResponse(status=401)
        if not token_obj.is_active:
            return HttpResponse(status=401)
        # If all checks pass, call the view function
        return view_func(request, *args, **kwargs)

    return wrapper


def get_credentials_from_env() -> service_account.Credentials:
    """
    Gets credentials from env vars
    """
    info: dict = json.loads(base64.b64decode(settings.GCP_SERVICE_ACCOUNT))
    return service_account.Credentials.from_service_account_info(info)


def get_ipp_info(parameters: dict) -> bool:
    geocode_ipp_url = str(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Geocode/Geocode_Logradouros_WGS84/GeocodeServer/reverseGeocode?"  # noqa
        + f'location={parameters["logradouro_longitude"]}%2C{parameters["logradouro_latitude"]}'
        + "&langCode=&locationType=&featureTypes=&outSR=&preferredLabelValues=&f=pjson"
    )

    response = requests.request(
        "GET",
        geocode_ipp_url,
    )
    data = response.json()

    try:
        parameters["logradouro_id_ipp"] = str(data["address"]["CL"])
        parameters["logradouro_id_bairro_ipp"] = str(data["address"]["COD_Bairro"])
        parameters["logradouro_nome_ipp"] = str(data["address"]["Match_addr"])
        return True
    except:  # noqa
        logger.info(data)
        parameters["abertura_manual"] = True
        return False


def google_find_place(address: str, parameters: dict) -> bool:
    """
    Uses Google Maps API to get the formatted address using find_place and then call
    google_geolocator function
    """
    client = googlemaps.Client(settings.GMAPS_API_TOKEN)
    find_place_result = client.find_place(
        address,
        "textquery",
        fields=["formatted_address", "name"],
        location_bias="rectangle:-22.74744540190159, -43.098580713057416|-23.100575987851833, -43.79779077663037",  # noqa
        language="pt",
    )

    if find_place_result["status"] == "OK":
        parameters["logradouro_ponto_referencia_identificado"] = find_place_result[
            "candidates"
        ][0]["name"]
        logger.info("find_place OK")
        logger.info("FINDPLACE RESULT ABAIXO")
        logger.info(find_place_result)
        logger.info("-----")
        if address_contains_street_number(
            find_place_result["candidates"][0]["formatted_address"]
        ):
            logger.info("Contém número da rua")
            parameters["logradouro_numero_identificado_google"] = True
            return google_geolocator(
                find_place_result["candidates"][0]["formatted_address"], parameters
            )
        else:
            logger.info("Não contém número da rua")
            parameters["logradouro_numero_identificado_google"] = False
            endereco_completo = f"{find_place_result['candidates'][0]['name']}, {find_place_result['candidates'][0]['formatted_address']}"  # noqa
            return google_geolocator(endereco_completo, parameters)
    else:
        logger.warning("find_place NOT OK")
        return False


def google_geolocator(address: str, parameters: dict) -> bool:
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

    client = googlemaps.Client(settings.GMAPS_API_TOKEN)
    geocode_result = client.geocode(address)

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
        geocode_result = client.reverse_geocode((lat, lng))

    for item in geocode_result[0]["address_components"]:
        if "street_number" in item["types"]:
            parameters["logradouro_numero"] = item["long_name"]
        elif [i for i in ACCEPTED_LOGRADOUROS if i in item["types"]]:
            parameters["logradouro_nome"] = item["long_name"]
        elif "sublocality" in item["types"] or "sublocality_level_1" in item["types"]:
            parameters["logradouro_bairro"] = item["long_name"]
        elif "postal_code" in item["types"]:
            parameters["logradouro_cep"] = item["long_name"]
        elif "administrative_area_level_2" in item["types"]:
            parameters["logradouro_cidade"] = item["long_name"]
        elif "administrative_area_level_1" in item["types"]:
            parameters["logradouro_estado"] = item["short_name"]

    parameters["logradouro_latitude"] = geocode_result[0]["geometry"]["location"]["lat"]
    parameters["logradouro_longitude"] = geocode_result[0]["geometry"]["location"][
        "lng"
    ]

    # Caso já tenha sido identificado que existe numero de logradouro no endereço retornado pelo find_place, mas
    # o geolocator não tenha conseguido retorná-lo, raspamos a string para achar esse número.
    if "logradouro_numero_identificado_google" in parameters:
        if (
            parameters["logradouro_numero_identificado_google"]
            and not parameters["logradouro_numero"]
        ):
            parameters["logradouro_numero"] = address_find_street_number(address)
        parameters["logradouro_numero_identificado_google"] = None
    else:
        pass

    # Fazer essa conversão usando try previne erros mais pra frente
    try:
        parameters["logradouro_numero"] = int(parameters["logradouro_numero"])
    except:  # noqa
        logger.info("logradouro_numero não é convertível para tipo inteiro.")

    return True


def form_info_update(
    parameter_list: list, parameter_name: str, parameter_value: any
) -> list:
    indice = -1
    for i in range(0, len(parameter_list)):
        if parameter_list[i]["displayName"] == parameter_name:
            indice = i
            break
    if indice == -1:
        raise ValueError(
            f"Parameter {parameter_name} was not found in form parameter list"
        )
    parameter_list[indice]["value"] = parameter_value

    return parameter_list


def validate_CPF(parameters: dict, form_parameters_list: list) -> bool:
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
    form_parameters_list = form_info_update(
        form_parameters_list, "usuario_cpf", cpf_formatado
    )

    return True


def validate_email(parameters: dict, form_parameters_list: list) -> bool:
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
