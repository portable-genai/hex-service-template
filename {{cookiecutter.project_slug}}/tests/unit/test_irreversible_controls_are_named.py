"""An irreversible control never arrives by default.

The audit bucket's lock is the one control in ``infra/terraform/`` that cannot be undone. A
locked Cloud Logging bucket refuses to be deleted, and refuses to have its retention window
shortened, for the whole retention period: not with project-owner rights, not with
``terraform destroy``, not at all. Every other knob in that directory can be applied and then
applied back.

So ``worm_locked`` has NO DEFAULT and a plan refuses until this deployment states it. An unset
value may take a reviewed default; it may never take an irreversible one. This is not a
hypothetical in this fleet: a sibling stack shipped ``default = true``, its deployment file named
neither the lock nor the retention, and its first apply locked an audit bucket until roughly 2033.
Nor is the answer ``default = false``, which would let a fork running this as a system of record
lose the WORM guarantee just as silently. There is no safe default, which is why there is none.

The retention floor is the other half. It binds only when the lock is on, so declining the lock is
a supported posture rather than a weakened one: an unlocked bucket is destroyable and its
retention policy is removable by a project owner anyway, so it evidences routing and coverage
rather than immutability. Turning the lock on re-imposes the floor at plan time.

Observed failing first, in ``scripts/verify-render.sh``: against the template as it shipped, the
no-default test failed on ``default = true`` and the conditional-floor test failed on the
unconditional ``>= 180``. Putting either back turns its test red again, which is the regression
each one exists to stop.

The plan-level half of the same claim is ``infra/terraform/production_edge.tftest.hcl``, which
runs ``terraform test`` with mock providers and proves the floor refuses 179 days on a LOCKED
stack while an unlocked stack may keep 3. This file is the half that needs no terraform binary,
so ``make gate`` holds it too.
"""

from __future__ import annotations

import re

from tests import REPO_ROOT

TF = REPO_ROOT / "infra" / "terraform"

#: ``variable "x" {`` with no literal brace pair, because this module is rendered by cookiecutter
#: and a doubled brace would be a Jinja opener rather than text.
_OPEN = "{"
_CLOSE = "}"


def _variable_block(name: str) -> str:
    """Return the full HCL text of one ``variable`` block, braces balanced."""
    text = (TF / "variables.tf").read_text(encoding="utf-8")
    start = text.find('variable "' + name + '" ' + _OPEN)
    assert start != -1, f"variables.tf declares no {name!r}"
    depth = 0
    for index in range(start, len(text)):
        if text[index] == _OPEN:
            depth += 1
        elif text[index] == _CLOSE:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated variable block {name!r}")


def test_the_audit_bucket_lock_is_a_variable_not_a_literal() -> None:
    worm = (TF / "logging_worm.tf").read_text(encoding="utf-8")
    assert re.search(r"^\s*locked\s*=\s*var\.worm_locked\s*$", worm, re.MULTILINE)
    assert not re.search(r"^\s*locked\s*=\s*(true|false)\s*$", worm, re.MULTILINE), (
        "a literal lock takes the irreversible decision for every deployment of this repo, and "
        "the only way to decline it is a source edit no deployment configuration records"
    )
    assert re.search(r"^\s*retention_days\s*=\s*var\.retention_days\b", worm, re.MULTILINE)


def test_the_lock_is_named_worm_locked_and_nothing_else() -> None:
    variables = (TF / "variables.tf").read_text(encoding="utf-8")
    assert 'variable "worm_locked"' in variables
    assert "lock_worm_bucket" not in variables, (
        "the fleet has ONE name for this control, worm_locked, so a deployment tfvars written "
        "for one stack states the lock in every stack"
    )


def test_the_lock_has_no_default_so_every_plan_names_it() -> None:
    block = _variable_block("worm_locked")
    assert not re.search(r"^\s*default\s*=", block, re.MULTILINE), (
        "worm_locked must have no default: an irreversible control must never be taken because "
        "a deployment said nothing, and a fork must never lose it the same way"
    )


def test_the_retention_floor_binds_only_when_locked() -> None:
    block = _variable_block("retention_days")
    assert re.search(r"^\s*default\s*=\s*180\b", block, re.MULTILINE)
    condition = re.search(r"^\s*condition\s*=\s*(.+)$", block, re.MULTILINE)
    assert condition is not None, (
        "retention_days carries no validation, so a locked bucket could be created with a short "
        "window"
    )
    assert re.fullmatch(
        r"var\.worm_locked\s*\?\s*var\.retention_days\s*>=\s*180\s*:\s*var\.retention_days\s*>=\s*1",
        condition.group(1).strip(),
    ), condition.group(1)


def test_the_example_shows_the_locked_production_form() -> None:
    example = (TF / "terraform.tfvars.example").read_text(encoding="utf-8")
    assert re.search(r"^worm_locked\s*=\s*true\s*$", example, re.MULTILINE), (
        "the example is what a first apply is copied from, so it shows the compliant production "
        "posture rather than leaving the one value with no default unstated"
    )
    assert re.search(r"^retention_days\s*=\s*180\s*$", example, re.MULTILINE)


def test_every_terraform_run_states_the_lock() -> None:
    """A missing required variable would fail every run, so the test file states it once."""
    suite = (TF / "production_edge.tftest.hcl").read_text(encoding="utf-8")
    assert re.search(r"^\s*worm_locked\s*=\s*true\s*$", suite, re.MULTILINE)
    assert re.search(r"^\s*worm_locked\s*=\s*false\s*$", suite, re.MULTILINE), (
        "the unlocked posture is a supported one, so the plan-level suite exercises it rather "
        "than proving only the form it ships"
    )
