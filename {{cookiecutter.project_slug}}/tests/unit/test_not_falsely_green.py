"""Prove every eval metric can go RED: a degraded case must score below its threshold.

A metric that cannot fail proves nothing, and the way that happens is rarely dramatic: a scorer
reads the product's own output, a golden set plants no target, a refactor turns a comparison into
a constant. Any of those leaves a confident 1.000 in the report and nothing anywhere says so.

Two properties make this file evidence rather than ceremony, and both are easy to lose:

* **The scorers are IMPORTED from ``eval.run_eval``, never re-implemented here.** A proof written
  against a local copy shows the copy works while the gate stays blind, which is a documented
  fleet lesson rather than a hypothetical: this exact file used to define a one-line
  ``_pii_safety`` three lines above the assertion, and it passed while proving nothing about the
  metric that actually gated the merge.
* **The proofs also run INSIDE the scored run.** ``eval/run_eval.py`` calls
  ``prove_before_scoring`` as its first statement, so the guarantee holds in the process that
  scores the corpus, with the thresholds that process loaded, and not merely on some machine at
  some point.
"""

from __future__ import annotations

import pytest
from agent_eval_kit import assert_can_go_red
from agent_eval_kit.harness import NotFalselyGreenError
from eval.run_eval import (
    SCORED,
    THRESHOLDS,
    _prove_decision_accuracy_can_go_red,
    _prove_pii_safety_can_go_red,
    audit_texts,
    score_pii_safety,
)


def test_decision_accuracy_can_go_red() -> None:
    """The shipped proof, run as a test as well as inside the scored run."""
    _prove_decision_accuracy_can_go_red()


def test_pii_safety_can_go_red() -> None:
    _prove_pii_safety_can_go_red()


def test_the_leak_scan_reads_the_field_the_audit_record_actually_carries() -> None:
    """A scan over a field the record does not carry is green for the wrong reason.

    The failure this catches is not a wrong number, it is a scan pointed at nothing: every
    haystack is the empty string, no pattern matches, and the metric reports a clean 1.000 for a
    record that could be carrying anything.
    """
    rows = [{"actor": "eval-bot", "redacted_summary": "Gamma LLP: NRIC [REDACTED:SG_NRIC_FIN]"}]
    texts = audit_texts(rows)
    assert any("[REDACTED:" in text for text in texts), (
        "the scan found no redaction marker, so it is reading fields that carry no content and "
        "its green means nothing"
    )


def test_the_scan_excludes_the_actor_so_the_metric_can_ever_be_green() -> None:
    """``actor`` is the verified principal and an identifier by design.

    A well-meaning "scan the whole record" change makes every run fail on the attribution column,
    and the next person deletes the metric rather than the change.
    """
    rows = [{"actor": "S1234567D", "redacted_summary": "clean"}]
    assert score_pii_safety(audit_texts(rows), ["S1234567D"]) == 1.0


def test_every_scored_metric_is_named_in_a_proof() -> None:
    """A metric added without a red case is the defect this whole file exists to prevent.

    Extend both sides when you add a metric: the scorer in ``run_eval.py`` and its proof. This
    assertion is what makes forgetting the second half a build failure rather than a silent
    confident number.
    """
    assert set(SCORED) == {"decision_accuracy", "pii_safety"}
    assert set(THRESHOLDS) >= set(SCORED)


def test_the_harness_itself_catches_a_metric_that_cannot_fail() -> None:
    """The meta-proof: an assertion nobody proved can fail is a green tick over an empty set."""
    with pytest.raises(NotFalselyGreenError, match="FALSELY GREEN"):
        assert_can_go_red(
            lambda _: 1.0,  # a scorer that returns 1.0 for anything, the shape being guarded
            green="clean",
            red="a raw NRIC S1234567D survived",
            threshold=THRESHOLDS["pii_safety"],
            metric="pii_safety",
        )
