"""API surface: verified-principal identity, fail-closed S2S, security headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from {{ cookiecutter.package_name }}.domain.models import (
    TriageInput,
)

from tests.fixtures import sample_cases

_TOKEN_ENV = "{{ cookiecutter.env_prefix }}_S2S_TOKEN"


def _triage_body(case: TriageInput = sample_cases.ESCALATING_CASE) -> dict[str, str]:
    return {"subject": case.subject, "text": case.text}


def test_triage_uses_the_verified_principal_as_actor(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/triage",
        json=_triage_body(),
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "high"
    assert body["requires_human_review"] is True
    # Rule R8: the escalation was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"]


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/triage",
        json=_triage_body(sample_cases.ROUTINE_CASE),
        headers={"X-Dev-Persona": "ghost"},
    )
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "{{ cookiecutter.region }}"


def test_healthz_states_the_provenance_the_ui_banner_renders(api_client: TestClient) -> None:
    """The service half of the banner contract (org decision, 2026-08-30).

    The UI must never infer either value. A console that read its runtime from
    ``window.location`` would be right until the deployment served through a proxy and
    wrong silently after that, so the service is asked and the service answers.
    """
    body = api_client.get("/healthz").json()
    assert body["runtime"] == "local"
    # `no-model`, not `deterministic-offline-stub`: this template binds no generative port
    # at all, and the stub string would claim a model-shaped port bound to a stub. The two
    # are different facts and a reviewer is entitled to know which one they are reading.
    assert body["generator_model"] == "no-model"


@pytest.mark.parametrize(
    ("profile", "expected"), [("local", "local"), ("gcp", "gcp"), ("onprem", "local")]
)
def test_the_runtime_follows_the_profile_and_onprem_is_not_gcp(profile: str, expected: str) -> None:
    """``onprem`` reads local, and that is the whole point of the profile.

    It runs on the adopter's own iron. Treating any non-local profile as "on GCP" would put
    the wrong sentence at the top of every page of the one deployment whose selling point is
    that it is not on GCP.
    """
    from {{ cookiecutter.package_name }}.config import Settings

    assert Settings(profile=profile).runtime == expected


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
