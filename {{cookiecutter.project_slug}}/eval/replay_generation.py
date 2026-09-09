"""Score the rubrics against a REAL model's words, offline, by replaying recorded output.

**Scaffold.** {{ cookiecutter.friendly_name }} triages deterministically and binds
no generation port yet, so nothing here is wired into ``run_eval.py``. It is placed at
generation time rather than left to be invented later, because the moment a repo binds a model
is exactly the moment its existing metrics quietly stop meaning what their names say.

Read this before you bind one. Every offline metric in a fresh repo scores a deterministic core.
The moment a model is in the path, metrics called ``groundedness`` or ``citation_accuracy``
become measurements of the VALIDATOR rather than of the model's restraint: they stay green
through a model swap, a prompt regression, a temperature change or a context-window truncation,
because no model is in the measured path at all.

The fix cannot be "call the model in the gate": the gate must pass with no network, no
credentials and no cloud SDK, and that property is not for trading. So a real call is made ONCE,
by hand, by ``scripts/record_model_fixtures.py``, its output is scrubbed and committed, and this
adapter replays it. The same rubrics and the same hand-written labels then score real model text
with nothing reachable.

To use it:

1. bind a generation port in ``ports/`` and a real adapter under ``adapters/gcp/``;
2. give this class the method your port declares, delegating to :meth:`replay`;
3. bind THIS class in the eval only, never in the container. Nothing a deployment binds should
   be able to serve pre-recorded answers to a customer, which is why this file lives under
   ``eval/`` rather than under ``src/``;
4. record once with ``make record-fixtures`` and commit the result;
5. call ``ReplayGenerationAdapter.reset_misses()`` before the replay run and
   ``ReplayGenerationAdapter.assert_no_misses()`` after it.

Step 5 is not optional bookkeeping. A well-built kernel treats ANY generation failure as
silence, deliberately: for the product, a model outage must degrade to "no answer", never to an
unvalidated fallback. That product property swallows this adapter's raise, and silence is
scoreable, so a stale recording would grade as a model that declined everything and would PASS
wherever silence was the expected answer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_eval_kit import ReplayAdapter

FIXTURE = Path(__file__).resolve().parent / "datasets" / "model_replay.jsonl"


class ReplayGenerationAdapter(ReplayAdapter):
    """Satisfies a generation port by replaying a recorded managed-model response.

    Fails closed in the one way that matters: a prompt with no recording RAISES, naming the case.
    It never falls back to a local drafter and it never reaches the network, because a replay
    that quietly substituted a different drafter would report a score for a model that produced
    none of it.
    """

    def __init__(self, model: str, fixture: Path = FIXTURE) -> None:
        super().__init__(model, fixture)

    def draft(self, prompt: str, inputs: Sequence[str] = ()) -> Mapping[str, Any] | None:
        """Rename this to whatever your generation port declares, and keep the delegation."""
        return self.replay(prompt, inputs)
