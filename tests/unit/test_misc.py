import dataclasses
import importlib
import json
import ssl
import sys
from datetime import datetime
from typing import Any, NoReturn

import pytest
from pydantic import ValidationError

import pyveoliaidf
from pyveoliaidf import __main__ as cli
from pyveoliaidf.config import ClientConfig
from pyveoliaidf.enum import PropertyNameEnum
from pyveoliaidf.errors import (
    LoginError,
    NotLoggedInError,
    PyVeoliaIDFError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    UnexpectedResponseError,
    UnknownContractError,
)
from pyveoliaidf.model import DailyReading
from pyveoliaidf.tls import build_ssl_context
from tests.unit.fakes import FakeApi
from tests.unit.helpers import record


class TestDailyReading:
    def make(self, **changes: Any) -> DailyReading:
        values: dict[str, Any] = {
            "time": "2026-10-05 21:00:00",
            "total_liter": 1,
            "daily_liter": 1,
            "type": "Mesuré",
            "timestamp": "t",
        }

        return DailyReading.model_validate({**values, **changes})

    def test_aliases_are_the_property_names_of_the_integration(self) -> None:
        reading = self.make()

        assert set(reading.as_dict()) == {member.value for member in PropertyNameEnum}

    def test_dict_form_writes_the_time_as_text(self) -> None:
        assert self.make().as_dict()["time"] == "2026-10-05 21:00:00"

    def test_fields_can_be_set_by_name(self) -> None:
        reading = DailyReading(time=datetime(2026, 10, 5, 21), total_liter=1, daily_liter=2, type="x", timestamp="t")

        assert reading.daily_liter == 2

    def test_is_immutable(self) -> None:
        with pytest.raises(ValidationError):
            self.make().total_liter = 5

    @pytest.mark.parametrize("changes", [{"total_liter": -1}, {"daily_liter": -1}, {"time": "never"}])
    def test_rejects_invalid_values(self, changes: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            self.make(**changes)


class TestErrors:
    def test_every_error_is_a_pyveoliaidf_error(self) -> None:
        for error in (
            ServerError("x"),
            LoginError("x"),
            RateLimitError("x"),
            SessionExpiredError("x"),
            UnexpectedResponseError("x"),
            NotLoggedInError("x"),
            UnknownContractError("x"),
        ):
            assert isinstance(error, PyVeoliaIDFError)

    def test_server_errors_carry_the_status(self) -> None:
        assert LoginError("x", 401).status_code == 401
        assert RateLimitError("x").status_code == 429
        assert ServerError("x").status_code is None

    def test_login_error_is_a_server_error(self) -> None:
        assert isinstance(LoginError("x"), ServerError)

    def test_builtin_bases_for_callers_that_catch_them(self) -> None:
        assert isinstance(NotLoggedInError("x"), ConnectionError)
        assert isinstance(UnknownContractError("C"), LookupError)
        assert UnknownContractError("C").contract_id == "C"


class TestConfig:
    def test_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            ClientConfig().retry_count = 5  # type: ignore[misc]

    def test_defaults_point_to_the_veolia_site(self) -> None:
        assert ClientConfig().base_url == "https://connexion.leaudiledefrance.fr"


class TestTls:
    def test_context_verifies_certificates_and_hosts(self) -> None:
        context = build_ssl_context()

        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname

    def test_context_trusts_the_bundled_intermediate(self) -> None:
        names = []
        for certificate in build_ssl_context().get_ca_certs():
            subject: Any = certificate["subject"]  # a tuple of tuples of (key, value) pairs
            names += [value for rdn in subject for key, value in rdn if key == "commonName"]

        assert "Gandi RSA Domain Validation Secure Server CA 3" in names


class TestPublicApi:
    def test_exports(self) -> None:
        for name in pyveoliaidf.__all__:
            assert hasattr(pyveoliaidf, name), name

    def test_version(self) -> None:
        assert pyveoliaidf.__version__

    def test_the_library_logger_has_a_null_handler(self) -> None:
        import logging

        assert any(isinstance(handler, logging.NullHandler) for handler in logging.getLogger("pyveoliaidf").handlers)

    def test_no_browser_dependency(self) -> None:
        importlib.import_module("pyveoliaidf")

        assert "selenium" not in sys.modules


class TestCli:
    async def test_run_returns_the_readings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = FakeApi(records=[record("2026-10-05", "143.868", "0.53")])
        monkeypatch.setattr(
            cli, "Client", lambda username, password, days: pyveoliaidf.Client(username, password, days, api=api)
        )

        data = await cli.run("u", "p", 7)

        assert data[0]["daily_liter"] == 530

    def test_main_prints_json(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        async def fake_run(username: Any, password: Any, days: Any) -> list[dict[str, str]]:
            return [{"time": "t"}]

        monkeypatch.setattr(cli, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["pyveoliaidf", "-u", "u", "-p", "p", "-d", "3"])

        assert cli.main() == 0
        assert json.loads(capsys.readouterr().out) == [{"time": "t"}]

    def test_main_reports_errors(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        async def failing_run(username: Any, password: Any, days: Any) -> NoReturn:
            raise LoginError("nope")

        monkeypatch.setattr(cli, "run", failing_run)
        monkeypatch.setattr(sys, "argv", ["pyveoliaidf", "-u", "u", "-p", "p"])

        assert cli.main() == 1
        assert "nope" in capsys.readouterr().out
