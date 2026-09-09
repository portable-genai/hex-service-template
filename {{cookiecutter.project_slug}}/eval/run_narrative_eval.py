#!/usr/bin/env python3
"""The half a rule cannot score: is the generated narrative any good, judged, against a floor.

Everything in ``run_eval.py`` is deterministic and binary. Was the severity right. Did anything
personal survive. Those are questions code can answer, and code answers them there.

They leave a gap that is exactly the model's own contribution. A triage narrative can be
correctly severity-banded, correctly redacted, and still omit the fact the reviewer needed,
cite nothing, or assert a certainty nobody has. Deciding that is a judgement, so it is judged,
and the judge is held to the same standard as every other scorer here: it must be shown able to
fail before anything it certifies is believed.

The whole run is ``agent_eval_kit.narrative_main``. This file supplies only what is specific to
this service: where its table is, where its floors are, the profiles each case is written in,
and which of them is the deliberate control.

    make eval-narrative                       # offline, no model, no credentials, no network
    python eval/run_narrative_eval.py \
        --judge local-model \
        --judge-base-url http://127.0.0.1:8001/v1 \
        --judge-model your/local-model        # opt in, outside CI

The judge is chosen HERE, on the command line, and never from the environment: a gate whose
scorer a stray variable could swap is not a gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_eval_kit import narrative_main

_REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = _REPO_ROOT / "eval" / "datasets" / "narrative_golden.jsonl"
FLOORS = _REPO_ROOT / "config" / "quality-floors.toml"

#: The ways each case is written. They are PROFILES rather than adjectives: they say which
#: deployment produced the narrative, which is what a portability claim is about.
PROFILES = ("managed", "reduced", "regressed")

#: The control. It exists to be below the floor, so a table where it passes is a table whose
#: floor is too low to refuse anything.
CONTROL = "regressed"


if __name__ == "__main__":
    raise SystemExit(
        narrative_main(
            dataset=DATASET,
            floors=FLOORS,
            profiles=PROFILES,
            control=CONTROL,
            description=(
                "Narrative quality for {{ cookiecutter.friendly_name }}, "
                "judged against the model-risk floors in config/quality-floors.toml."
            ),
            argv=sys.argv[1:],
        )
    )
