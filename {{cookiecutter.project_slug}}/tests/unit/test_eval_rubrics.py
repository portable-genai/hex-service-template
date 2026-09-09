"""Every gated metric has a reviewed bar, and every reviewed bar gates a metric.

Both directions, because they fail differently and only one of them is obvious. A metric scored
with no rubric got its threshold from a number somebody typed at a call site. A rubric for a
metric nothing scores is worse: it reads as governance, it satisfies a reviewer looking for
evidence that the bars are owned, and it gates nothing at all. That is the direction that rots
without anybody noticing, because it rots toward looking well governed.
"""

from __future__ import annotations

import pytest
from agent_eval_kit import load_rubrics
from agent_eval_kit.rubrics import RubricError
from eval.run_eval import RUBRICS, SCORED, THRESHOLDS


def test_the_rubrics_and_the_scored_metrics_agree_in_both_directions() -> None:
    load_rubrics(RUBRICS).assert_covers(SCORED)


def test_the_thresholds_the_runner_uses_come_from_the_rubrics() -> None:
    """There is deliberately no fallback dict: a fallback is a second home for one number."""
    assert load_rubrics(RUBRICS).thresholds() == THRESHOLDS


def test_a_metric_with_no_reviewed_bar_fails_the_build() -> None:
    with pytest.raises(RubricError, match="invented at the call site"):
        load_rubrics(RUBRICS).assert_covers([*SCORED, "a_metric_nobody_wrote_a_rubric_for"])


def test_a_bar_that_names_no_metric_fails_the_build_too() -> None:
    with pytest.raises(RubricError, match="reads as governance"):
        load_rubrics(RUBRICS).assert_covers(["decision_accuracy"])


def test_the_safety_metric_carries_the_strictest_bar() -> None:
    """Practice E2. A leak gate set loosely is the one bar that must never be relaxed in a fork."""
    assert THRESHOLDS["pii_safety"] >= 0.99


def test_every_rubric_carries_its_own_reasoning() -> None:
    """A bar with no argument beside it is a module constant that moved house."""
    for rubric in load_rubrics(RUBRICS):
        assert rubric.description.strip(), f"{rubric.metric}: the rubric explains nothing"


def test_the_corpus_can_express_every_bar_it_is_measured_against() -> None:
    """The denominator rule, checked here as well as inside the scored run.

    Here it catches a bar somebody raised; there it catches a corpus somebody shrank. Both are
    the same mistake seen from opposite ends, and either one turns a labelled rate back into a
    silent 1.0.
    """
    from agent_eval_kit import assert_denominator_supports, load_jsonl
    from eval.run_eval import DEFAULT_DATASET

    cases = load_jsonl(DEFAULT_DATASET)
    assert_denominator_supports(
        THRESHOLDS["decision_accuracy"], len(cases), metric="decision_accuracy"
    )
