#!/usr/bin/env python3
"""Regenerate the derived half of ``docs/evals.md`` from the rubrics, golden set and floors.

A page that lists metrics and thresholds by hand goes stale the first time a bar moves, and
nothing notices. So the derivation is a command, and ``--check`` makes staleness a build failure
rather than something a reader discovers:

    make evals-doc          # rewrite the generated sections
    make evals-doc-check    # non-zero when the page and the artifacts disagree (runs in the gate)

Only the sections named in :data:`BLOCKS` are generated. Everything else on the page is
hand-written prose addressed to a reviewer, and this script does not touch it: the point is a
document a person wrote, whose FACTS cannot drift from the artifacts they describe.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_eval_kit import load_jsonl, load_rubrics, render_main, required_positives
from agent_eval_kit.floors import load_quality_floors
from agent_eval_kit.rubrics import Rubric

_REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = _REPO_ROOT / "docs" / "evals.md"
RUBRICS = _REPO_ROOT / "eval" / "rubrics"
GOLDEN = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"
NARRATIVE = _REPO_ROOT / "eval" / "datasets" / "narrative_golden.jsonl"
FLOORS = _REPO_ROOT / "config" / "quality-floors.toml"

#: The headings this script owns. Each runs from its heading to the next `\n## `.
BLOCKS = (
    "## What is measured, and against what bar",
    "## What is exercised",
    "## Where the quality bars come from",
)


def _is_all_or_nothing(rubric: Rubric) -> bool:
    """Whether a rubric declares its metric 1.0-or-0.0 for the whole run.

    Read from the rubric rather than inferred from the threshold, because 0.99 is both the bar a
    leak metric carries (one leak anywhere fails it) and a perfectly ordinary rate. Guessing from
    the number would print "needs 100 cases" beside a metric that a corpus of one already gates
    correctly, which is a confident wrong answer rather than a missing one.
    """
    import yaml

    document = yaml.safe_load(Path(rubric.source).read_text(encoding="utf-8"))
    return str(((document or {}).get("denominator") or {}).get("kind", "rate")) == "all-or-nothing"


def _metrics_block() -> list[str]:
    rubrics = load_rubrics(RUBRICS)
    cases = load_jsonl(GOLDEN)
    lines = [
        BLOCKS[0],
        "",
        "Every bar below lives in `eval/rubrics/*.yaml` next to the argument for it, and the",
        "runner reads it from there. A metric with no reviewed bar, and a bar nothing measures,",
        "both fail the build.",
        "",
        "The third column is the denominator rule, and it applies only to a metric whose score",
        "is a FRACTION over scored cases: such a threshold `t` tolerates a single miss only over",
        "at least `1/(1-t)` cases, and below that the bar is arithmetically identical to 1.0",
        "while reading as though it had headroom. A metric that is 1.0-or-0.0 for the whole run",
        "is marked `all or nothing`: it already refuses a single failure, so a bigger corpus",
        "changes nothing about what its bar means. Each rubric declares which it is, in",
        "`denominator.kind`, rather than the rule being guessed from the number.",
        "",
        "| Metric | Bar | Needs at least | Corpus has | What it measures |",
        "|---|---|---|---|---|",
    ]
    for rubric in rubrics:
        if _is_all_or_nothing(rubric):
            needs = "all or nothing"
        else:
            needs = f"{required_positives(rubric.threshold)} cases"
        lines.append(
            f"| `{rubric.metric}` | {rubric.threshold:g} | {needs} | {len(cases)} | "
            f"{rubric.description} |"
        )
    lines.append("")
    return lines


def _exercised_block() -> list[str]:
    cases = load_jsonl(GOLDEN)
    planted = [case for case in cases if case.get("planted")]
    narrative = load_jsonl(NARRATIVE) if NARRATIVE.exists() else []
    lines = [
        BLOCKS[1],
        "",
        f"- **{len(cases)} golden triage cases** in `eval/datasets/golden_cases.jsonl`, each",
        "  carrying the severity a reviewer assigned by reading it. The expectation is the",
        "  dataset's, never the service's own verdict: a metric that compared the engine with",
        "  itself would be a tautology with a threshold.",
        f"- **{len(planted)} of them plant a raw identifier**, so the leak metric has a target it",
        "  could miss. A corpus that plants nothing scores a vacuous 1.0, and the runner refuses",
        "  one for that reason.",
    ]
    if narrative:
        lines.append(
            f"- **{len(narrative)} judged narrative cases** in "
            "`eval/datasets/narrative_golden.jsonl`, each written once per profile with the band"
        )
        lines.append(
            "  it is expected to land in. A profile that quietly got BETTER fails too, because a"
        )
        lines.append("  band nobody predicted is a change nobody reviewed.")
    lines.append("")
    return lines


def _floors_block() -> list[str]:
    floors = load_quality_floors(FLOORS)
    lines = [
        BLOCKS[2],
        "",
        "`config/quality-floors.toml` is owned by model risk. A **floor** refuses: below it a",
        "profile must not serve that vertical, which is not the same as serving it worse. A",
        "**target** is full quality. Between the two is DEGRADED, the band a portability claim",
        "describes in adjectives and which nothing measures until a floor exists.",
        "",
        "| Vertical | Floor | Target | Why |",
        "|---|---|---|---|",
    ]
    for floor in floors:
        bars = f"{floor.floor:g} | {floor.target:g}"
        lines.append(f"| `{floor.vertical}` | {bars} | {floor.note} |")
    lines.append("")
    return lines


def render() -> str:
    """The page, with the generated blocks replaced and the hand-written prose untouched."""
    text = DOC.read_text(encoding="utf-8")
    generated = {
        BLOCKS[0]: _metrics_block(),
        BLOCKS[1]: _exercised_block(),
        BLOCKS[2]: _floors_block(),
    }
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if line in generated:
            out.extend(generated[line])
            skipping = True
            continue
        if skipping:
            if line.startswith("## "):
                skipping = False
            else:
                continue
        out.append(line)
    missing = [heading for heading in BLOCKS if heading not in text]
    if missing:
        raise SystemExit(
            f"{DOC}: missing generated section(s) {missing}. This script replaces named "
            "headings; it does not invent them, because a page it could create from nothing "
            "would silently replace one a person wrote."
        )
    return "\n".join(out).rstrip("\n") + "\n"


if __name__ == "__main__":
    raise SystemExit(
        render_main(
            output=DOC,
            render=render,
            description="Regenerate docs/evals.md from the rubrics, golden set and floors.",
            argv=sys.argv[1:],
        )
    )
