#!/usr/bin/env python3
"""Record the managed model's replies ONCE, by hand, so the eval can replay them offline.

**Scaffold.** {{ cookiecutter.friendly_name }} binds no generation port yet,
so this script refuses with an explanation rather than pretending to record. Everything that
makes a recording safe to commit is already wired: fill in the capture loop and delete the
refusal.

This is an authoring step, never a gate step. It requires the managed profile and real
credentials, it makes real calls, and it writes the file ``eval/replay_generation.py`` replays.
Run it, read the diff, commit the result:

    {{ cookiecutter.env_prefix }}_PROFILE=gcp python scripts/record_model_fixtures.py

Why a recording rather than a live call in the eval: the gate must pass with no network, no
credentials and no cloud SDK. Why a recording rather than nothing: without one, every grounding
and citation metric scores the offline deterministic core, which structurally cannot invent a
figure, so those metrics measure the validator rather than a model's restraint.

**Nothing is written unless the whole batch is clean.** ``write_recordings`` scans every reply
with the same pattern set the runtime redactor uses, for each case's planted identifier, and for
length. One hit aborts the entire write rather than dropping the offending row: a fixture that
silently lost a case would be a corpus nobody could reason about, and a partial write is how a
scrubbed file ends up half scrubbed.

Cost is a handful of managed-model calls per re-record, and a re-record is needed only when the
prompt or the corpus changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_eval_kit import Recorded, load_jsonl, recording_key, write_recordings
from pii_kit import pack_leak

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "eval"))
sys.path.insert(0, str(_REPO_ROOT / "src"))

import replay_generation  # noqa: E402

from {{ cookiecutter.package_name }}.config import Settings  # noqa: E402
from {{ cookiecutter.package_name }}.domain.pii import PII_PATTERNS  # noqa: E402

GOLDEN = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"


def main(argv: list[str] | None = None) -> int:
    settings = Settings.load()
    if settings.profile != "gcp":
        print(
            f"refused: recording needs the managed profile (got {settings.profile!r}). "
            "This step makes real model calls; the eval that replays them does not.",
            file=sys.stderr,
        )
        return 2

    cases = load_jsonl(GOLDEN, required=("id", "subject", "text"))
    planted = [str(case["planted"]) for case in cases if case.get("planted")]
    # The model the recording is attributed TO. Point this at whatever your Settings calls the
    # generation model once one is bound; the recording is keyed on it, so a model swap correctly
    # invalidates the old recording rather than inheriting it.
    model = getattr(getattr(settings, "models", None), "reasoning", "")

    captured: list[Recorded] = []
    for case in cases:
        # SCAFFOLD: build the prompt exactly as the product builds it, call the REAL generation
        # adapter, and append a Recorded(...) row. Keying on the model, the prompt and what the
        # model was given is what makes a recording replayable: all three change the answer, so
        # keying on the prompt alone would replay one case's reply for another case's evidence.
        _ = recording_key(model, "the prompt the product builds", [str(case["id"])])

    if not captured:
        print(
            "refused: this repository binds no generation port yet, so there is nothing to "
            "record. Bind one, fill in the capture loop above, delete this refusal, and see "
            "eval/replay_generation.py for the replay side.",
            file=sys.stderr,
        )
        return 1

    written = write_recordings(
        replay_generation.FIXTURE,
        captured,
        leaks=lambda text: bool(pack_leak(text, PII_PATTERNS)),
        planted=planted,
    )
    print(f"wrote {written} recordings to {replay_generation.FIXTURE}")
    print("Review the diff before committing: this file is model output, not authored fixture.")
    return 0


if __name__ == "__main__":  # pragma: no cover - an authoring step, never a gate step
    raise SystemExit(main(sys.argv[1:]))
