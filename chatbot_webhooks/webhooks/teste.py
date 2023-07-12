import json

from jellyfish import jaro_similarity
from loguru import logger
import requests

def get_ipp_street_name(parameters: dict) -> dict:
    THRESHOLD = 0.8
    logradouro_google = parameters["logradouro_nome"]
    logradouro_ipp = parameters["logradouro_nome_ipp"]

    # Corte a string para considerar apenas o nome da rua
    for i in range(0,len(logradouro_ipp)):
        if logradouro_ipp[i] not in "0123456789 -":
            logradouro_ipp = logradouro_ipp[i:]
            break
    
    logger.info(f'Logradouro IPP: {logradouro_ipp}')
    if jaro_similarity(logradouro_google, logradouro_ipp) > THRESHOLD:
        logger.info(f"Similaridade alta o suficiente: {jaro_similarity(logradouro_google, logradouro_ipp)}")
        return parameters
    else:
        logger.info(f"logradouro_nome retornado pelo Google significantemente diferente do retornado pelo IPP. Threshold: {jaro_similarity(logradouro_google, logradouro_ipp)}")
        # Call IPP api
        geocode_logradouro_ipp_url = str(
            "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Geocode/Geocode_Logradouros_WGS84/GeocodeServer/findAddressCandidates?"
            + f"Address={logradouro_google}&Address2=&Address3=&Neighborhood=&City=&Subregion=&Region=&Postal=&PostalExt=&CountryCode=&SingleLine=&outFields=cl"
            + "&maxLocations=&matchOutOfRange=true&langCode=&locationType=&sourceCountry=&category=&location=&searchExtent=&outSR=&magicKey=&preferredLabelValues=&f=pjson"
        )

        response = requests.request(
            "GET",
            geocode_logradouro_ipp_url,
        )
        data = response.json()

        try:
            candidates = list(data["candidates"])
            logradouro_google_completo = f'{logradouro_google}, {parameters["logradouro_bairro_ipp"]}'
            logradouro_codigo = None
            logradouro_real = None
            best_similarity = 0
            for candidato in candidates:
                similarity = jaro_similarity(candidato["address"], logradouro_google_completo)
                if similarity > best_similarity:
                    best_similarity = similarity
                    logradouro_codigo = candidato["attributes"]["cl"]
                    logradouro_real = candidato["address"]
            
            logger.info(f'Logradouro encontrado no Google, com bairro do IPP: {logradouro_google_completo}')
            logger.info(f'Logradouro no IPP com maior semelhança: {logradouro_real}, cl: {logradouro_codigo}, semelhança: {best_similarity}')

            parameters["logradouro_id_ipp"] = logradouro_codigo
            
            return parameters
        except:
            logger.info("Correspondência não exata entre endereço no Google e no IPP")
            return parameters

dicionario = {
    "logradouro_nome": "Rua do Catete",
    "logradouro_nome_ipp": "20-84 Rua Barão de Guaratiba, Catete",
    "logradouro_bairro_ipp": "Catete",
}

print(get_ipp_street_name(dicionario))