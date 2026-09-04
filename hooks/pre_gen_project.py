"""Refuse to render a name the template has never proved it can render green.

Every rendered line that contains ``package_name``, ``project_slug`` or ``env_prefix`` gets
longer when the name does. The rendered gate's FIRST step is ``make lint``, which enforces a
100 character line length, so past some name length a zero-edit render is red on arrival. That
is not hypothetical: a render with a 41 character ``package_name`` failed ``ruff check`` with
five errors and ``ruff format --check`` with one file, and the failure reached this template's
consumers as "the scaffold is broken".

The fix has two halves and this file is the second one. The first half is that the emitted
source is now written to survive a long name (long dotted targets come from short module-level
constants, first-party imports carry a magic trailing comma so their layout does not change
with the name, and no docstring line puts a long fixed suffix after a rendered name). The
second half is a BOUND: the source survives long names up to a stated limit, ``verify-render``
renders exactly at that limit and runs the whole gate there, and this hook refuses anything
past it. Without the bound, "any valid name renders green" is a claim nobody can test, because
a 300 character package name breaks any import line ever written.

Keep :data:`MAX_LENGTHS` and the ``max`` row of ``scripts/verify-render.sh`` in step. The
rendered ``tests/unit/test_repo_artifacts.py`` has no view of this file, so the render matrix
is the only thing holding them together.
"""

from __future__ import annotations

import keyword
import re
import sys

#: Longest value the template is PROVEN to render green for, per variable. Each limit is the
#: one the `max` row of scripts/verify-render.sh renders at, so raising a number here without
#: raising it there turns a proof into a guess.
#:
#: * project_slug 63: the DNS label / Cloud Run service name limit, which the rendered agent
#:   card URL and the Terraform state prefix both inherit. Lint has far more headroom.
#: * package_name 48: the binding constraint is the longest first-party import the rendered
#:   tree contains, ``from <pkg>.adapters.onprem.review_router import (`` at 5 + 48 + 30 + 9 =
#:   92 columns, which leaves 8 columns for a deeper module added later.
#: * env_prefix 32: the binding constraint is prose that names ``<PREFIX>_AUDIT_ANCHOR`` and
#:   friends inside a docstring or a Makefile comment.
#: * friendly_name 48: it is a module docstring's whole summary line
#:   (``"""FastAPI application for <NAME>.``), which is the tightest line in the tree. The
#:   repository name used to share it as a parenthetical id; a file no longer restates the
#:   repository it lives in, so the line carries one value.
#: * region 24: longer than any current GCP region id, and it shares a line with nothing.
#: * description 96: it is the whole of ``src/<package>/__init__.py``'s second paragraph line.
MAX_LENGTHS = {
    "project_slug": 63,
    "package_name": 48,
    "env_prefix": 32,
    "friendly_name": 48,
    "region": 24,
    "description": 96,
}

#: Shape each variable must have, and the reason in words a reader can act on.
PATTERNS = {
    "project_slug": (
        re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"),
        "lower-case letters, digits and single hyphens, starting with a letter "
        "(it is a repository name, a DNS label and a container service name)",
    ),
    "package_name": (
        re.compile(r"^[a-z][a-z0-9_]*$"),
        "a lower-case Python identifier: letters, digits and underscores, starting "
        "with a letter",
    ),
    "env_prefix": (
        re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$"),
        "upper-case letters, digits and single underscores, starting with a letter "
        "(it is prefixed to environment variable names such as <PREFIX>_PROFILE)",
    ),
    "region": (
        re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"),
        "a cloud region id such as asia-southeast1",
    ),
}

VALUES = {
    "project_slug": "{{ cookiecutter.project_slug }}",
    "package_name": "{{ cookiecutter.package_name }}",
    "env_prefix": "{{ cookiecutter.env_prefix }}",
    "friendly_name": "{{ cookiecutter.friendly_name }}",
    "region": "{{ cookiecutter.region }}",
    "description": "{{ cookiecutter.description }}",
}


def problems() -> list[str]:
    found: list[str] = []
    for name, value in VALUES.items():
        if not value:
            found.append(name + " must not be empty")
            continue
        limit = MAX_LENGTHS.get(name)
        if limit is not None and len(value) > limit:
            found.append(
                "%s is %d characters; the template is proved green only up to %d. "
                "Shorten it, or raise the limit in hooks/pre_gen_project.py AND in the `max` "
                "row of scripts/verify-render.sh and re-run that gate." % (name, len(value), limit)
            )
        rule = PATTERNS.get(name)
        if rule is not None and not rule[0].match(value):
            found.append("%s must be %s; got %r" % (name, rule[1], value))
    package = VALUES["package_name"]
    if not package.isidentifier() or keyword.iskeyword(package):
        found.append("package_name must be a usable Python identifier; got %r" % package)
    return found


def main() -> None:
    found = problems()
    if not found:
        return
    sys.stderr.write("cookiecutter refused to render:\n")
    for line in found:
        sys.stderr.write("  - " + line + "\n")
    raise SystemExit(1)


main()
