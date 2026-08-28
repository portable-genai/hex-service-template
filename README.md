# hex-service-template

A **reusable CI workflow** + a **cookiecutter template** that starts a new hexagonal agent repo AT Doc1 parity instead of
converging toward it. It pins the three commons packages, ships the mandated doc set and the
three adapter profiles, and its offline gate is green on render.

## What is here

```
reusable-workflows/hard-gate.yaml      # the workflow_call reusable workflow (canonical source)
.github/workflows/hard-gate.yaml       # the same file, hosted so `uses: .../hard-gate.yaml@v0.0.1` resolves
cookiecutter.json                      # the template variables
{{cookiecutter.project_slug}}/         # the generated repo (a complete hexagonal agent)
BOOTSTRAP-CHECKLIST.md                 # the contract for whoever builds the next repo
ui-base/                               # the older shared Next.js skeleton (superseded, see below)
```

**Read [`BOOTSTRAP-CHECKLIST.md`](BOOTSTRAP-CHECKLIST.md) before rendering a repo.** It states
exactly what a rendered repo already has, what must be done first, and what remains genuinely
per-repo work. It is the contract the repo-building agents follow; keeping it current is part of
changing this template, not a follow-up.

## 1. The reusable hard-gate workflow

The catalog's SDK-free hard gate (`ruff` + `ruff format` + `mypy --strict` + `pytest -m 'not
integration'` + `eval`) and the `pip-audit` supply-chain job, as one `workflow_call` workflow with
SHA-pinned actions. `pip-audit` is a HARD gate: no `continue-on-error`, so a known-vulnerable
dependency fails the run exactly like a failing test. A consuming repo replaces its per-repo CI
body with:

```yaml
jobs:
  gate:
    uses: portable-genai/hex-service-template/.github/workflows/hard-gate.yaml@v0.0.1
    with:
      python-versions: '["3.12", "3.13"]'
      run-eval: true
      dev-lockfile: requirements-dev.lock
      runtime-lockfile: requirements-gcp.lock
      iap-matrix-path: tests/unit/test_iap_crypto_matrix.py
```

`iap-matrix-path` names the IAP negative matrix, which cannot run in the gate above because
google-auth is deliberately absent from the dev lockfile. Naming it adds a job that installs the
RUNTIME lockfile and runs that module with its require-flag on, so a missing verifier is an error
rather than a silent skip: the one adapter whose declaration stands the loopback exposure guard
down must not be the one adapter nobody tests. The job stays offline (the signing key is minted
in-process and the key-set fetch is served in-process). It reads the environment prefix out of the
repo's `.env.example`, because workflow files are copied without rendering and a per-repo literal
in a workflow is wrong exactly once. Leave the input empty and the job does not run at all.

The two lockfile inputs default to empty, so a repo that has not compiled its locks keeps the
older extras-based install. When they are set, CI installs from the lock and then the project with
`--no-deps` (the lock stays authoritative), and `pip-audit` judges exactly the versions CI and the
container image install rather than a fresh resolve nobody ships. Every repo rendered from the
template passes them.

Bumping the gate for every repo becomes a change to the ref, not N per-repo edits (this retires
the RECURRENCE of the supply-chain sweep). To resolve across private repos of one owner, enable
"Accessible from repositories owned by the user" in this repo's Actions settings.

## 2. The cookiecutter template

Generates a complete hexagonal agent repo: a pure-stdlib domain core with a deterministic service,
`@runtime_checkable` ports, three adapter profiles (local / gcp-lazy / onprem placeholder), a DI
container driven by `config/settings.yaml`, a FastAPI app wired with the commons identity / S2S /
fail-closed helpers, rule R8 routing to the Hrz7 review console through `review-kit`, an
`eval/run_eval.py` using the eval-kit scaffold + a not-falsely-green test, committed lockfiles, a
hardened Dockerfile (digest-pinned, non-root, healthchecked), a vertical-neutral
`infra/terraform/` deploy posture (residency validated at plan time, Org Policy, regional CMEK,
least-privilege IAM, a locked WORM log bucket, security alerts, a dry-run-first VPC-SC perimeter
and an opt-in Cloud Run edge, all checked offline by `make tf-check` and by a CI job), and
the full mandated artifact set (LICENSE, AGENTS.md, docs/practices-audit.md,
.env.example, .env.secrets.example). The four commons packages are pre-pinned by tag.

It also packages itself. `make plugin` renders an Agent Plugins 1.0.0 directory from what the
repo ALREADY declares, so the manifest is never a second description of the service that can go
out of step with it: identity comes from the A2A agent card, keywords from the governed tool
catalog when the repo has grown one and from the card's skills when it has not, and `skills/`
from `.agents/skills`. Both of those last two are DETECTED rather than configured, which is what
makes it work on day one: a freshly rendered repo has no vendored skills and no MCP server, so it
renders a valid skills-only plugin and grows into a full one instead of failing on arrival.

Rule R8 is wired, not documented: the rendered service routes every escalated result to the
review console in the same request that produced it, with a `ReviewRouterPort` bound in all three
adapter families, and `tests/unit/test_review_routing.py` fails the build if an escalation stops
at the `requires_human_review` flag. A rendered repo never owes R8 as a hand addition.

It is also DEMOABLE on render, not merely green. `scripts/` carries the whole demo surface (the
scripted arc, a static audit-first renderer, a live click-through server, a presenter-paced
walkthrough that doubles as the unattended self-test, an executable portability claim and an
offline documentation checker), and `ui/` carries an embeddable micro-frontend whose browser
never asserts an identity. Both are stdlib-and-npm-lock reproducible, both have their own CI
workflow, and `make drop-ui` removes the UI consistently for a repo that has no user-facing
surface. `make demo` works in a fresh render with zero hand edits.

Interactively:

```sh
uv tool install cookiecutter                      # or: pip install cookiecutter
cookiecutter path/to/hex-service-template
# answer the prompts (project_slug, package_name, catalog_id, env_prefix, region, ...)
cd <project_slug> && make install && make gate    # the offline gate is green on render
```

Non-interactively (the form to use when scripting a batch of repos). Every variable is passed as
`key=value` after the template path, and `--no-input` suppresses the prompts:

```sh
cookiecutter --no-input --output-dir ~/Documents/portable-genai path/to/hex-service-template \
  friendly_name="Contact Centre AI" \
  project_slug="contact-centre-conversations" \
  package_name="contact_centre_conversations" \
  catalog_id="E1" \
  description="A grounded, audited contact-centre assistant." \
  env_prefix="CONTACT" \
  region="asia-southeast1" \
  commons_version="0.0.1" \
  eval_kit_version="0.0.1" \
  pii_kit_version="0.0.1" \
  review_kit_version="0.0.1"
```

Then, in the rendered directory:

```sh
python3.12 -m venv .venv && source .venv/bin/activate   # stdlib venv, so pip is present
make install                                            # locked install; resolves the four pins
make gate                                               # offline: lint, types, tests, eval, plugin
make audit                                              # pip-audit over both locks (needs network)
```

`package_name` must be a valid Python identifier and `env_prefix` an upper-case environment
prefix; neither is derived from `project_slug`, so pass all three explicitly.

### The commons pins

Four release lines, moving independently, so four variable PAIRS: a version naming the release
tag that `pyproject.toml` declares, and the commit that tag resolves to, which is what the
lockfiles pin.

| Version variable | Commit variable | Package |
|---|---|---|
| `commons_version` | `commons_commit` | `hex-service-kit` |
| `eval_kit_version` | `eval_kit_commit` | `agent-eval-kit` |
| `pii_kit_version` | `pii_kit_commit` | `pii-kit` |
| `review_kit_version` | `review_kit_commit` | `review-kit` |

`cookiecutter.json` holds the default tag and the commit it resolves to for each pair; read the
values there rather than from prose, which goes stale the moment a pin moves.

`commons_version` is a security floor, not a preference. The pinned release checks the
service-identity policy before the token, gates the zero-secret local opening on an exact profile
match, covers WebSocket scopes in the exposure guard, and exports `read_env_setting`, which
resolves every environment read in three states, so a variable an operator deliberately emptied
does not inherit the more permissive unset default. The rendered `config.resolve_profile` is built
on it. It also carries `hex_service_kit.federation`, which owns the IAP transport facts (which
header carries an assertion, the issuer, the key set) that the rendered `adapters/gcp/identity.py`
rebinds instead of re-declaring. Never render a new repo below it.

`review_kit_version` is what makes rule R8 real rather than aspirational, so it is not optional
either: without it a rendered repo would set `requires_human_review` and stop.

### Lockfiles

The rendered repo ships `requirements-dev.lock` and `requirements-gcp.lock`, compiled with
`uv pip compile --universal` so one file installs across the whole CI matrix. `make install`, CI
and the Dockerfile all install from a lock and then the project with `--no-deps`.

The four commons are pinned in the lockfiles by 40-character COMMIT, never by tag. A tag is a
movable pointer: a re-pushed tag changes what installs with NO diff in the lockfile and nothing in
the repo to notice, which breaks the reproducible-install claim exactly where it should be
strongest. `pyproject.toml` keeps the TAG, because that is the half a human can review, and each
lockfile header carries a `tag = commit` map so `tests/unit/test_repo_artifacts.py` can prove the
three-way agreement with no network.

Dereference a tag with `git rev-list -n 1 <tag>`, NOT `git rev-parse <tag>`: these are annotated
tags, so `rev-parse` returns the tag OBJECT, which is a different sha and is not a commit.

After changing a dependency or a version variable, run `make lock` in a rendered repo and copy
both files back into `{{cookiecutter.project_slug}}/`, re-templating the four commons lines and
the project slug.

## 3. The UI

Every rendered repo now carries its own `ui/`: a Next.js App Router console that runs standalone
and embeds into a client application, with a server-verified identity boundary (the browser never
asserts an actor, the service credential never leaves the server), per-tenant CORS and a framing
allowlist that refuses a wildcard. It ships a committed `package-lock.json` and its own CI job
(`tsc`, node tests, production build, `npm audit --audit-level=high`), all guarded so the
workflow is correct whether or not the repo kept the UI.

`ui-base/` is the older shared skeleton and is kept only as a reference for repos that predate
this. New work goes in `{{cookiecutter.project_slug}}/ui/`, which is render-verified.

## Verifying the template

`scripts/verify-render.sh` renders the template ACROSS A MATRIX OF NAME LENGTHS (`short`,
`default`, `refuted`, `max`), and for each render installs the four commons from their local
checkouts and runs `make lint` and `make plugin` by NAME and then the full offline gate on the
output, THEN the socket-level exposure matrix, the demo self-test, the portability tour, the
static render and the documentation checks, THEN the whole gate again with `ui/` removed.
The two targets are run by name for the same reason: a unit test exercises the renderer, but only
the target proves the make wiring and the module path it names, and `make plugin` is also the
only place the skills-less, server-less render is executed, which is the state every new repo
starts in. Every row must be green. Run
it after editing any template file.

The matrix exists because nothing in a rendered repo may depend on the LENGTH of a rendered
value, and a one-row gate cannot see when something does: `make lint` enforces 100 columns, and a
line that fits at the default `example_agent` was red at a 42 character package name. The `max`
row renders at exactly the limits `hooks/pre_gen_project.py` refuses to exceed, so the boundary
is stated, enforced and tested rather than assumed.

It proves the CODE renders and passes. It does not prove the version PINS resolve or that the
committed lockfiles install: for that, render outside this workspace and run `make install`.

## License

Apache-2.0. Synthetic, obviously fictional data only.
