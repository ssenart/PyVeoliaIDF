"""A client of the Salesforce Aura endpoint: the generic transport under the Veolia site.

The Veolia customer area is a Salesforce Experience site. Its pages do not call a REST API: they post "actions" to one
endpoint (Aura), and the actions run Apex methods on the server. This module knows that protocol and nothing about water:
the bootstrap of the context, the login, and the call of an Apex method. The Veolia methods are in api_client.py.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from urllib.parse import unquote, urljoin

import aiohttp
from pydantic import SecretStr
from yarl import URL

from pyveoliaidf.config import ClientConfig
from pyveoliaidf.errors import (
    LoginError,
    NotLoggedInError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    UnexpectedResponseError,
)
from pyveoliaidf.resilience import RetryableError, retrying
from pyveoliaidf.tls import build_ssl_context

LOGIN_PAGE = "/s/login/"
HOME_PAGE = "/s/"
AURA_PATH = "/s/sfsites/aura"

# The pages the Aura calls come from. The server checks them against the app that the context names.
LOGIN_PAGE_URI = "/espace-particuliers/s/login"
START_URL = "/espace-particuliers/s/"
DEFAULT_PAGE_URI = "/espace-particuliers/s/"

LOGIN_DESCRIPTOR = "apex://LightningLoginFormController/ACTION$login"
APEX_DESCRIPTOR = "aura://ApexActionController/ACTION$execute"

# The context is JSON in the URL of the scripts of every page: /s/sfsites/l/{url-encoded JSON}/app.js
CONTEXT_IN_PAGE = re.compile(r"/s/sfsites/l/(%7B.+?%7D)/")

CSRF_COOKIE_MARKER = "ERIC"

HTTP_TOO_MANY_REQUESTS = 429
HTTP_RETRYABLE = {HTTP_TOO_MANY_REQUESTS, 502, 503, 504}

Logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AuraContext:
    """What every Aura call must send back to the server: which framework build and which app the client was loaded from."""

    mode: str
    app: str
    fwuid: str
    loaded: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "fwuid": self.fwuid,
                "app": self.app,
                "loaded": self.loaded,
                "dn": [],
                "globals": {},
                "uad": True,
            },
            separators=(",", ":"),
        )

    def updated_from(self, response_context: dict[str, Any]) -> "AuraContext":
        """Returns the context that the server asks for in its answer: a new framework build, or more loaded components."""

        fwuid = response_context.get("fwuid")
        loaded = response_context.get("loaded")

        return replace(
            self,
            fwuid=fwuid if isinstance(fwuid, str) and fwuid else self.fwuid,
            loaded={**self.loaded, **loaded} if isinstance(loaded, dict) else self.loaded,
        )


# ------------------------------------------------------------------------------------------------------------
class AuraTransport(Protocol):
    """What the Veolia API client needs from the transport: the tests give it a fake."""

    async def login(self) -> None: ...

    async def logout(self) -> None: ...

    def is_logged_in(self) -> bool: ...

    async def call_apex(
        self, classname: str, method: str, params: dict[str, Any] | None = None, page_uri: str = DEFAULT_PAGE_URI
    ) -> Any: ...

    async def close(self) -> None: ...


# ------------------------------------------------------------------------------------------------------------
def parse_context(html: str) -> AuraContext:
    """Returns the Aura context that a page of the site carries in the URLs of its scripts.

    A page has several such URLs, and not all of them name the framework build: the first one that does is the context.
    """

    matches = CONTEXT_IN_PAGE.findall(html)
    if not matches:
        raise UnexpectedResponseError("The page carries no Aura context.")

    for candidate in matches:
        try:
            raw = json.loads(unquote(candidate))
        except ValueError:
            continue
        if isinstance(raw, dict) and raw.get("fwuid") and raw.get("app") and raw.get("mode"):
            loaded = raw.get("loaded")
            return AuraContext(
                mode=str(raw["mode"]),
                app=str(raw["app"]),
                fwuid=str(raw["fwuid"]),
                loaded={str(key): str(value) for key, value in loaded.items()} if isinstance(loaded, dict) else {},
            )

    raise UnexpectedResponseError("No Aura context of the page names the framework build (fwuid).")


# ------------------------------------------------------------------------------------------------------------
def parse_response(text: str) -> dict[str, Any]:
    """Returns the JSON of an Aura answer, which may come with some text around it."""

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise UnexpectedResponseError("The Aura answer holds no JSON.")

    try:
        body: dict[str, Any] = json.loads(text[start : end + 1])  # it starts with a brace: an object, or an error
    except ValueError as error:
        raise UnexpectedResponseError("The Aura answer is not valid JSON.") from error

    return body


# ------------------------------------------------------------------------------------------------------------
def event_descriptors(body: dict[str, Any]) -> list[str]:
    """Returns the descriptors of the events that an Aura answer carries."""

    events = body.get("events")
    if not isinstance(events, list):
        return []

    return [
        event["descriptor"] for event in events if isinstance(event, dict) and isinstance(event.get("descriptor"), str)
    ]


# ------------------------------------------------------------------------------------------------------------
def redirect_url(body: dict[str, Any]) -> str | None:
    """Returns the URL of the clientRedirect event of an Aura answer, if there is one: it is how a login ends."""

    events = body.get("events")
    if not isinstance(events, list):
        return None

    for event in events:
        if isinstance(event, dict) and event.get("descriptor") == "markup://aura:clientRedirect":
            url = event.get("attributes", {}).get("values", {}).get("url")
            if isinstance(url, str) and url:
                return url

    return None


# ------------------------------------------------------------------------------------------------------------
def action_result(body: dict[str, Any]) -> dict[str, Any]:
    """Returns the first action of an Aura answer."""

    actions = body.get("actions")
    if not isinstance(actions, list) or not actions or not isinstance(actions[0], dict):
        raise UnexpectedResponseError("The Aura answer holds no action.")

    return actions[0]


# ------------------------------------------------------------------------------------------------------------
def error_messages(action: dict[str, Any]) -> str:
    """Returns the messages of a failed action. The messages come from the server and carry no secret."""

    errors = action.get("error")
    messages = [
        error["message"]
        for error in (errors if isinstance(errors, list) else [])
        if isinstance(error, dict) and isinstance(error.get("message"), str)
    ]

    return "; ".join(messages) or "no reason given"


# ------------------------------------------------------------------------------------------------------------
class AuraClient:
    """A logged-in conversation with the Aura endpoint of the site.

    The session that is given must keep cookies (the login is a cookie), and must trust the intermediate certificate that
    the site leaves out of its chain: build its connector with TCPConnector(ssl=build_ssl_context()). Home Assistant's
    shared session does neither, so with Home Assistant, let the client create its own session. When no session is
    given, the client owns one, and close() ends it.
    """

    # ------------------------------------------------------
    def __init__(
        self,
        username: str,
        password: str | SecretStr,
        config: ClientConfig | None = None,
        session: aiohttp.ClientSession | None = None,
    ):
        self._username = username
        self._password = password if isinstance(password, SecretStr) else SecretStr(password)
        self._config = config or ClientConfig()
        self._session = session
        self._owns_session = session is None
        self._context: AuraContext | None = None
        self._token: str | None = None
        # Counts the logins, so that concurrent calls that see the session end log in once between them.
        self._login_count = 0
        self._lock = asyncio.Lock()
        self._session_lock = asyncio.Lock()

    # ------------------------------------------------------
    def __repr__(self) -> str:
        return f"AuraClient(username={self._username!r}, base_url={self._config.base_url!r})"

    # ------------------------------------------------------
    def is_logged_in(self) -> bool:
        return self._token is not None

    # ------------------------------------------------------
    async def login(self) -> None:
        async with self._lock:
            if self._token is None:
                await self._login()

    # ------------------------------------------------------
    async def logout(self) -> None:
        """Forgets the session. The cookies are dropped too, so that the next login starts clean."""

        async with self._lock:
            self._token = None
            self._context = None
            if self._session is not None:
                self._session.cookie_jar.clear()

    # ------------------------------------------------------
    async def close(self) -> None:
        await self.logout()
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------
    async def call_apex(
        self, classname: str, method: str, params: dict[str, Any] | None = None, page_uri: str = DEFAULT_PAGE_URI
    ) -> Any:
        """Runs an Apex method and returns its value.

        When the server says the session has ended, the client logs in again and repeats the call once. It does the same
        when the server says the framework build has changed, after taking the new context from the answer.
        """

        if self._token is None or self._context is None:
            raise NotLoggedInError("Call login() before calling the server.")

        action = {
            "id": "1;a",
            "descriptor": APEX_DESCRIPTOR,
            "callingDescriptor": "UNKNOWN",
            "params": {
                "namespace": "",
                "classname": classname,
                "method": method,
                "params": params or {},
                "cacheable": False,
                "isContinuation": False,
            },
        }

        login_count = self._login_count
        try:
            return await self._run_apex(action, page_uri)
        except SessionExpiredError:
            Logger.debug("The session has expired: logging in again.")
            async with self._lock:
                # Another call may have logged in again while this one waited for the lock.
                if self._login_count == login_count:
                    self._token = None
                    await self._login()

            return await self._run_apex(action, page_uri)

    # ------------------------------------------------------
    async def _run_apex(self, action: dict[str, Any], page_uri: str) -> Any:
        for attempt in (1, 2):
            body = await self._post_action(action, page_uri, "aura.ApexAction.execute")
            descriptors = event_descriptors(body)

            if any(descriptor.endswith("aura:invalidSession") for descriptor in descriptors):
                raise SessionExpiredError("The server closed the session.", 401)

            if any(descriptor.endswith("aura:clientOutOfSync") for descriptor in descriptors):
                if attempt == 2:
                    break
                Logger.debug("The server asks for a new framework build: retrying with its context.")
                continue

            result = action_result(body)
            if result.get("state") != "SUCCESS":
                raise ServerError(
                    f"The call {action['params']['classname']}.{action['params']['method']} failed: {error_messages(result)}"
                )

            value = result.get("returnValue")

            # Apex answers are wrapped once more: {"returnValue": ..., "cacheable": ...}
            return value["returnValue"] if isinstance(value, dict) and "returnValue" in value else value

        raise UnexpectedResponseError("The server keeps asking for a new framework build.")

    # ------------------------------------------------------
    async def _login(self) -> None:
        try:
            await self._do_login()
        except SessionExpiredError as error:
            # An HTTP 401 or 403 while logging in is a refusal of the login, not an expired session.
            raise LoginError(str(error), error.status_code) from error

    # ------------------------------------------------------
    async def _do_login(self) -> None:
        session = await self._ensure_session()
        login_page = await self._get(urljoin(self._config.base_url, LOGIN_PAGE))
        self._context = parse_context(login_page)

        action = {
            "id": "1;a",
            "descriptor": LOGIN_DESCRIPTOR,
            "callingDescriptor": "UNKNOWN",
            "params": {
                "username": self._username,
                "password": self._password.get_secret_value(),
                "startUrl": START_URL,
            },
        }
        body = await self._post_action(action, LOGIN_PAGE_URI, "other.LightningLoginForm.login", token="undefined")
        result = action_result(body)
        if result.get("state") != "SUCCESS":
            raise LoginError(f"The login failed: {error_messages(result)}", 401)

        # A refused login answers with a message; an accepted one answers with a redirect to the front door.
        value = result.get("returnValue")
        if isinstance(value, str) and value:
            raise LoginError(f"The login was refused: {value}", 401)

        target = redirect_url(body)
        if target is None:
            raise LoginError("The login ended without a redirect: the login page has probably changed.", 401)

        await self._get(urljoin(self._config.base_url, target))
        home_page = await self._get(urljoin(self._config.base_url, HOME_PAGE))
        self._context = parse_context(home_page)

        cookies = session.cookie_jar.filter_cookies(URL(self._config.base_url))
        token = next((cookie.value for name, cookie in cookies.items() if CSRF_COOKIE_MARKER in name), None)
        if token is None:
            raise LoginError("The login gave no session token: check that the HTTP session keeps cookies.", 401)
        self._token = token
        self._login_count += 1

        Logger.debug("Logged in.")

    # ------------------------------------------------------
    async def _post_action(
        self, action: dict[str, Any], page_uri: str, descriptor_flag: str, token: str | None = None
    ) -> dict[str, Any]:
        assert self._context is not None

        url = f"{urljoin(self._config.base_url, AURA_PATH)}?r=0&{descriptor_flag}=1"
        form = {
            "message": json.dumps({"actions": [action]}, separators=(",", ":")),
            "aura.context": self._context.as_json(),
            "aura.pageURI": page_uri,
            "aura.token": token if token is not None else (self._token or "undefined"),
        }

        text = await self._request("POST", url, data=form)
        body = parse_response(text)

        context = body.get("context")
        if isinstance(context, dict):
            self._context = self._context.updated_from(context)

        return body

    # ------------------------------------------------------
    async def _get(self, url: str) -> str:
        return await self._request("GET", url)

    # ------------------------------------------------------
    async def _request(self, method: str, url: str, data: dict[str, str] | None = None) -> str:
        session = await self._ensure_session()
        timeout = aiohttp.ClientTimeout(sock_connect=self._config.connect_timeout, sock_read=self._config.read_timeout)

        async def operation() -> str:
            started = time.monotonic()
            try:
                async with session.request(method, url, data=data, timeout=timeout) as response:
                    Logger.debug(
                        "%s %s -> %d in %.2fs", method, URL(url).path, response.status, time.monotonic() - started
                    )
                    if response.status in HTTP_RETRYABLE:
                        retry_after = response.headers.get("Retry-After", "")
                        raise RetryableError(
                            f"HTTP {response.status}",
                            float(retry_after) if retry_after.isdigit() else None,
                            response.status,
                        )
                    if response.status in (401, 403):
                        raise SessionExpiredError(
                            f"The server refused the call (HTTP {response.status}).", response.status
                        )
                    if response.status >= 400:
                        raise ServerError(
                            f"The server answered HTTP {response.status} to {method} {URL(url).path}.", response.status
                        )

                    return await response.text()
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as error:
                raise RetryableError(f"{type(error).__name__}") from error

        try:
            return await retrying(operation, self._config)
        except RetryableError as error:
            if error.status == HTTP_TOO_MANY_REQUESTS:
                raise RateLimitError("The server kept refusing the calls (HTTP 429).") from error
            raise ServerError(f"The server could not be reached ({error}).") from error

    # ------------------------------------------------------
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Returns the HTTP session, and makes it on the first call.

        The TLS context reads the certificate files, which blocks: it is built in a thread, so that an application with
        an event loop that watches for blocking calls (Home Assistant does) is not slowed down or warned.
        """

        async with self._session_lock:
            if self._session is None:
                ssl_context = await asyncio.to_thread(build_ssl_context)
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl_context),
                    cookie_jar=aiohttp.CookieJar(),
                    headers={"User-Agent": self._config.user_agent},
                )

            return self._session
