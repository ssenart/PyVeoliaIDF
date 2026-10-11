import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from pydantic import SecretStr

from pyveoliaidf.aura import AuraClient
from pyveoliaidf.config import ClientConfig
from pyveoliaidf.errors import (
    LoginError,
    NotLoggedInError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    UnexpectedResponseError,
)
from pyveoliaidf.tls import build_ssl_context
from tests.unit.fake_site import FakeSite
from tests.unit.helpers import apex_body, aura_body, event, redirect_event

USERNAME = "user@example.invalid"
PASSWORD = "s3cret-password"


def config_for(site: FakeSite, **overrides: float) -> ClientConfig:
    settings = {"retry_count": 2, "retry_delay": 0.0, "max_retry_delay": 0.0, **overrides}

    return ClientConfig(base_url=site.base_url, **settings)  # type: ignore[arg-type]


@pytest.fixture
async def client(site: FakeSite) -> AsyncIterator[AuraClient]:
    aura = AuraClient(USERNAME, PASSWORD, config_for(site))
    yield aura
    await aura.close()


@pytest.fixture
async def logged_in(site: FakeSite, client: AuraClient) -> AuraClient:
    await client.login()

    return client


class TestLogin:
    async def test_gets_a_session_token_and_the_community_context(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue_apex("ok")

        await logged_in.call_apex("Cls", "method")

        form = site.call_forms[0]
        assert form["aura.token"] == "csrf-token-value"
        assert '"fwuid":"fwuid-2"' in form["aura.context"]
        assert '"app":"siteforce:communityApp"' in form["aura.context"]
        assert site.hits == ["login-page", "login", "frontdoor", "home", "call"]

    async def test_login_form_carries_the_credentials_and_the_login_context(
        self, site: FakeSite, logged_in: AuraClient
    ) -> None:
        form = site.forms[0]

        assert "ACTION$login" in form["message"]
        assert USERNAME in form["message"]
        assert PASSWORD in form["message"]
        assert form["aura.token"] == "undefined"
        assert '"fwuid":"fwuid-1"' in form["aura.context"]
        assert form["aura.pageURI"] == "/espace-particuliers/s/login"

    async def test_login_is_done_once(self, site: FakeSite, logged_in: AuraClient) -> None:
        await logged_in.login()

        assert site.logins == 1
        assert logged_in.is_logged_in()

    async def test_concurrent_logins_log_in_once(self, site: FakeSite, client: AuraClient) -> None:
        site.in_flight_delay = 0.05

        await asyncio.gather(client.login(), client.login(), client.login())

        assert site.logins == 1

    @pytest.mark.parametrize("status", [401, 403])
    async def test_http_refusal_of_the_login_page_is_a_login_error(
        self, site: FakeSite, client: AuraClient, status: int
    ) -> None:
        site.login_page_status = status

        with pytest.raises(LoginError) as error:
            await client.login()

        assert error.value.status_code == status

    async def test_refused_login(self, site: FakeSite, client: AuraClient) -> None:
        site.login_answer = aura_body("Your login attempt has failed.")

        with pytest.raises(LoginError, match="refused") as error:
            await client.login()

        assert PASSWORD not in str(error.value)
        assert not client.is_logged_in()

    async def test_failed_login_action(self, site: FakeSite, client: AuraClient) -> None:
        site.login_answer = aura_body(None, state="ERROR", errors=["Bad controller"])

        with pytest.raises(LoginError, match="Bad controller"):
            await client.login()

    async def test_login_without_redirect(self, site: FakeSite, client: AuraClient) -> None:
        site.login_answer = aura_body(None)

        with pytest.raises(LoginError, match="without a redirect"):
            await client.login()

    async def test_login_without_session_cookie(self, site: FakeSite, client: AuraClient) -> None:
        site.sets_cookie = False

        with pytest.raises(LoginError, match="keeps cookies"):
            await client.login()

    async def test_login_page_without_context(self, site: FakeSite, client: AuraClient) -> None:
        site.login_page = "<html></html>"

        with pytest.raises(UnexpectedResponseError):
            await client.login()

    async def test_password_can_be_given_as_a_secret(self, site: FakeSite) -> None:
        aura = AuraClient(USERNAME, SecretStr(PASSWORD), config_for(site))

        try:
            await aura.login()

            assert PASSWORD in site.forms[0]["message"]
        finally:
            await aura.close()

    async def test_repr_hides_the_password(self, client: AuraClient) -> None:
        assert PASSWORD not in repr(client)
        assert USERNAME in repr(client)


class TestCallApex:
    async def test_not_logged_in(self, client: AuraClient) -> None:
        with pytest.raises(NotLoggedInError):
            await client.call_apex("Cls", "method")

    async def test_returns_the_unwrapped_value_and_sends_the_parameters(
        self, site: FakeSite, logged_in: AuraClient
    ) -> None:
        site.queue_apex({"answer": 42})

        assert await logged_in.call_apex("Cls", "method", {"a": 1}, page_uri="/some/page") == {"answer": 42}

        form = site.call_forms[0]
        assert '"classname":"Cls"' in form["message"]
        assert '"method":"method"' in form["message"]
        assert '"params":{"a":1}' in form["message"]
        assert form["aura.pageURI"] == "/some/page"

    async def test_returns_a_value_that_is_not_wrapped(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue(aura_body(["a", "b"]))

        assert await logged_in.call_apex("Cls", "method") == ["a", "b"]

    async def test_error_state(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue(aura_body(None, state="ERROR", errors=["Script-thrown exception"]))

        with pytest.raises(ServerError, match="Cls.method failed: Script-thrown exception"):
            await logged_in.call_apex("Cls", "method")

    async def test_takes_the_new_context_from_the_answer(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue(aura_body("one", context={"fwuid": "fwuid-3"}), apex_body("two"))

        await logged_in.call_apex("Cls", "one")
        await logged_in.call_apex("Cls", "two")

        assert '"fwuid":"fwuid-3"' in site.call_forms[1]["aura.context"]

    async def test_repeats_the_call_once_when_the_client_is_out_of_sync(
        self, site: FakeSite, logged_in: AuraClient
    ) -> None:
        site.queue(aura_body(None, events=[event("clientOutOfSync")], context={"fwuid": "fwuid-9"}), apex_body("fine"))

        assert await logged_in.call_apex("Cls", "method") == "fine"
        assert '"fwuid":"fwuid-9"' in site.call_forms[1]["aura.context"]

    async def test_gives_up_when_the_client_stays_out_of_sync(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue(*[aura_body(None, events=[event("clientOutOfSync")]) for _ in range(2)])

        with pytest.raises(UnexpectedResponseError, match="keeps asking"):
            await logged_in.call_apex("Cls", "method")

    async def test_logs_in_again_when_the_session_has_expired(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue(aura_body(None, events=[event("invalidSession")]), apex_body("after relogin"))

        assert await logged_in.call_apex("Cls", "method") == "after relogin"
        assert site.logins == 2

    async def test_http_401_means_the_session_has_ended(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue((401, {}), apex_body("after relogin"))

        assert await logged_in.call_apex("Cls", "method") == "after relogin"
        assert site.logins == 2

    async def test_concurrent_calls_that_see_the_session_end_log_in_once(
        self, site: FakeSite, logged_in: AuraClient
    ) -> None:
        site.queue(
            aura_body(None, events=[event("invalidSession")]),
            aura_body(None, events=[event("invalidSession")]),
            apex_body("first"),
            apex_body("second"),
        )

        results = await asyncio.gather(logged_in.call_apex("Cls", "a"), logged_in.call_apex("Cls", "b"))

        assert sorted(results) == ["first", "second"]
        assert site.logins == 2  # the first login, and one more for both calls

    async def test_gives_up_when_the_session_keeps_expiring(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue((401, {}), (401, {}))

        with pytest.raises(SessionExpiredError):
            await logged_in.call_apex("Cls", "method")


class TestHttpErrors:
    async def test_server_error_is_retried_then_reported(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue(*[(503, {}) for _ in range(3)])

        with pytest.raises(ServerError, match="could not be reached"):
            await logged_in.call_apex("Cls", "method")

        assert len(site.call_forms) == 3

    async def test_too_many_requests(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue(*[(429, {"Retry-After": "0"}) for _ in range(3)])

        with pytest.raises(RateLimitError):
            await logged_in.call_apex("Cls", "method")

    async def test_recovers_after_a_transient_failure(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue((502, {}), apex_body("back"))

        assert await logged_in.call_apex("Cls", "method") == "back"

    async def test_other_http_errors_are_reported_at_once(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue((404, {}))

        with pytest.raises(ServerError, match="HTTP 404") as error:
            await logged_in.call_apex("Cls", "method")

        assert error.value.status_code == 404
        assert len(site.call_forms) == 1

    async def test_unreadable_answer(self, site: FakeSite, logged_in: AuraClient) -> None:
        site.queue("<html>maintenance</html>")

        with pytest.raises(UnexpectedResponseError):
            await logged_in.call_apex("Cls", "method")

    async def test_timeouts_are_retried_then_reported(self, site: FakeSite) -> None:
        async def slow(request: web.Request) -> web.Response:
            await asyncio.sleep(1)
            return web.Response(text="{}")

        aura = AuraClient(USERNAME, PASSWORD, config_for(site, read_timeout=0.05))
        try:
            await aura.login()
            site.queue(slow, slow, slow)

            with pytest.raises(ServerError, match="TimeoutError"):
                await aura.call_apex("Cls", "method")
        finally:
            await aura.close()

    async def test_connection_errors_are_retried_then_reported(self, site: FakeSite) -> None:
        aura = AuraClient(USERNAME, PASSWORD, config_for(site))
        try:
            await aura.login()
            await site.stop()

            with pytest.raises(ServerError, match="ClientConnectorError|ClientConnectionError"):
                await aura.call_apex("Cls", "method")
        finally:
            await aura.close()
            await site.start()


class TestSession:
    async def test_logout_forgets_the_session(self, logged_in: AuraClient) -> None:
        await logged_in.logout()

        assert not logged_in.is_logged_in()
        with pytest.raises(NotLoggedInError):
            await logged_in.call_apex("Cls", "method")

    async def test_logout_before_any_login(self, client: AuraClient) -> None:
        await client.logout()

        assert not client.is_logged_in()

    async def test_login_after_logout(self, site: FakeSite, logged_in: AuraClient) -> None:
        await logged_in.logout()
        await logged_in.login()

        assert site.logins == 2
        assert logged_in.is_logged_in()

    async def test_a_given_session_is_not_closed(self, site: FakeSite) -> None:
        session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        aura = AuraClient(USERNAME, PASSWORD, config_for(site), session=session)
        await aura.login()

        await aura.close()

        assert not session.closed
        await session.close()

    async def test_an_own_session_is_closed(self, logged_in: AuraClient) -> None:
        session = logged_in._session

        await logged_in.close()

        assert session is not None
        assert session.closed

    async def test_the_tls_context_is_built_off_the_event_loop(
        self, site: FakeSite, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Reading the certificate files blocks: an application that watches its event loop (Home Assistant) warns about it.
        threads: list[int] = []
        real_build = build_ssl_context

        def spy() -> Any:
            threads.append(threading.get_ident())
            return real_build()

        monkeypatch.setattr("pyveoliaidf.aura.build_ssl_context", spy)
        aura = AuraClient(USERNAME, PASSWORD, config_for(site))
        try:
            await aura.login()
        finally:
            await aura.close()

        assert threads
        assert threading.get_ident() not in threads

    async def test_concurrent_first_calls_make_one_session(self, site: FakeSite) -> None:
        aura = AuraClient(USERNAME, PASSWORD, config_for(site))
        try:
            sessions = await asyncio.gather(*(aura._ensure_session() for _ in range(5)))

            assert len({id(session) for session in sessions}) == 1
        finally:
            await aura.close()

    async def test_close_twice(self, logged_in: AuraClient) -> None:
        await logged_in.close()
        await logged_in.close()

    async def test_secrets_never_reach_the_logs(
        self, site: FakeSite, logged_in: AuraClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        site.queue_apex("ok")

        await logged_in.call_apex("Cls", "method")

        assert [record for record in caplog.records if record.name.startswith("pyveoliaidf")]
        assert PASSWORD not in caplog.text
        assert "csrf-token-value" not in caplog.text


def test_redirect_events_are_relative_to_the_site() -> None:
    assert redirect_event()["attributes"]["values"]["url"].startswith("/")
