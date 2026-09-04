#!/usr/bin/env python3
"""Evaluation gate for {{ cookiecutter.friendly_name }}.

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``TriageService`` against a golden set with SDK-free local adapters and scores two metrics.
* **gate** - the promotion verdict from the shared model-quality-gate authority (needs the ``gcp``
  profile), resolved through the container's ``EvaluationGatePort`` so the authority is a
  binding like every other port rather than a client constructed here.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_eval_kit import EvalMetricResult, EvalReport, eval_main
from pii_kit import pack_leak

from {{ cookiecutter.package_name }}.adapters.local.audit import (
    LocalAuditAdapter,
)
from {{ cookiecutter.package_name }}.adapters.local.tracer import (
    LocalNoopTracerAdapter,
)
from {{ cookiecutter.package_name }}.config import (
    Settings,
    build_container,
)
from {{ cookiecutter.package_name }}.domain.models import (
    TriageInput,
)
from {{ cookiecutter.package_name }}.domain.pii import (
    PII_PATTERNS,
)
from {{ cookiecutter.package_name }}.domain.triage_service import (
    TriageService,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {"decision_accuracy": 0.80, "pii_safety": 0.99}


def _load(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    settings = Settings(profile="local", audit_path=":memory:")
    audit = LocalAuditAdapter(settings)
    # The no-op tracer keeps smoke mode SDK-free and offline, which is the whole point of it.
    service = TriageService(audit, LocalNoopTracerAdapter(settings))

    decision_scores: list[float] = []
    for case in cases:
        result = service.triage(
            TriageInput(subject=case["subject"], text=case["text"]), actor="eval-bot"
        )
        decision_scores.append(1.0 if result.severity.value == case["expected_severity"] else 0.0)

    # pii_safety: no raw identifier may survive into any audit record. The pack scan uses the
    # same rows the redactor masks with; the planted-literal check is an independent oracle that
    # fires even if a row is broken (the two-part scorer lesson from the C4 rollout).
    records = [str(e.get("redacted_summary", "")) for e in audit.log.read_all()]
    planted = [case["planted"] for case in cases if case.get("planted")]
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    pii_safety = 0.0 if (pack_leaked or literal_leaked) else 1.0

    results = (
        EvalMetricResult.scored(
            "decision_accuracy", _mean(decision_scores), THRESHOLDS["decision_accuracy"]
        ),
        EvalMetricResult.scored("pii_safety", pii_safety, THRESHOLDS["pii_safety"]),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"{{ cookiecutter.env_prefix }}_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    # Resolved through the CONTAINER, not by constructing a client here. The binding is then
    # configuration like every other port: an on-prem deployment gets an explicit refusal instead
    # of a client pointed at a service it does not run, and a repo cannot quietly grow a second,
    # differently-configured route to the same authority.
    container = build_container(settings)
    report = container.evaluation.evaluate(str(dataset))
    if not isinstance(report, EvalReport):
        raise SystemExit("EvaluationGatePort.evaluate did not return an EvalReport")
    return report, bool(container.evaluation.gate(str(dataset)))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline and managed evaluation gate for {{ cookiecutter.project_slug }}.",
        )
    )
