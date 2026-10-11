"""Builders of the pages and answers of the Veolia site, as the unit tests need them."""

import json
from typing import Any
from urllib.parse import quote

FRONTDOOR_PATH = "/secur/frontdoor.jsp?sid=SESSION"

# The fake site runs on http, where the browsers (and aiohttp) would not send back a Secure cookie.
CSRF_COOKIE = "ERIC_PROD-0abc=csrf-token-value; Path=/"


def context_json(fwuid: str = "fwuid-1", app: str = "siteforce:loginApp2", loaded: str = "1811_abc") -> dict[str, Any]:
    return {
        "mode": "PRODDEBUG",
        "app": app,
        "fwuid": fwuid,
        "loaded": {f"APPLICATION@markup://{app}": loaded},
    }


def page(fwuid: str = "fwuid-1", app: str = "siteforce:loginApp2") -> str:
    """A page of the site: the first script URL has a context without fwuid, as the real ones do."""

    style = quote(json.dumps({"mode": "PRODDEBUG", "app": app, "styleContext": {"c": "other"}}), safe="")
    framework = quote(json.dumps(context_json(fwuid, app)), safe="")

    return (
        "<html><head>"
        f'<link href="/s/sfsites/l/{style}/app.css?3=" rel="stylesheet">'
        f'<script src="/s/sfsites/l/{framework}/app.js?3="></script>'
        "</head><body></body></html>"
    )


def action(state: str = "SUCCESS", value: Any = None, errors: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"id": "1;a", "state": state, "returnValue": value}
    if errors is not None:
        result["error"] = [{"message": message} for message in errors]

    return result


def aura_body(
    value: Any = None,
    state: str = "SUCCESS",
    errors: list[str] | None = None,
    events: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"actions": [action(state, value, errors)]}
    if events is not None:
        body["events"] = events
    if context is not None:
        body["context"] = context

    return body


def apex_body(value: Any) -> dict[str, Any]:
    """An Apex answer: the value is wrapped once more, as the server does."""

    return aura_body({"returnValue": value, "cacheable": False})


def redirect_event(url: str = FRONTDOOR_PATH) -> dict[str, Any]:
    return {"descriptor": "markup://aura:clientRedirect", "attributes": {"values": {"url": url}}}


def event(name: str) -> dict[str, Any]:
    return {"descriptor": f"markup://aura:{name}", "attributes": {"values": {}}}


def party(first_name: str = "Jane") -> dict[str, Any]:
    """A customer or a payer. Every value is fake and recognizable, so that the tests can look for it in repr and logs."""

    return {
        "AssujettiTVA": False,
        "BillingCity": "Paris",
        "BillingPostalCode": "75001",
        "BillingStreet": "1 rue Fictive",
        "ContratClientId": "CC-1",
        "Email": "jane@example.invalid",
        "FirstName": first_name,
        "GC": False,
        "Id": "PARTY-1",
        "LastName": "Doe",
        "MobilePhone": "0600000000",
        "Name": "Jane Doe",
        "Salutation": "Mme",
        "VCRM_ID": "CRM-1",
        "VerrouillageFiche": False,
    }


def contract_details(
    contract_id: str = "CONTRACT-1", meters: tuple[str, ...] = ("X1",), number: str = "1234567", salt: str = ""
) -> dict[str, Any]:
    """The details of a contract, with every field that the site sends.

    The salt makes the tokens of the meters differ from one call to the next, as the real site's do.
    """

    return {
        "compteInfo": [
            {
                "ELEMA": f"point-token-{meter}{salt}",
                "ELEMB": f"meter-token-{meter}{salt}",
                "ID_PDS": "1234567890",
                "NUM_COMPTEUR": meter,
            }
            for meter in meters
        ],
        "compteParticulier": True,
        "contrat": {
            "AutoriteOrganisatrice": "SEDIF",
            "DateSortieEPT": "2024-01-01",
            "Id": contract_id,
            "Name": number,
            "SITE_CP": "75001",
            "SITE_Commune": "Paris",
            "SITE_Rue": "1 rue Fictive",
            "Statut": "Actif",
        },
        "contratClient": party(),
        "multipleContrats": False,
        "payeurClient": party("Payer"),
        "segmentationPrimaire": "PARTICULIER",
        "solde": 12.5,
    }


def record(day: str, index: str, consumption: str, estimated: bool = False, **extra: Any) -> dict[str, Any]:
    return {
        "CONSOMMATION": consumption,
        "DATE_INDEX": f"{day} 21:00:00",
        "DEBIT_PERMANENT": "0",
        "FLAG_ESTIMATION": estimated,
        "FLAG_ESTIMATION_INDEX": True,
        "VALEUR_INDEX": index,
        **extra,
    }


def consumption(records: list[dict[str, Any]], **top: Any) -> dict[str, Any]:
    """The answer of the consumption method: the records, and everything the site says around them."""

    answer: dict[str, Any] = {
        "data": {
            "CONSOMMATION": records,
            "CONSOMMATION_MAX": "2.921",
            "CONSOMMATION_MOYENNE": "0.92921",
            "DATE_CONSOMMATION_MAX": "2026-09-05",
            "DATE_DEBUT": "2026-07-12 02:00:00",
            "DATE_FIN": "2026-10-10 02:00:00",
            "ID_PDS": "1234567890",
            "NUMERO_COMPTEUR": "X1",
        },
        "prixMoyenEau": 4.9171,
        "seuilDebitPermanet": 0.0,
        "showDebitPermanent": False,
        "canCompareMonth": True,
        "indexMesure": [f"{item['VALEUR_INDEX']};{item['DATE_INDEX']}" for item in records],
    }
    answer.update(top)

    return answer
