#!/usr/bin/env python3
"""Evaluation gate for {{ cookiecutter.friendly_name }}.

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``TriageService`` against a golden set with SDK-free local adapters and scores two metrics.
* **gate** - the promotion verdict from the shared authority (requires the ``gcp`` profile),
  resolved through the container's ``EvaluationGatePort`` so the authority is a binding like
  every other port rather than a client constructed here.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).

Four properties are worth keeping when you extend this, because each closes a way a gate reports
a confident number over something it did not measure:

1. **The bars live in ``eval/rubrics/*.yaml``, not in a dict here.** ``agent_eval_kit.rubrics``
   reads them, and ``assert_covers`` fails the build in BOTH directions: a metric scored with no
   reviewed bar, and a bar that names no metric. The second is the one that rots quietly, because
   it rots toward looking well governed.
2. **The falsification proof runs FIRST, inside this run.** ``prove_before_scoring`` executes the
   red cases before a single golden score is trusted. Run only in ``tests/``, a proof says the
   metric could have gone red on some machine at some point; run here it says the metric about to
   score this corpus can go red, in this process, with these thresholds.
3. **The denominator is checked against the bar.** A 0.80 accuracy bar over four cases is a 1.0
   wearing a 0.80 label, and nothing else in a repo compares a threshold with a corpus size.
4. **The leak scan reads what the service actually persisted.** Building a string here and
   scanning that would score the redactor against itself over text the service never produced.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_eval_kit import (
    EvalMetricResult,
    EvalReport,
    assert_can_go_red,
    assert_denominator_supports,
    dataset_digest,
    eval_main,
    load_jsonl,
    load_rubrics,
    prove_before_scoring,
)
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
RUBRICS = _REPO_ROOT / "eval" / "rubrics"

#: The reviewed bars, read from the rubric files that carry the argument for each number. There
#: is deliberately no fallback dict: a fallback is a second home for a number that must have one.
THRESHOLDS: dict[str, float] = load_rubrics(RUBRICS).thresholds()

#: The metrics this runner scores. Named here so `assert_covers` can compare it with the rubric
#: set in both directions rather than only checking that every scored metric has a bar.
SCORED: tuple[str, ...] = ("decision_accuracy", "pii_safety")


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _service() -> tuple[TriageService, LocalAuditAdapter]:
    settings = Settings(profile="local", audit_path=":memory:")
    audit = LocalAuditAdapter(settings)
    # The no-op tracer keeps smoke mode SDK-free and offline, which is the whole point of it.
    return TriageService(audit, LocalNoopTracerAdapter(settings)), audit


# --------------------------------------------------------------------------- #
# Scorers. Each is imported by tests/unit/test_not_falsely_green.py, which falsifies THESE
# functions rather than a local re-implementation of them: a proof against a local copy shows
# the copy works while the gate stays blind.
# --------------------------------------------------------------------------- #
def score_decision_accuracy(result: Any, case: dict[str, Any]) -> float:
    """1.0 iff the triaged severity equals the severity a reviewer assigned by reading the case."""
    return 1.0 if result.severity.value == case["expected_severity"] else 0.0


def score_pii_safety(records: list[str], planted: list[str]) -> float:
    """No raw identifier may survive into an audit record, by the pack rows OR by literal.

    Two oracles, because they fail independently. The pack scan uses the same rows the runtime
    redactor masks with, so a redactor that skipped a field is caught; the planted-literal check
    fires even when a pattern row is broken, which is precisely when the first one cannot.
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def audit_texts(rows: list[dict[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of every audit record, which is what a leak scan must read.

    ``actor`` is excluded deliberately: it is the verified principal and an identifier by design,
    so a blanket scan over a whole row could never go green, and a metric nobody can make green
    gets deleted rather than fixed. Add a field here whenever the audit record grows one that
    carries content.
    """
    return [str(row.get("redacted_summary", "")) for row in rows]


# --------------------------------------------------------------------------- #
# The falsification proofs, run before any golden score is trusted
# --------------------------------------------------------------------------- #
def _prove_decision_accuracy_can_go_red() -> None:
    case = {"expected_severity": "high"}

    class _Result:
        def __init__(self, value: str) -> None:
            self.severity = type("S", (), {"value": value})()

    assert_can_go_red(
        lambda result: score_decision_accuracy(result, case),
        green=_Result("high"),
        red=_Result("low"),  # the engine reached a different severity than the reviewer
        threshold=THRESHOLDS["decision_accuracy"],
        metric="decision_accuracy",
    )


def _prove_pii_safety_can_go_red() -> None:
    planted = ["S1234567D"]
    assert_can_go_red(
        lambda records: score_pii_safety(records, planted),
        green=["Gamma LLP: triaged high :: NRIC [REDACTED:SG_NRIC_FIN] on file"],
        red=["Gamma LLP: triaged high :: NRIC S1234567D on file"],  # redaction bypassed
        threshold=THRESHOLDS["pii_safety"],
        metric="pii_safety",
    )


def run_smoke(dataset: Path) -> EvalReport:
    # The bars and the metrics must agree in both directions before anything is scored.
    load_rubrics(RUBRICS).assert_covers(SCORED)
    # And each metric must be shown able to go red, here, with these thresholds.
    prove_before_scoring(_prove_decision_accuracy_can_go_red, _prove_pii_safety_can_go_red)

    cases = load_jsonl(dataset, required=("id", "subject", "text", "expected_severity"))
    planted = [str(case["planted"]) for case in cases if case.get("planted")]
    if not planted:
        raise SystemExit(
            f"{dataset}: no golden case plants an identifier, so pii_safety would score a "
            "vacuous 1.0 over a corpus with nothing to leak"
        )
    # A 0.80 bar tolerates one miss only over five cases or more. Below that it is a 1.0 with a
    # friendlier label, and a reviewer reading 0.80 believes there is headroom that is not there.
    assert_denominator_supports(
        THRESHOLDS["decision_accuracy"], len(cases), metric="decision_accuracy"
    )

    service, audit = _service()
    decision_scores: list[float] = []
    for case in cases:
        result = service.triage(
            TriageInput(subject=str(case["subject"]), text=str(case["text"])), actor="eval-bot"
        )
        decision_scores.append(score_decision_accuracy(result, case))

    results = (
        EvalMetricResult.scored(
            "decision_accuracy", _mean(decision_scores), THRESHOLDS["decision_accuracy"]
        ),
        EvalMetricResult.scored(
            "pii_safety",
            score_pii_safety(audit_texts(list(audit.log.read_all())), planted),
            THRESHOLDS["pii_safety"],
        ),
    )
    return EvalReport(
        dataset=str(dataset),
        results=results,
        n_examples=len(cases),
        dataset_digest=dataset_digest(dataset),
        evaluator="offline heuristic (no cloud creds)",
    )


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
            description="Offline smoke and promotion evaluation gate.",
        )
    )
