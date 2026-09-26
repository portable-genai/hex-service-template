"""The deterministic triage service: pure decision, redact-before-audit, soft escalation.

The consequential decision (the severity band and whether to escalate) is pure stdlib and
replayable; an LLM would only narrate, never produce the band. PII is redacted BEFORE anything
is written to the audit sink (R2/P-04), every result carries a citation, and a consequential
result escalates softly to a human (P-06) rather than auto-executing.

Rule R1: the guardrail screens BOTH directions of the one generation call this service makes,
the narrated ``summary`` (a fork that replaces the deterministic string below with a real model
call inherits this screening unchanged, because it wraps the STEP, not the string): the case
text is screened INPUT before it is scored or narrated at all, and the narrated summary is
screened OUTPUT before it is audited or returned. A blocked direction is audited
``Decision.BLOCKED`` and raises :class:`~.errors.GuardrailBlockedError`, never a partial result.
"""

from __future__ import annotations

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.guardrail import GuardrailPort
from ..ports.observability import ObservabilityTracerPort
from .errors import GuardrailBlockedError
from .kernel import AuditEvent, Citation, Decision, Direction, GuardrailVerdict, Severity, utcnow
from .models import TriageInput, TriageResult
from .pii import PII_PATTERNS

# Deterministic keyword bands (the vertical IP; swap for your policy). Ordered most severe first.
_SEVERITY_KEYWORDS: tuple[tuple[Severity, frozenset[str]], ...] = (
    (Severity.CRITICAL, frozenset({"sanction", "terrorism", "fraud"})),
    (Severity.HIGH, frozenset({"breach", "leak", "urgent", "weapon"})),
    (Severity.MEDIUM, frozenset({"complaint", "dispute", "delay"})),
)


#: Span name for one triage. A module constant so the traced name is greppable and stable.
_TRIAGE_SPAN = "triage.assess"


class TriageService:
    """Score a case into a severity band and record an already-redacted audit event."""

    def __init__(
        self,
        audit: AuditSinkPort,
        tracer: ObservabilityTracerPort,
        guardrail: GuardrailPort,
    ) -> None:
        self._audit = audit
        self._tracer = tracer
        self._guardrail = guardrail

    def triage(self, case: TriageInput, *, actor: str) -> TriageResult:
        # The span wraps the whole unit of work, and carries STRUCTURAL attributes only: the
        # action and the actor, never the case text. A span is not a redacted sink (P-04).
        with self._tracer.span(_TRIAGE_SPAN, action="triage", actor=actor):
            return self._triage(case, actor=actor)

    def _triage(self, case: TriageInput, *, actor: str) -> TriageResult:
        # 1) Guardrail screen (INPUT), before the case is scored or narrated at all (rule R1).
        in_verdict: GuardrailVerdict = self._guardrail.screen(case.text, Direction.INPUT)
        if not in_verdict.allowed:
            self._audit_blocked(actor, case.subject, Severity.LOW, in_verdict)
            raise GuardrailBlockedError(in_verdict.reason or "triage input blocked by guardrail")

        severity = self._severity(case.text)
        escalate = severity in (Severity.HIGH, Severity.CRITICAL)
        decision = Decision.ESCALATED if escalate else Decision.ALLOWED
        summary = f"{case.subject}: triaged {severity.value}"

        # 2) Guardrail screen (OUTPUT) on the narrated summary, before it is audited or returned.
        # This is the step a real generation call replaces `summary` above at: the screen stays
        # in exactly this place regardless of what produces the text.
        out_verdict: GuardrailVerdict = self._guardrail.screen(summary, Direction.OUTPUT)
        if not out_verdict.allowed:
            self._audit_blocked(actor, case.subject, severity, out_verdict)
            raise GuardrailBlockedError(out_verdict.reason or "triage output blocked by guardrail")
        summary = out_verdict.sanitized_text or summary

        citation = Citation(
            source_id=f"case:{case.subject}",
            title="Case description",
            snippet=case.text[:80],
        )

        # Redact BEFORE the audit write: the raw identifiers never reach the WORM record.
        self._audit.record(
            AuditEvent(
                action="triage",
                actor=actor,
                decision=decision,
                severity=severity,
                redacted_summary=redact(f"{summary} :: {case.text}", PII_PATTERNS),
                citations=(citation,),
                timestamp=utcnow(),
            )
        )

        return TriageResult(
            subject=case.subject,
            severity=severity,
            decision=decision,
            summary=summary,
            requires_human_review=escalate,
            citations=(citation,),
        )

    def _audit_blocked(
        self, actor: str, subject: str, severity: Severity, verdict: GuardrailVerdict
    ) -> None:
        """Audit a guardrail block BEFORE the raise reaches the caller (rule R1/R2).

        Never carries the blocked text: only that a block happened, in which direction, and
        why. A blocked attempt is a security-relevant event the WORM trail must hold even
        though the request as a whole never produced a triage.
        """
        self._audit.record(
            AuditEvent(
                action="triage",
                actor=actor,
                decision=Decision.BLOCKED,
                severity=severity,
                redacted_summary=redact(
                    f"{subject}: blocked ({verdict.direction.value}): "
                    f"{verdict.reason or 'guardrail block'}",
                    PII_PATTERNS,
                ),
                citations=(),
                timestamp=utcnow(),
            )
        )

    @staticmethod
    def _severity(text: str) -> Severity:
        lowered = text.lower()
        for severity, keywords in _SEVERITY_KEYWORDS:
            if any(word in lowered for word in keywords):
                return severity
        return Severity.LOW
