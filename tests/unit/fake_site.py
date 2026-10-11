"""A fake Veolia site: a small aiohttp server on the loopback, so that the transport runs for real (cookies, redirects, forms).

The tests script what the Aura endpoint answers, and read what the client sent.
"""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestServer

from tests.unit.helpers import CSRF_COOKIE, FRONTDOOR_PATH, apex_body, aura_body, page, redirect_event

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


class FakeSite:
    def __init__(self) -> None:
        self.login_fwuid = "fwuid-1"
        self.home_fwuid = "fwuid-2"
        self.sets_cookie = True
        self.login_page: str | None = None
        self.login_page_status = 200
        # What the login action answers; None means the answer of an accepted login.
        self.login_answer: dict[str, Any] | None = None
        # The answers to the calls that are not logins, in order: a dict (JSON, 200), a (status, headers) tuple, or a callable.
        self.answers: deque[Any] = deque()
        self.forms: list[dict[str, str]] = []
        self.logins = 0
        self.hits: list[str] = []
        self.in_flight_delay = 0.0
        self._server: TestServer | None = None

    @property
    def base_url(self) -> str:
        assert self._server is not None
        return f"http://localhost:{self._server.port}"

    def queue(self, *answers: Any) -> None:
        self.answers.extend(answers)

    def queue_apex(self, value: Any) -> None:
        self.answers.append(apex_body(value))

    @property
    def call_forms(self) -> list[dict[str, str]]:
        """The forms of the calls that are not logins."""

        return [form for form in self.forms if "ACTION$login" not in form["message"]]

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/s/login/", self._login_page)
        app.router.add_post("/s/sfsites/aura", self._aura)
        app.router.add_get("/secur/frontdoor.jsp", self._frontdoor)
        app.router.add_get("/s/", self._home)
        self._server = TestServer(app, host="127.0.0.1")
        await self._server.start_server()

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.close()

    async def _login_page(self, request: web.Request) -> web.Response:
        self.hits.append("login-page")
        return web.Response(
            status=self.login_page_status,
            text=self.login_page if self.login_page is not None else page(self.login_fwuid),
        )

    async def _home(self, request: web.Request) -> web.Response:
        self.hits.append("home")
        return web.Response(text=page(self.home_fwuid, app="siteforce:communityApp"))

    async def _frontdoor(self, request: web.Request) -> web.Response:
        self.hits.append("frontdoor")
        response = web.Response(text="")
        if self.sets_cookie:
            name, _, value = CSRF_COOKIE.split(";")[0].partition("=")
            response.set_cookie(name, value, path="/")
        return response

    async def _aura(self, request: web.Request) -> web.StreamResponse:
        form = dict(await request.post())
        self.forms.append({key: str(value) for key, value in form.items()})
        message = str(form["message"])

        if "ACTION$login" in message:
            self.logins += 1
            self.hits.append("login")
            await asyncio.sleep(self.in_flight_delay)
            return web.json_response(self.login_answer or aura_body(None, events=[redirect_event()]))

        self.hits.append("call")
        if not self.answers:
            return web.json_response(apex_body(None))

        answer = self.answers.popleft()
        if callable(answer):
            return await answer(request)  # type: ignore[no-any-return]
        if isinstance(answer, tuple):
            status, headers = answer
            return web.Response(status=status, headers=headers, text="")
        if isinstance(answer, str):
            return web.Response(text=answer)
        return web.json_response(answer)


__all__ = ["FakeSite", "FRONTDOOR_PATH"]
