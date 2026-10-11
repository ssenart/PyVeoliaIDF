from typing import Any

import pytest

from pyveoliaidf.aura import (
    AuraContext,
    action_result,
    error_messages,
    event_descriptors,
    parse_context,
    parse_response,
    redirect_url,
)
from pyveoliaidf.errors import UnexpectedResponseError
from tests.unit.helpers import FRONTDOOR_PATH, aura_body, event, page, redirect_event


class TestParseContext:
    def test_takes_the_context_that_names_the_framework_build(self) -> None:
        context = parse_context(page(fwuid="build-7", app="siteforce:communityApp"))

        assert context.fwuid == "build-7"
        assert context.app == "siteforce:communityApp"
        assert context.mode == "PRODDEBUG"
        assert context.loaded == {"APPLICATION@markup://siteforce:communityApp": "1811_abc"}

    def test_page_without_context(self) -> None:
        with pytest.raises(UnexpectedResponseError, match="no Aura context"):
            parse_context("<html></html>")

    def test_page_where_no_context_has_a_fwuid(self) -> None:
        html = '<script src="/s/sfsites/l/%7B%22mode%22%3A%22PROD%22%7D/app.js"></script>'

        with pytest.raises(UnexpectedResponseError, match="fwuid"):
            parse_context(html)

    def test_skips_a_context_that_is_not_json(self) -> None:
        html = '<script src="/s/sfsites/l/%7Bnot-json%7D/app.js"></script>' + page(fwuid="ok")

        assert parse_context(html).fwuid == "ok"

    def test_context_without_loaded_components(self) -> None:
        html = '<script src="/s/sfsites/l/%7B%22mode%22%3A%22P%22%2C%22app%22%3A%22a%3Ab%22%2C%22fwuid%22%3A%22f%22%7D/x.js">'

        assert parse_context(html).loaded == {}


class TestAuraContext:
    def test_json_has_the_fields_the_server_expects(self) -> None:
        context = AuraContext(mode="PROD", app="a:b", fwuid="f", loaded={"k": "v"})

        assert (
            context.as_json()
            == '{"mode":"PROD","fwuid":"f","app":"a:b","loaded":{"k":"v"},"dn":[],"globals":{},"uad":true}'
        )

    def test_takes_a_new_framework_build_and_more_loaded_components(self) -> None:
        context = AuraContext(mode="PROD", app="a:b", fwuid="old", loaded={"k": "v"})

        updated = context.updated_from({"fwuid": "new", "loaded": {"k2": "v2"}})

        assert updated.fwuid == "new"
        assert updated.loaded == {"k": "v", "k2": "v2"}
        assert context.fwuid == "old"  # the context is immutable

    def test_ignores_what_it_cannot_use(self) -> None:
        context = AuraContext(mode="PROD", app="a:b", fwuid="old", loaded={"k": "v"})

        assert context.updated_from({"fwuid": "", "loaded": "nope"}) == context
        assert context.updated_from({}) == context


class TestParseResponse:
    def test_plain_json(self) -> None:
        assert parse_response('{"actions": []}') == {"actions": []}

    def test_json_with_text_around_it(self) -> None:
        assert parse_response('while(1);\n{"actions": []}\n/*ERROR*/') == {"actions": []}

    @pytest.mark.parametrize("text", ["", "no json here", "} {"])
    def test_no_json(self, text: str) -> None:
        with pytest.raises(UnexpectedResponseError, match="no JSON"):
            parse_response(text)

    def test_invalid_json(self) -> None:
        with pytest.raises(UnexpectedResponseError, match="not valid JSON"):
            parse_response("{not json}")


class TestEvents:
    def test_descriptors(self) -> None:
        events: list[Any] = [event("invalidSession"), {"no": "descriptor"}, "junk"]
        body = aura_body(events=events)

        assert event_descriptors(body) == ["markup://aura:invalidSession"]

    def test_no_events(self) -> None:
        assert event_descriptors({}) == []
        assert event_descriptors({"events": "nope"}) == []

    def test_redirect_url(self) -> None:
        assert redirect_url(aura_body(events=[event("other"), redirect_event()])) == FRONTDOOR_PATH

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"events": "nope"},
            {"events": [event("clientOutOfSync")]},
            {"events": [{"descriptor": "markup://aura:clientRedirect", "attributes": {"values": {}}}]},
            {"events": [{"descriptor": "markup://aura:clientRedirect", "attributes": {"values": {"url": ""}}}]},
        ],
    )
    def test_no_redirect_url(self, body: dict[str, Any]) -> None:
        assert redirect_url(body) is None


class TestActionResult:
    def test_first_action(self) -> None:
        assert action_result(aura_body("value"))["returnValue"] == "value"

    @pytest.mark.parametrize("body", [{}, {"actions": []}, {"actions": "nope"}, {"actions": ["junk"]}])
    def test_no_action(self, body: dict[str, Any]) -> None:
        with pytest.raises(UnexpectedResponseError, match="no action"):
            action_result(body)

    def test_error_messages(self) -> None:
        result = {"error": [{"message": "first"}, {"message": "second"}, {"other": 1}]}

        assert error_messages(result) == "first; second"

    @pytest.mark.parametrize("result", [{}, {"error": "nope"}, {"error": []}, {"error": [{"message": 3}]}])
    def test_no_error_message(self, result: dict[str, Any]) -> None:
        assert error_messages(result) == "no reason given"
