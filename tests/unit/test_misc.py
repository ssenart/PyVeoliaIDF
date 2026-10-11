import dataclasses
import json
import logging
import ssl
import sys
from datetime import date, timedelta
from typing import Any

import pytest

import pyveoliaidf
from pyveoliaidf import __main__ as cli
from pyveoliaidf.config import ClientConfig
from pyveoliaidf.errors import (
    LoginError,
    NotLoggedInError,
    PyVeoliaIDFError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    UnexpectedResponseError,
    UnknownContractError,
    UnknownMeterError,
)
from pyveoliaidf.tls import build_ssl_context
from tests.unit.fakes import FakeApi, daily_records

TODAY = date.today()


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
            UnknownMeterError("x"),
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
        assert isinstance(UnknownMeterError("M"), LookupError)
        assert UnknownContractError("C").contract_number == "C"
        assert UnknownMeterError("M").meter_number == "M"


class TestConfig:
    def test_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            ClientConfig().retry_count = 5  # type: ignore[misc]

    def test_defaults_point_to_the_veolia_site(self) -> None:
        assert ClientConfig().base_url == "https://connexion.leaudiledefrance.fr"

    def test_the_default_window_is_below_what_the_site_accepts(self) -> None:
        assert ClientConfig().max_window_days <= 100


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

    def test_exports_the_model_and_the_layers(self) -> None:
        for name in ("Client", "ConsumptionHistory", "Contract", "Reading", "Step", "VeoliaApiClient", "AuraClient"):
            assert name in pyveoliaidf.__all__

    def test_version(self) -> None:
        assert pyveoliaidf.__version__

    def test_the_library_logger_has_a_null_handler(self) -> None:
        assert any(isinstance(handler, logging.NullHandler) for handler in logging.getLogger("pyveoliaidf").handlers)

    def test_no_browser_dependency(self) -> None:
        assert "selenium" not in sys.modules


class TestCli:
    def args(self, *argv: str) -> Any:
        return cli.build_parser().parse_args(list(argv))

    def patch_client(self, monkeypatch: pytest.MonkeyPatch, api: FakeApi) -> list[tuple[str, str]]:
        built: list[tuple[str, str]] = []

        def make_client(username: str, password: str, **kwargs: Any) -> pyveoliaidf.Client:
            built.append((username, password))
            return pyveoliaidf.Client(username, password, api=api, **kwargs)

        monkeypatch.setattr(cli, "Client", make_client)

        return built

    async def test_run_returns_the_history_as_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.patch_client(monkeypatch, FakeApi(records=daily_records(TODAY - timedelta(days=5), 5)))

        result: Any = await cli.run(self.args("-d", "7"), "u", "p")

        assert result["step"] == "day"
        assert result["readings"][0]["volume_m3"] == "0.5"  # decimals are exact in the JSON

    async def test_run_passes_the_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = FakeApi(contracts={"A": ("X1",), "B": ("X2",)}, week_records=[])
        self.patch_client(monkeypatch, api)

        await cli.run(
            self.args(
                "--step", "week", "--contract", "B", "--meter", "X2", "--start", "2026-01-01", "--end", "2026-02-01"
            ),
            "u",
            "p",
        )

        assert api.consumption_calls[0][:3] == ("B", "X2", pyveoliaidf.Step.WEEK)
        assert api.consumption_calls[0][3:] == (date(2026, 1, 1), date(2026, 2, 1))

    async def test_run_lists_the_contracts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.patch_client(monkeypatch, FakeApi(contracts={"A": ("X1", "X2")}))

        result: Any = await cli.run(self.args("--contracts"), "u", "p")

        assert [meter["number"] for meter in result[0]["meters"]] == ["X1", "X2"]

    def test_the_options_have_defaults(self) -> None:
        args = self.args()

        assert (args.days, args.step, args.contracts, args.start, args.end) == (365, "day", False, None, None)

    def test_the_version_is_printed(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(sys, "argv", ["pyveoliaidf", "--version"])

        with pytest.raises(SystemExit) as exit_:
            cli.main()

        assert exit_.value.code == 0
        assert capsys.readouterr().out.strip() == f"pyveoliaidf {pyveoliaidf.__version__}"

    def test_verbose_logs_to_the_standard_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        configured: dict[str, Any] = {}

        async def fake_run(args: Any, username: str, password: str) -> Any:
            return {}

        monkeypatch.setattr(cli, "run", fake_run)
        monkeypatch.setattr("logging.basicConfig", lambda **kwargs: configured.update(kwargs))
        monkeypatch.setattr(sys, "argv", ["pyveoliaidf", "-u", "u", "-p", "p", "-v"])

        assert cli.main() == 0
        assert configured["level"] == logging.DEBUG
        assert configured["stream"] is sys.stderr

    def test_without_verbose_the_logging_is_left_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_run(args: Any, username: str, password: str) -> Any:
            return {}

        def fail(**kwargs: Any) -> None:
            raise AssertionError("logging was configured")

        monkeypatch.setattr(cli, "run", fake_run)
        monkeypatch.setattr("logging.basicConfig", fail)
        monkeypatch.setattr(sys, "argv", ["pyveoliaidf", "-u", "u", "-p", "p"])

        assert cli.main() == 0

    def test_the_credentials_come_from_the_options_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VEOLIAIDF_USERNAME", "env-user")
        monkeypatch.setenv("VEOLIAIDF_PASSWORD", "env-password")

        assert cli.credentials(self.args("-u", "opt-user", "-p", "opt-password")) == ("opt-user", "opt-password")

    def test_the_credentials_come_from_the_environment_next(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VEOLIAIDF_USERNAME", "env-user")
        monkeypatch.setenv("VEOLIAIDF_PASSWORD", "env-password")

        assert cli.credentials(self.args()) == ("env-user", "env-password")

    def test_the_credentials_are_prompted_for_last(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda prompt: "typed-user")
        monkeypatch.setattr("getpass.getpass", lambda prompt: "typed-password")

        assert cli.credentials(self.args()) == ("typed-user", "typed-password")

    def test_main_prints_json(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        async def fake_run(args: Any, username: str, password: str) -> Any:
            return {"readings": []}

        monkeypatch.setattr(cli, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["pyveoliaidf", "-u", "u", "-p", "p", "-d", "3"])

        assert cli.main() == 0
        assert json.loads(capsys.readouterr().out) == {"readings": []}

    def test_main_reports_errors(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        async def failing_run(args: Any, username: str, password: str) -> Any:
            raise LoginError("nope")

        monkeypatch.setattr(cli, "run", failing_run)
        monkeypatch.setattr(sys, "argv", ["pyveoliaidf", "-u", "u", "-p", "p"])

        assert cli.main() == 1
        assert "nope" in capsys.readouterr().out
