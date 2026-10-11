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


def contract_details(contract_id: str = "CONTRACT-1") -> dict[str, Any]:
    """The details of a contract. The personal fields are fake, and the library must drop them."""

    customer = {"FirstName": "Jane", "LastName": "Doe", "Email": "jane@example.invalid", "MobilePhone": "0600000000"}

    return {
        "compteInfo": [{"ELEMA": "point-token", "ELEMB": "meter-token", "ID_PDS": "1234567890", "NUM_COMPTEUR": "X1"}],
        "contrat": {"Id": contract_id, "Name": "1234567"},
        "contratClient": customer,
        "payeurClient": customer,
    }


def record(day: str, index: str, consumption: str, estimated: bool = False) -> dict[str, Any]:
    return {
        "CONSOMMATION": consumption,
        "DATE_INDEX": f"{day} 21:00:00",
        "DEBIT_PERMANENT": "0",
        "FLAG_ESTIMATION": estimated,
        "FLAG_ESTIMATION_INDEX": True,
        "VALEUR_INDEX": index,
    }


def consumption(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": {"CONSOMMATION": records, "ID_PDS": "1234567890"}, "prixMoyenEau": 4.9171}
