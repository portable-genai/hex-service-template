"""Review routing has a switch, default on, and every caller says what happened to a hand-off.

The fleet's runtime-control contract (2026-09-24). Review routing is the one cheap runtime
control this service has: ``{{ cookiecutter.env_prefix }}_REVIEW_ROUTING`` is read in three
states; off binds a disabled router and says so at startup; on under the managed profile refuses
to boot without a console; and the API, the agent tool and the CLI report ``review_routing``
rather than failing an already-scored triage when the console is unreachable.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from {{ cookiecutter.package_name }} import (
    config as config_module,
)
from {{ cookiecutter.package_name }}.adapters import (
    controls as controls_module,
)
from {{ cookiecutter.package_name }}.adapters.controls import (
    DisabledReviewRouter,
    RecordingReviewRouter,
    ReviewRouting,
)
from {{ cookiecutter.package_name }}.adapters.local.review_router import (
    LocalReviewRouter,
)
from {{ cookiecutter.package_name }}.agent.tools import triage_case
from {{ cookiecutter.package_name }}.api import app as api_module
from {{ cookiecutter.package_name }}.api.app import app
from {{ cookiecutter.package_name }}.cli.main import main as cli_main
from {{ cookiecutter.package_name }}.config import (
    REVIEW_ROUTING_ENV,
    Container,
    ControlSwitches,
    ProfileChoice,
    Settings,
    build_container,
    warn_switched_off,
)
from {{ cookiecutter.package_name }}.domain.models import TriageResult
from {{ cookiecutter.package_name }}.domain.triage_service import TriageService
from {{ cookiecutter.package_name }}.envread import ConfiguredEmptyError

from tests.conftest import local_settings
from tests.fixtures import sample_cases

_LOOPBACK = ("127.0.0.1", 50000)
_PROFILE_ENV = "{{ cookiecutter.env_prefix }}_PROFILE"
_GCP = ProfileChoice("gcp", True)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(REVIEW_ROUTING_ENV, raising=False)
    monkeypatch.delenv("HUMAN_REVIEW_URL", raising=False)
    # The CLI and the API load settings from the environment; both run the local profile here.
    monkeypatch.setenv(_PROFILE_ENV, "local")
    # The API caches its container for the process; each test here states its own posture.
    api_module._container.cache_clear()
    yield
    api_module._container.cache_clear()


def _result(case=sample_cases.ESCALATING_CASE) -> TriageResult:  # type: ignore[no-untyped-def]
    container = build_container(local_settings())
    service = TriageService(container.audit, container.tracer, container.guardrail)
    return service.triage(case, actor=sample_cases.ACTOR)


def _managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "resolve_profile", lambda environ=None: _GCP)


# --------------------------------------------------------------------------- #
# Three states
# --------------------------------------------------------------------------- #
def test_routing_is_on_when_nothing_is_said() -> None:
    assert Settings.load().controls == ControlSwitches(review_routing=True)


def test_routing_switched_off_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    assert Settings.load().controls.switched_off() == (REVIEW_ROUTING_ENV,)


def test_an_emptied_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "")
    with pytest.raises(ConfiguredEmptyError, match=REVIEW_ROUTING_ENV):
        Settings.load()


def test_an_unrecognised_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "sometimes")
    with pytest.raises(ValueError, match=REVIEW_ROUTING_ENV):
        Settings.load()


# --------------------------------------------------------------------------- #
# Off binds the disabled router, and says so once
# --------------------------------------------------------------------------- #
def test_off_binds_the_disabled_router() -> None:
    settings = local_settings(controls=ControlSwitches(review_routing=False))
    assert isinstance(Container(settings).review_router, DisabledReviewRouter)


def test_on_binds_the_profile_router() -> None:
    assert not isinstance(Container(local_settings()).review_router, DisabledReviewRouter)


def test_the_off_posture_is_logged_once_however_many_containers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    warn_switched_off.cache_clear()
    settings = local_settings(controls=ControlSwitches(review_routing=False))
    with caplog.at_level(logging.WARNING, logger=config_module.__name__):
        for _ in range(3):
            build_container(settings)
    assert caplog.text.count(REVIEW_ROUTING_ENV) == 1


# --------------------------------------------------------------------------- #
# On has to work: checked at boot under the managed profile
# --------------------------------------------------------------------------- #
def test_routing_on_under_gcp_without_a_console_refuses_at_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _managed(monkeypatch)
    with pytest.raises(ConfiguredEmptyError, match="HUMAN_REVIEW_URL"):
        Settings.load()


def test_routing_stated_off_under_gcp_needs_no_console(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "false")
    assert Settings.load().controls.review_routing is False


def test_routing_on_under_gcp_with_a_console_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    monkeypatch.setenv("HUMAN_REVIEW_URL", "https://review.example.test")
    assert Settings.load().review_url == "https://review.example.test"


# --------------------------------------------------------------------------- #
# The four routing outcomes
# --------------------------------------------------------------------------- #
class _Accepting:
    def route(self, result: TriageResult, *, maker: str, tenant: str = "") -> str:
        return "review-1"


class _Refusing:
    def route(self, result: TriageResult, *, maker: str, tenant: str = "") -> str:
        raise ConnectionError("console unreachable")


def test_routing_outcomes_take_each_of_their_four_values() -> None:
    escalated = _result()

    not_required = RecordingReviewRouter(_Accepting())
    assert not_required.route(_result(sample_cases.ROUTINE_CASE), maker="m") == ""
    assert not_required.outcome is ReviewRouting.NOT_REQUIRED

    routed = RecordingReviewRouter(_Accepting())
    assert routed.route(escalated, maker="m") == "review-1"
    assert routed.outcome is ReviewRouting.ROUTED

    off = RecordingReviewRouter(DisabledReviewRouter(local_settings()))
    assert off.route(escalated, maker="m") == ""
    assert off.outcome is ReviewRouting.OFF

    failed = RecordingReviewRouter(_Refusing())
    assert failed.route(escalated, maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED


def test_a_failed_hand_off_is_reported_and_logged_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed = RecordingReviewRouter(_Refusing())
    with caplog.at_level(logging.WARNING, logger=controls_module.__name__):
        assert failed.route(_result(), maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED
    assert "ConnectionError" in caplog.text


# --------------------------------------------------------------------------- #
# Every caller reports it: the API, the agent tool, the CLI
# --------------------------------------------------------------------------- #
def _post(case=sample_cases.ESCALATING_CASE):  # type: ignore[no-untyped-def]
    return TestClient(app, client=_LOOPBACK).post(
        "/v1/triage",
        json={"subject": case.subject, "text": case.text},
        headers={"X-Dev-Persona": "auditor"},
    )


def test_the_api_reports_a_routed_hand_off() -> None:
    body = _post().json()
    assert body["review_routing"] == "routed"
    assert body["review_ref"]


def test_the_api_reports_not_required_for_a_routine_case() -> None:
    body = _post(sample_cases.ROUTINE_CASE).json()
    assert body["review_routing"] == "not_required"
    assert body["review_ref"] == ""


def test_the_api_reports_routing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    body = _post().json()
    assert body["review_routing"] == "off"
    assert body["review_ref"] == ""


def test_the_api_reports_a_failed_hand_off_instead_of_failing_the_triage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(LocalReviewRouter, "route", _Refusing.route)
    response = _post()
    assert response.status_code == 200
    assert response.json()["review_routing"] == "failed"
    assert response.json()["review_ref"] == ""


def test_the_agent_tool_reports_the_hand_off() -> None:
    case = sample_cases.ESCALATING_CASE
    payload = triage_case(case.subject, case.text, settings=local_settings())
    assert payload["review_routing"] == "routed"


def test_the_agent_tool_reports_a_failed_hand_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LocalReviewRouter, "route", _Refusing.route)
    case = sample_cases.ESCALATING_CASE
    payload = triage_case(case.subject, case.text, settings=local_settings())
    assert payload["review_routing"] == "failed"
    assert payload["review_ref"] == ""


def test_the_cli_reports_the_hand_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    case = sample_cases.ESCALATING_CASE
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    assert cli_main(["triage", case.subject, case.text]) == 0
    assert "human review hand-off : off" in capsys.readouterr().out


def test_the_cli_reports_a_failed_hand_off_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(LocalReviewRouter, "route", _Refusing.route)
    case = sample_cases.ESCALATING_CASE
    assert cli_main(["triage", case.subject, case.text]) == 0
    assert "human review hand-off : failed" in capsys.readouterr().out
