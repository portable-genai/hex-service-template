#!/usr/bin/env bash
# Render the cookiecutter template ACROSS A MATRIX OF NAME LENGTHS and run the FULL offline gate
# on every render, installing the FOUR commons packages at the commits cookiecutter.json pins,
# cloned fresh (see "The commons" below). This is the template's own "gate": if it fails, the
# template does not start a repo at parity. `make gate` runs it, and so does the hosted CI job.
#
# WHY A MATRIX. Every rendered line that contains `package_name`, `project_slug` or `env_prefix`
# grows with the name. `make lint` is the FIRST step of both the rendered gate and the shared
# hard-gate workflow, and it enforces a 100 column line length. This script used to render ONE
# name set (the defaults, package_name `example_agent`, 13 characters) and declared the template
# green; a render with a 41 character package name was red on arrival, `ruff check` with five
# errors and `ruff format --check` with one file, with no hand edit anywhere. A single-row gate
# could not see it, and 34 repositories were waiting on this output.
#
# So the rows below are the claim. `short` and `max` bracket the range the template is proved
# for; `refuted` is the exact name set that was red before this was fixed, kept as a named
# regression; `default` is what `cookiecutter --no-input` produces. `max` renders at the limits
# in hooks/pre_gen_project.py, which REFUSES anything longer, so "any valid combination of names
# renders green" is a statement with a tested boundary rather than an untestable absolute.
#
# What this does NOT prove: that the committed lockfiles install. Each render's third-party
# packages are resolved fresh below rather than from its lock, and the rendered repo itself is
# installed with --no-deps. It does fetch every pinned commons COMMIT from GitHub, so a pin naming
# a commit GitHub does not have fails here. After changing a version variable or a lockfile, also
# render outside this workspace and run `make install` (which installs from requirements-dev.lock)
# before trusting the template.
#
# Usage:
#   scripts/verify-render.sh              # the whole matrix; this is the gate
#   scripts/verify-render.sh default      # one row by label, for a fast edit loop ONLY
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"       # the hex-service-template repo
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------------------- #
# The commons. A rendered repo installs the commits cookiecutter.json pins, because its lockfiles
# pin exactly those, so the gate installs the same code: each package cloned fresh from GitHub
# and checked out at its pinned commit. That makes the answer a property of THIS commit of the
# template, the same on a laptop and in the hosted CI job. It used to install whatever the
# sibling checkouts in the workspace held, which is not what any render ships, and which a CI
# runner does not have at all. A full clone keeps the tags and the history, which the rendered
# pin object-type check below needs.
#
# COMMONS_GIT_CHECKOUT_ROOT names a directory of existing checkouts instead, one per package name,
# installed AS THEY STAND: that is for co-developing a commons change with the template before
# either is released. It is the same variable the rendered object-type check searches, and a run
# that uses it says loudly that it is NOT the gate.
#
# Fields, `:` separated: the package, and the cookiecutter.json variable carrying its commit.
# ---------------------------------------------------------------------------------------- #
COMMONS=(
  "pii-kit:pii_kit_commit"
  "hex-service-kit:commons_commit"
  "agent-eval-kit:eval_kit_commit"
  "review-kit:review_kit_commit"
)
COMMONS_ROOT=""
COMMONS_PINNED=0

provide_commons() {
  local entry kit variable commit head
  if [ -n "${COMMONS_GIT_CHECKOUT_ROOT:-}" ]; then
    COMMONS_ROOT="$(cd "$COMMONS_GIT_CHECKOUT_ROOT" && pwd)"
    echo "== the commons: the checkouts under $COMMONS_ROOT, AS THEY STAND =="
    echo "   COMMONS_GIT_CHECKOUT_ROOT is set, so the pinned commits are NOT what gets installed."
    for entry in "${COMMONS[@]}"; do
      kit="${entry%%:*}"
      if ! git -C "$COMMONS_ROOT/$kit" rev-parse --git-dir >/dev/null 2>&1; then
        echo "   FAILED: $COMMONS_ROOT/$kit is not a git checkout" >&2
        exit 1
      fi
    done
  else
    COMMONS_ROOT="$WORK/commons"
    echo "== the commons: fresh clones, checked out at the commits cookiecutter.json pins =="
    for entry in "${COMMONS[@]}"; do
      kit="${entry%%:*}"
      variable="${entry#*:}"
      commit="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' \
        "$HERE/cookiecutter.json" "$variable")"
      git clone --quiet "https://github.com/portable-genai/$kit.git" "$COMMONS_ROOT/$kit"
      git -C "$COMMONS_ROOT/$kit" checkout --quiet --detach "$commit"
      head="$(git -C "$COMMONS_ROOT/$kit" rev-parse HEAD)"
      if [ "$head" != "$commit" ]; then
        echo "   FAILED: $kit checked out $head, not the pinned $commit ($variable)" >&2
        exit 1
      fi
      echo "   $kit at $commit ($variable)"
    done
    COMMONS_PINNED=1
  fi
  # The rendered object-type check reads the same variable, so it asks these object stores.
  export COMMONS_GIT_CHECKOUT_ROOT="$COMMONS_ROOT"
}

# ---------------------------------------------------------------------------------------- #
# The render matrix. Fields, `|` separated:
#   label | project_slug | package_name | env_prefix | friendly_name | region |
#   description
#
# EVERY rendered variable is here, not only the three that were caught failing, because the
# defect class is "a rendered value lengthens a line", and `friendly_name` owns
# the tightest line in the tree (a module docstring's summary) while `description` owns a whole
# line of its own in `src/<package>/__init__.py`.
#
# `max` must stay at the MAX_LENGTHS in hooks/pre_gen_project.py, and
# `assert_max_row_matches_the_hook` below fails this gate if it drifts in either direction.
# Raising a limit there without lengthening this row turns a proof into a guess.
# ---------------------------------------------------------------------------------------- #
MATRIX=(
  "short|svc-a|a|A|A|a|D"
  "default|svc-example-agent|example_agent|EXAMPLE|Example Triage Agent|asia-southeast1|A grounded, audited triage agent scaffolded at cdd-sow-research parity from the catalog commons."
  "refuted|svc-bravo-considerably-longer-named-gate-agent|bravo_considerably_longer_named_gate_agent|BRAVOCONSIDERABLYLONGERPREFIX|Bravo Longer Named Gate Agent|asia-southeast1|The exact name set that rendered red before the matrix existed."
  "max|svc-maximum-length-boundary-probe-agent-for-the-render-gate-xyz|maximum_length_boundary_probe_agent_for_the_gate|MAXIMUMLENGTHBOUNDARYPROBEENVXYZ|Maximum Length Boundary Probe Rendering Agent XY|asia-southeast1-probe-xy|A grounded, audited agent scaffolded at cdd-sow-research parity from catalog commons, at length."
)

WANTED="${1:-}"

# A targeted `pytest` run inside this gate is only evidence if it RAN, PASSED, and skipped
# nothing. Three ways such a block reports green over nothing, and all three are closed here:
#
#   1. the module skipped (no google object store, no google-auth) and reported "1 skipped";
#   2. the selection collected nothing, because a module or a test was renamed;
#   3. SOME tests failed. `pytest ... || true` throws the exit code away, and a summary line
#      reading "3 failed, 19 passed" still CONTAINS " passed", so a substring test for it
#      accepts a failing run. That is the shape this gate exists to refuse, and it was in this
#      gate: a synthetic-summary control caught it before the block was trusted.
#
# $1 pytest's exit status, $2 its combined output, $3 what the block is called,
# $4 why a skip is not acceptable HERE.
assert_pytest_ran_and_passed() {
  local status="$1" output="$2" label="$3" why="$4"
  case "$output" in
    *skipped*|*"no tests ran"*)
      echo "   FAILED: $label SKIPPED where $why" >&2
      echo "$output" | tail -20 >&2
      return 1 ;;
  esac
  if [ "$status" -ne 0 ]; then
    echo "   FAILED: $label exited $status" >&2
    echo "$output" | tail -40 >&2
    return 1
  fi
  case "$output" in
    *" passed"*) return 0 ;;
    *)
      echo "   FAILED: $label reported no passing tests at all" >&2
      echo "$output" | tail -40 >&2
      return 1 ;;
  esac
}

# The controls for the function above, run BEFORE it is trusted on anything. A gate assertion
# nobody proved can fail is a tick over an empty set, which is the whole subject of this file.
assert_the_pytest_assertion_can_fail() {
  local case_label
  for case_label in "0|1 skipped, 1 warning in 0.01s" \
                    "0|no tests ran in 0.01s" \
                    "1|3 failed, 19 passed in 0.60s" \
                    "2|ERROR collecting tests/unit/x.py" \
                    "0|"; do
    if assert_pytest_ran_and_passed "${case_label%%|*}" "${case_label#*|}" \
         "control" "control" >/dev/null 2>&1; then
      echo "   FAILED: the pytest assertion ACCEPTED '${case_label#*|}'" >&2
      exit 1
    fi
  done
  if ! assert_pytest_ran_and_passed 0 "22 passed, 1 warning in 0.23s" "control" "control"; then
    echo "   FAILED: the pytest assertion rejected a clean pass" >&2
    exit 1
  fi
  echo "   the pytest assertion rejects skips, empty selections, failures and errors"
}

verify_one_render() {
  local label="$1" slug="$2" pkg="$3" prefix="$4" friendly="$5" \
        region="$6" description="$7"

  echo
  echo "#################################################################################"
  echo "## MATRIX ROW '$label': slug=${#slug} pkg=${#pkg} prefix=${#prefix}"
  echo "##   friendly=${#friendly} region=${#region} description=${#description} characters"
  echo "##   $slug / $pkg / $prefix"
  echo "#################################################################################"

  local out="$WORK/$label"
  mkdir -p "$out"
  echo "== rendering template to $out =="
  uvx --from cookiecutter cookiecutter --no-input -o "$out" "$HERE" \
    project_slug="$slug" package_name="$pkg" env_prefix="$prefix" \
    friendly_name="$friendly" region="$region" \
    description="$description"

  local dir="$out/$slug"
  cd "$dir"

  echo "== creating venv + installing the commons from $COMMONS_ROOT =="
  uv venv --python 3.12 .venv >/dev/null
  # shellcheck disable=SC1091
  source .venv/bin/activate
  uv pip install --quiet \
    -e "$COMMONS_ROOT/pii-kit" \
    -e "$COMMONS_ROOT/hex-service-kit" \
    -e "$COMMONS_ROOT/agent-eval-kit" \
    -e "$COMMONS_ROOT/review-kit" \
    fastapi uvicorn httpx pydantic pyyaml types-PyYAML \
    ruff==0.16.4 mypy pytest jsonschema
  # Install the rendered repo itself WITHOUT re-resolving its git+https commons pins.
  uv pip install --quiet --no-deps -e .

  # The MANAGED verifier, deliberately installed here and nowhere in the rendered dev toolchain.
  # `make gate` in a rendered repo stays SDK-free, which is the whole offline-gate claim; but
  # that left the ONE adapter whose declaration switches the exposure guard off with nothing but
  # `# pragma: no cover - needs live GCP` over it, and three defects lived in three of its lines.
  # google-auth (and `cryptography` to mint a key with) are what let this gate run the real
  # verifier over locally minted assertions, with no project, no credential and no network.
  # Both are already pinned in the rendered requirements-gcp.lock, so nothing new ships.
  # `requests` is not decoration: `google.auth.transport.requests` refuses to import without it,
  # which is the transport the adapter constructs. All three are pinned in the rendered
  # requirements-gcp.lock already, so nothing new ships; they are simply not in the dev lock.
  uv pip install --quiet google-auth cryptography requests

  # `make lint` FIRST, and by name. It is the first step a repo owner runs, the first step of
  # `make gate`, and the first step of the shared hard-gate workflow; when it is red on arrival
  # nothing after it has been observed. Running the Makefile target (rather than ruff directly)
  # also proves the target itself renders and works with this env_prefix.
  echo "== make lint =="; make lint

  echo "== ruff check =="; ruff check src tests eval scripts
  echo "== ruff format --check =="; ruff format --check src tests eval scripts
  echo "== mypy src =="; mypy src

  # `make plugin` by name, for the same reason as `make lint` above: the target is part of
  # `make gate`, and a rendered repo that cannot render its own plugin directory is red on
  # arrival. The unit test exercises the RENDERER; this proves the TARGET, the module path it
  # names and the package name it was rendered with. A fresh repo has no vendored skills and no
  # MCP server, so this is also the only place the skills-less, server-less case is executed.
  echo "== make plugin =="; make plugin

  echo "== pytest =="; pytest -m 'not integration'
  echo "== eval (offline smoke) =="; python eval/run_eval.py

  # The other two halves of the rendered gate, by name, for the same reason as `make lint`
  # above: both are in `make gate`, and both are the kind of thing that is red on arrival
  # without anybody noticing. The judged half needs no model server and no network, and it
  # refuses its own table before grading anything; the doc check fails when the generated page
  # and the artifacts it describes disagree, which is exactly the state a freshly rendered repo
  # would be in if the renderer were broken.
  echo "== eval-narrative (judged, offline) =="; python eval/run_narrative_eval.py
  echo "== evals-doc --check =="; python scripts/render_evals_doc.py --check

  # The refutations this template was rebuilt to close, both of them a rendered repo serving a
  # real result (and honouring X-Dev-Persona) to a LAN peer with NO credential: first with the
  # profile variable ABSENT and the S2S token set, then with the profile chosen DELIBERATELY as
  # `local` and the S2S token set, because the guard only ever covered the zero-secret demo. Both
  # are covered by the rendered gate (tests/unit/test_serving_path_exposure.py), and the WHOLE
  # matrix is re-proved HERE over a real socket, because a TestClient asserts what the app object
  # does and a bound uvicorn asserts what a stranger gets.
  echo "== the exposure matrix, over a real socket, from a non-loopback address =="
  "$HERE/scripts/prove-exposure-matrix.sh" "$dir"

  # The commons pins are checked by OBJECT TYPE (an annotated tag object sha is also 40 hex, so a
  # regex cannot tell one from a commit). That check needs a git object store, and here it has
  # one: the commons are installed editable from git checkouts, named to it by
  # COMMONS_GIT_CHECKOUT_ROOT. Assert it actually RAN, so the guard cannot quietly degrade into a
  # skip in the one place it is guaranteed to have evidence.
  echo "== the commons pins are commits, checked against the real git objects =="
  # No extra -q: the rendered pyproject already passes one in `addopts`, and a second one is -qq,
  # which suppresses the "N passed" summary line the checks below read.
  local pin_check pin_status
  set +e
  pin_check="$(pytest --no-header -rs \
    tests/unit/test_repo_artifacts.py -k commit_object_and_not_a_tag_object 2>&1)"
  pin_status=$?
  set -e
  echo "$pin_check" | grep -E '[0-9]+ (passed|failed|skipped)|no tests ran' | sed 's/^/   /'
  assert_pytest_ran_and_passed "$pin_status" "$pin_check" \
    "the object-type check" "it has a git object store" || return 1

  # The IAP negative matrix against a LOCALLY MINTED key: the real google-auth verifier over
  # assertions this gate signs itself, offline. It is skippable by design where google-auth is
  # absent (the SDK-free `make gate`), so here, where it IS installed, the flag makes a missing
  # verifier a hard ERROR and the run is asserted to have PASSED rather than skipped. Same shape
  # as the pin object-type check above, and for the same reason: the one place with the evidence
  # must not be the place the check quietly degrades into a tick.
  echo "== the IAP negative matrix, real verifier, locally minted key, no network =="
  local matrix_check matrix_status
  set +e
  matrix_check="$(env "${prefix}_REQUIRE_IAP_MATRIX=1" \
    pytest --no-header -rs tests/unit/test_iap_crypto_matrix.py 2>&1)"
  matrix_status=$?
  set -e
  echo "$matrix_check" | grep -E '[0-9]+ (passed|failed|skipped|error)|no tests ran' | sed 's/^/   /'
  assert_pytest_ran_and_passed "$matrix_status" "$matrix_check" \
    "the IAP negative matrix" "google-auth is installed" || return 1

  # The demo surface is OUTSIDE `make gate` in the rendered repo (the gate proves the service,
  # not the story), so verify it here explicitly. A rendered repo that is green but not demoable
  # has not reached parity: 34 repos start from this output.
  echo "== demo self-test (headless, unattended) =="
  PYTHONPATH=src python scripts/walkthrough.py --auto --headless
  echo "== portability seam tour =="
  PYTHONPATH=src python scripts/portability_demo.py
  echo "== static demo render =="
  PYTHONPATH=src python scripts/demo.py demo.json --quiet
  PYTHONPATH=src python scripts/render_ui.py demo.json out >/dev/null
  echo "== documentation checks =="
  PYTHONPATH=src python scripts/check_docs_links.py

  # The UI's policy tests need NO node_modules: they import only node builtins and the plain
  # `.mjs` policy modules, which is why they were written that way. So the template's own gate
  # can run them offline, with no install, and it must: this gate never touched ui/ before, and a
  # wildcard-CORS two-state read planted in ui/lib/embed-policy.mjs therefore passed it
  # untouched. `tsc`, `npm ci` and the real `next build` still belong to the ui-gate workflow,
  # which has a node toolchain.
  echo "== ui policy tests (bare node, no install) =="
  node --test ui/tests/*.test.mjs

  # The gate must stay green for a repo that has NO ui/, because most catalog repos have none and
  # `make drop-ui` is the documented path. Proving it here means the removal path cannot rot.
  echo "== the same repo with the UI removed =="
  PYTHONPATH=src python scripts/drop_ui.py
  ruff check src tests eval scripts
  ruff format --check src tests eval scripts
  pytest -q -m 'not integration' >/dev/null
  echo "   gate still green with no ui/"

  deactivate
  cd "$HERE"
  echo "== ROW '$label': GREEN =="
}

# The name-length limits the hook enforces must be exactly what the `max` row renders at, or the
# hook is promising something this gate never observed. Check it here rather than trusting a
# comment: a limit is raised in the hook far more often than the matrix row is lengthened.
assert_max_row_matches_the_hook() {
  local row label slug pkg prefix friendly region description
  for row in "${MATRIX[@]}"; do
    IFS='|' read -r label slug pkg prefix friendly region description <<<"$row"
    [ "$label" = "max" ] && break
  done
  python3 - "$slug" "$pkg" "$prefix" "$friendly" "$region" "$description" <<'PY'
import re, sys, pathlib
slug, pkg, prefix, friendly, region, description = sys.argv[1:7]
text = pathlib.Path("hooks/pre_gen_project.py").read_text()
block = re.search(r"MAX_LENGTHS = \{(.*?)\}", text, re.S).group(1)
limits = {k: int(v) for k, v in re.findall(r'"(\w+)":\s*(\d+)', block)}
actual = {"project_slug": len(slug), "package_name": len(pkg),
          "env_prefix": len(prefix),
          "friendly_name": len(friendly), "region": len(region),
          "description": len(description)}
missing = sorted(set(limits) - set(actual)) + sorted(set(actual) - set(limits))
if missing:
    sys.stderr.write("MAX_LENGTHS and the `max` row cover different variables: %s\n" % missing)
    raise SystemExit(1)
bad = [f"{k}: hook limit {limits[k]}, `max` row renders {v}"
       for k, v in actual.items() if limits.get(k) != v]
if bad:
    sys.stderr.write("the `max` matrix row does not render at the hook's limits:\n")
    for line in bad:
        sys.stderr.write("  - " + line + "\n")
    sys.stderr.write("Lengthen the row, or lower the limit. A limit nothing renders at is a guess.\n")
    raise SystemExit(1)
print("   hook limits and the `max` row agree: " + ", ".join(f"{k}={v}" for k, v in actual.items()))
PY
}

cd "$HERE"
echo "== this gate's own pass/skip assertion, proved against synthetic summaries =="
assert_the_pytest_assertion_can_fail
echo "== the name-length limits the pre-gen hook enforces =="
assert_max_row_matches_the_hook
provide_commons

ran=0
for row in "${MATRIX[@]}"; do
  IFS='|' read -r label slug pkg prefix friendly region description <<<"$row"
  if [ -n "$WANTED" ] && [ "$WANTED" != "$label" ]; then
    continue
  fi
  verify_one_render "$label" "$slug" "$pkg" "$prefix" "$friendly" \
    "$region" "$description"
  ran=$((ran + 1))
done

if [ "$ran" -eq 0 ]; then
  echo "no matrix row matched '$WANTED'" >&2
  exit 1
fi
if [ -n "$WANTED" ]; then
  echo
  echo "== ONE ROW ONLY ('$WANTED'): this is NOT the gate. Run with no argument before landing. =="
  exit 0
fi
if [ "$COMMONS_PINNED" -ne 1 ]; then
  echo
  echo "== GREEN across ${ran} name sets against the commons AS THEY STAND in $COMMONS_ROOT:"
  echo "== this is NOT the gate. Unset COMMONS_GIT_CHECKOUT_ROOT and run again before landing. =="
  exit 0
fi

echo
echo "== TEMPLATE RENDER GATE: GREEN across ${ran} name sets =="
