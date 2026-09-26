"""GuardrailPort: the boundary that screens a generation call in both directions (rule R1).

Rule R1 is the reason this port exists: a service that binds ``agent-guardrail-gateway`` as a
mandatory dependency must screen every inbound prompt BEFORE it reaches a model or the domain's
own narration, and every outbound answer AFTER it is produced and BEFORE it is audited or
returned. ``domain/triage_service.py`` calls :meth:`GuardrailPort.screen` around its narration
step in exactly that shape, so a fork that replaces the deterministic summary with a real
generation call inherits the screening already in place rather than having to remember to add it.

The domain stays pure. This port names the screen; the adapters (not this module) depend on the
managed guardrail service (Model Armor) or a local heuristic stand-in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.kernel import Direction, GuardrailVerdict


@runtime_checkable
class GuardrailPort(Protocol):
    def screen(self, text: str, direction: Direction) -> GuardrailVerdict:
        """Screen inbound prompt or outbound response text; may sanitise it in place.

        Never raises on a policy match: a block is reported as ``GuardrailVerdict(allowed=False,
        ...)`` so the caller can audit the attempt before deciding how to fail. Raising is
        reserved for the adapter being unable to reach its backend at all (the managed family
        with no template configured, or the on-prem placeholder).
        """
        ...
