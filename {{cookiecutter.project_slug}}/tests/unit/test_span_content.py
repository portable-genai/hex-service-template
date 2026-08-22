"""A span carries structure, never content, and this is the test that keeps it that way.

A trace backend is not the WORM audit trail. It has no redaction stage, a wider read
audience and no retention rule written against a regulator's requirement, so anything
content-shaped that reaches a span attribute has left the boundary that redaction exists to
hold, and left it silently: nothing fails, nothing logs, and the leak is discovered by
whoever opens the trace viewer.

The pressure this resists is real and reasonable-sounding. Someone debugging a slow or
wrong triage adds "just the case text" to the span, because that is the one thing the trace
does not tell them. The allowlist test below is what turns that from a quiet regression
into a failed build.

Rendered repos inherit this file, so the guard exists before the first vertical span does.
"""

from __future__ import annotations

from contextlib import contextmanager

from {{ cookiecutter.package_name }}.adapters.local.audit import (
    LocalAuditAdapter,
)
from {{ cookiecutter.package_name }}.config import (
    Settings,
)
from {{ cookiecutter.package_name }}.domain.models import (
    TriageInput,
)
from {{ cookiecutter.package_name }}.domain.triage_service import (
    TriageService,
)

#: Obviously fictional, and shaped like the identifiers redaction is meant to catch, so a
#: span that carried the case text would fail on this string rather than on a subtlety.
_PLANTED_IDENTIFIER = "S1234567D"
_CASE_TEXT = f"urgent leak reported by holder {_PLANTED_IDENTIFIER} (FICTIONAL)"
_ACTOR = "analyst@bank.example"

#: The complete set of attribute keys a triage span may carry. Adding to this is a decision
#: about what leaves the trust boundary, so it is made here rather than at the call site.
_ALLOWED_ATTRIBUTES = {"action", "actor"}


class _RecordingTracer:
    """Captures span names and attributes. Satisfies ObservabilityTracerPort structurally."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str):  # type: ignore[no-untyped-def]
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _triage() -> _RecordingTracer:
    tracer = _RecordingTracer()
    audit = LocalAuditAdapter(Settings(profile="local", audit_path=":memory:"))
    service = TriageService(audit, tracer)  # type: ignore[arg-type]
    service.triage(TriageInput("ACME (FICTIONAL)", _CASE_TEXT), actor=_ACTOR)
    return tracer


def test_one_triage_opens_exactly_one_span() -> None:
    tracer = _triage()
    assert [name for name, _ in tracer.spans] == ["triage.assess"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    _, attributes = _triage().spans[0]
    assert attributes["action"] == "triage"
    assert attributes["actor"] == _ACTOR


def test_the_attribute_keys_are_a_fixed_allowlist() -> None:
    """Widening this set is a trust-boundary decision, so it cannot happen by accident."""
    for _, attributes in _triage().spans:
        assert set(attributes) == _ALLOWED_ATTRIBUTES, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_ALLOWED_ATTRIBUTES here deliberately"
        )


def test_no_attribute_value_carries_the_case_text_or_a_planted_identifier() -> None:
    emitted = " ".join(value for _, attributes in _triage().spans for value in attributes.values())
    assert _PLANTED_IDENTIFIER not in emitted
    assert "leak" not in emitted.lower(), "the case text reached a span attribute"
