"""The ``live`` profile: the laptop stack, with a real local model behind any model port.

A newly scaffolded service binds no model port, so here ``live`` binds exactly what ``local``
binds and takes the same laptop posture. The day a repository adds a model port, its ``live``
entry binds a kit-backed adapter under ``adapters/live/`` (the shared
``hex_service_kit.localmodel`` client, never a hand-rolled one) and the banner test below is what
makes the provenance banner name the local model that answers.
"""

from __future__ import annotations

import pytest

from {{ cookiecutter.package_name }} import config
from {{ cookiecutter.package_name }}.adapters.local.identity import (
    LocalIdentityAdapter,
)
from {{ cookiecutter.package_name }}.config import (
    DEFAULT_BINDINGS,
    LIVE_PROFILE,
    ProfileChoice,
    build_container,
)
from {{ cookiecutter.package_name }}.ports import (
    PORT_PROTOCOLS,
)

from tests.conftest import local_settings


def test_the_container_builds_every_port_under_live() -> None:
    container = build_container(local_settings(profile=LIVE_PROFILE))
    for port, protocol in PORT_PROTOCOLS.items():
        assert isinstance(getattr(container, port), protocol), port


def test_live_binds_only_local_or_live_adapters() -> None:
    """``live`` is a laptop lane: each port binds its ``local`` adapter or a kit-backed live one."""
    for port, table in DEFAULT_BINDINGS.items():
        binding = table["live"]
        assert binding == table["local"] or ".adapters.live." in binding, port


def test_live_takes_the_laptop_posture() -> None:
    choice = ProfileChoice(profile=LIVE_PROFILE, explicit=True)
    assert choice.exposure_profile == config.LOCAL_PROFILE
    assert choice.bind_profile == config.LOCAL_PROFILE
    # The seeded personas construct under a deliberate live, exactly as under local.
    LocalIdentityAdapter(local_settings(profile=LIVE_PROFILE))


def test_a_scaffold_with_no_model_port_says_so_under_live() -> None:
    assert local_settings(profile=LIVE_PROFILE).generator_model == "no-model"


def test_a_live_model_port_names_the_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once a model port is bound to a live adapter, the banner names the model it calls."""
    monkeypatch.setattr(config, "_GENERATOR_PORT", "llm")
    monkeypatch.setenv("LOCAL_MODEL", "some-org/some-local-model")
    table = {
        "local": "pkg.adapters.local.llm:LocalDeterministicLLMAdapter",
        "live": "pkg.adapters.live.llm:LocalModelLLMAdapter",
        "gcp": "pkg.adapters.gcp.llm:CloudLLMAdapter",
        "onprem": "pkg.adapters.onprem.llm:OnPremLLMAdapter",
    }
    adapters = {**DEFAULT_BINDINGS, "llm": table}
    live = local_settings(profile=LIVE_PROFILE, adapters=adapters)
    assert live.generator_model == "some-org/some-local-model"
    # The same port bound to the offline stub under live says stub, not a model it never calls.
    stubbed_table = dict(table, live=table["local"])
    stubbed = local_settings(profile=LIVE_PROFILE, adapters=dict(adapters, llm=stubbed_table))
    assert stubbed.generator_model == "deterministic-offline-stub"
