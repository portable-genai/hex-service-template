# Bootstrap checklist: what a rendered repo already has, and what you must still add

This is the CONTRACT between `hex-service-template` and whoever builds the next repo from it.
Read it before you write a line. Two rules govern everything below:

1. **If it is in section 1, do not rebuild it.** It is already there, already tested, and already
   consistent with the other repos. Rewriting it is how a fleet stops being a fleet.
2. **If it is in section 3, it is yours and nobody else will do it.** A rendered repo is green and
   demoable, which is not the same as finished. Section 3 is the honest difference.

If you find yourself hand-building something the template should have given you, fix the TEMPLATE
and re-render. Every gap closed here is closed for every repo that follows; every gap worked
around in one repo is a gap the next thirty inherit.

---

## 0. Render it

```bash
uvx --from cookiecutter cookiecutter --no-input \
  -o <parent-dir> <path-to>/hex-service-template \
  friendly_name="Contact Centre Assistant" \
  project_slug=contact-centre-conversations \
  package_name=contact_centre_assistant \
  env_prefix=CONTACT \
  region=australia-southeast1 \
  description="One sentence, in the catalog's voice."
```

Rules that are not negotiable:

- Every variable goes AFTER the template path, as `key=value`. Cookiecutter ignores a variable
  passed before it, silently, and you get the defaults.
- **Rendering is not idempotent.** Always render into a clean path. Re-rendering over an existing
  directory produces a mixture of both.
- `project_slug` must match the repository name as listed on the organization front page,
  <https://github.com/portable-genai>. It is how the rest of the catalog finds this repo, and
  it is the repository's only identity.
- `package_name` is a Python identifier: lowercase, underscores. `env_prefix` is uppercase and
  short; it prefixes every environment variable this service reads.
- `region` is the residency region and is shared by the runtime and Terraform. Pick it from the
  client's jurisdiction, not from habit.

Then, once, in the rendered repo:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install        # locked install; needs network the first time (git tags for the commons)
make gate           # must be green with ZERO edits. If it is not, the template has a bug.
make demo-selftest  # must pass with ZERO edits
```

`make gate` green on the first try is the template's promise. If it fails, do not patch the repo:
report it against `hex-service-template`, because it is failing in every repo rendered that day.

---

## 1. What the template ALREADY gives you (do not rebuild)

### Architecture and code
- Hexagonal layout: `domain/` (pure stdlib, kernel and vertical split), `ports/` (runtime-checkable
  Protocols re-exported once), `adapters/{local,gcp,onprem}/`, `config.py` with a settings-file
  binding table, `api/`, `cli/`, `agent/`.
- Three profiles, swappable by one environment variable, with every port bound in every profile.
  Managed SDK imports are lazy, so the offline profiles import with no SDK installed.
- A deterministic domain service, redact-before-audit, citations on every result, and rule R8
  routing on every surface (API, CLI, agent tools).
- Identity as a server-verified `Principal`; the client-asserted actor is discarded everywhere.
- A hash-chained WORM audit log with an EXTERNAL head anchor, and honest limits written down.

### Born fail-closed
- The profile resolves once, at import, into a `ProfileChoice`. Three states of one variable:
  UNSET is NO CHOICE (never a silent `local`), SET-AND-EMPTY refuses to boot rather than
  inheriting the unset behaviour, and an unknown or mis-capitalised value refuses too. Name the
  profile in your deployment; there is no default.
- Two derived postures, because they fail closed in opposite directions: `exposure_profile`
  drives the relaxations (CORS, the `X-Dev-Persona` header, HSTS, the S2S scheme) and reads
  `unconfigured` when nobody chose; `bind_profile` drives the loopback bound and reads `local`.
- The seeded dev personas refuse to be served unless `local` was chosen DELIBERATELY, so a
  deployment whose profile variable went missing cannot hand out an approver persona.
- The loopback exposure guard is bound to the app OBJECT, so it holds under the Dockerfile `CMD`
  as well as under `make run-api`, and its posture comes from the IDENTITY BINDING: a deployment
  whose identity adapter cannot verify an end user (the seeded personas, the on-prem placeholder,
  or no profile at all) refuses EVERY route to a non-loopback peer, including `/healthz`. Setting
  `<PREFIX>_S2S_TOKEN` does not change that: it authenticates a calling service and no end user.
  Binding an adapter that declares `end_user_auth = VERIFIED` is what lifts the bound.
- The UI reads `UI_PROFILE` the same three ways and refuses to seed a persona when nobody chose,
  and reads `UI_FRAME_ANCESTORS`, `UI_TENANT_ORIGINS` and `AGENT_API_URL` the same three ways
  through `ui/lib/env-setting.mjs`. The two allowlists are resolved at module scope in
  `next.config.mjs`, so an emptied one fails `next build` and `next start` rather than serving
  the shipped default and looking exactly like a UI nobody configured. The OUTBOUND
  `AGENT_S2S_TOKEN` is the one deliberate two-state read, matching
  `hex_service_kit.s2s.client_headers`: the receiver decides whether an uncredentialed call is
  acceptable, and it refuses an emptied secret itself.
- CORS never falls back to `*`; an emptied variable denies rather than inheriting a default.
- The managed review router refuses rather than swallowing an escalation.

### The drift guards (the reason a repo stays at parity)
- A port is registered in FIVE places and set equality is asserted across all five, in both
  directions. Four out of five is a port with zero enforcement and a green build.
- Behavioural parity: the offline family must ANSWER, the exit family must RAISE, the managed
  family must REFUSE in its documented way. Not merely "did not raise".
- The SDK-free claim is proved by BLOCKING the import in a fresh interpreter, not by the machine
  happening to have no SDK installed.
- A scan that fails the build if any module other than `config.py` re-reads the profile variable,
  and a wider one that fails it for ANY two-state `os.environ.get` / `os.getenv` read in `src/`,
  `scripts/` or `eval/`. The narrow guard alone is how a two-state read of a DIFFERENT variable
  once survived in two repos with a green build.
- The same scan for `ui/`, written in node because the Python one parses Python. It walks every
  shipped `.mjs` / `.js` / `.ts` / `.tsx` and fails on any direct `env.X` read that is neither an
  exact-match comparison against a literal nor exempted with a written reason. The Python-only
  guard is how `env.UI_TENANT_ORIGINS || "*"`, a wildcard CORS allowlist one emptied variable
  away, once passed the entire gate with `tsc` clean and every test green.
- A scan that expands the exposure guard's `unauthenticated=` argument through the module
  constants it names and fails the build if it reaches ANY service credential, with the original
  defect carried as the mutant it must go red on. The guard bounds END-USER routes, and an S2S
  token authenticates a calling service and no end user.
- The commons pins are checked by git OBJECT TYPE, not by a regular expression: an annotated tag
  object's sha is also 40 hex characters, and swapping one in passed every structural check.
- The test layout is enforced: an unmarked integration module fails the build.

### The deploy posture (`infra/terraform/`, vertical-neutral and already enforced)
- Residency validated at PLAN time: the region and the allowlist both default to the region this
  repo was rendered for, and an out-of-allowlist region fails `terraform plan` rather than moving
  regulated data out of jurisdiction.
- Org Policy guardrails (resource-location allowlist, no service-account key creation, uniform
  bucket-level access, optional domain-restricted sharing), a REGIONAL CMEK key ring with 90-day
  rotation and per-service-agent bindings, a least-privilege serving identity, a locked WORM
  Cloud Logging bucket plus sink with DATA_READ auditing on, five log-based security metrics with
  alert policies, and a VPC-SC perimeter that starts in DRY RUN.
- The serving edge is OPT-IN (`production_edge_enabled = false`): Cloud Run behind an external
  load balancer, Cloud Armor and IAP, with a digest-pinned image, CMEK on the revision, and the
  three-state environment discipline carried onto the service (a variable with no value is ABSENT
  rather than empty).
- `render.tf.json` is the only file cookiecutter rendered; everything else there is verbatim, so
  the WORM sink filter and the managed audit adapter's logger name derive from the SAME rendered
  package name and agree by construction.
- What is NOT there, deliberately: this vertical's own resources. A store, a warehouse, a bucket
  or a recogniser is added in FOUR places in one commit (`apis.tf`, `kms.tf`, `iam.tf`,
  `vpc_sc.tf`) plus its own file. A service enabled with no CMEK binding encrypts under
  Google-managed keys and looks identical in the console.

### Tests, gate and CI
- `tests/{unit,contract,integration,fixtures}` with a shared `conftest.py` driving the REAL local
  adapters, and one canonical request per port shared by the structural and behavioural suites.
- `make gate`: ruff check, ruff format, mypy strict on `src`, pytest (integration deselected),
  and the offline eval smoke check. Offline, credential-free, network-free.
- `make tf-check`: `terraform init -backend=false`, `validate`, `fmt -check -recursive` and
  `test`. Deliberately OUTSIDE `make gate` (it needs the terraform binary, and the gate must run
  on Python alone), but not optional: the hosted check runs the same four commands in its
  own terraform step. `terraform test` is the half that carries the refusals, over `mock_provider` and
  plan-only runs, so it needs no project and no credentials either.
- `make audit`: `pip-audit` over both lockfiles (the one step that needs network).
- No hand-written workflows, deliberately. CI is a GitHub Actions caller RENDERED from the
  reviewed contract, which runs this repo's OWN make targets: the gate, the demo self-test, the
  portability tour, `ui-check` where there is a UI, and the terraform test. It reaches a new
  repository only once `org-metadata/ci/gcp/repository-policy.json` names it and the caller is
  rendered and committed; until then the repo is gated by its local `make gate` alone, and
  nothing reports that gap. Registering a new repository is therefore a step someone has to
  take -- the seven commons kits sat in the contract with no required check at all until
  2026-09-02, and nothing anywhere reported it.
- Committed `requirements-dev.lock`, `requirements-gcp.lock` and `ui/package-lock.json`; every
  install path uses them; dependabot watches pip, docker and npm.

### The demo surface (`scripts/`, all offline and stdlib-only)
- `make demo` : the presenter-paced eight-step walkthrough, starting its own loopback server,
  narrating on the terminal and waiting for the presenter.
- `make demo-selftest` : the same walkthrough headless and unattended, asserting every step.
- `make demo-static` : the audit-first output view as static HTML, for screenshots.
- `make portability` : the executable, BOUNDED portability claim, pass or fail per named check.
- `make docs-check` : relative links resolve, code fences close, no em-dash or en-dash in prose.
- No browser engine, no bundler, no network, no cloud. It runs from a checkout on a locked-down
  laptop, which is exactly where a demo gets asked for.

### The UI (`ui/`)
- A Next.js App Router console that runs standalone and embeds in a client application.
- The security boundary: the browser never asserts an actor, identity is resolved server-side, the
  service credential never leaves the server, and framing and CORS are per-tenant allowlists that
  refuse a wildcard. Covered by node tests in CI and by source assertions in the offline gate.
- **The document CSP is nonce-based and the route is forced dynamic.** Both are load-bearing:
  `script-src 'self'` blocks Next's inline hydration bootstrap, and a nonce on a statically
  prerendered route blocks even more. Do not "simplify" either one, and do not reach for
  `'unsafe-inline'`. `assertHydratableCsp` fails the build if `app/layout.tsx` loses
  `force-dynamic`, and the ui gate runs `npm run assert-hydratable` against a real build.
- **`next dev` writes no documents.** `next.config.mjs` sets `agentRules: false`, because the
  default generates `ui/AGENTS.md` and `ui/CLAUDE.md`: a second working agreement plus the
  tool-specific alias the catalog convention forbids, and its prose carries an em-dash that
  `make docs-check` fails on. The gate asserts the flag AND asserts both files are absent, so a
  framework bump that renames the option is caught by the artifact rather than by the spelling.
- **If this repo has no user-facing surface, run `make drop-ui`.** It removes the directory, its
  dependabot ecosystem and its CI job together; the gate checks the three for consistency in both
  directions, so half a removal fails the build.

### Observability (already wired, do not re-invent)
- Two ports arrive bound in all three profiles: `tracer` and `evaluation`. Neither Protocol is
  declared in this repo. They are imported from the commons (`hex_service_kit.observability`,
  `agent_eval_kit`), because sixteen hand-copied versions of them had already drifted apart.
- The domain service opens one span per unit of work. Add spans to YOUR units of work the same
  way, with structural attributes only, never content.
- `configure_logging` is called for you in `api/app.py` and the CLI. Use `logging.getLogger(
  __name__)` and log freely; only the allowlisted extras (`tenant`, `actor`, `correlation_id`)
  reach the sink, so an accidental `extra={"prompt": ...}` cannot leak.
- Where spans GO is deployment configuration, not code: `OTEL_EXPORTER_OTLP_ENDPOINT` set means
  OTLP to the `agent-observability` collector, unset means straight to Cloud Trace. Do not add a profile for it.

### Documents
- `SPEC.md` > `ARCHITECTURE.md` > `COMPLIANCE.md` > `README.md` (the declared authority order),
  plus `AGENTS.md`, `CONTRIBUTING.md` with file-by-file
  extension walkthroughs, `DEMO.md`, `docs/runbook.md`,
  `docs/onprem-migration.md`, `docs/practices-audit.md` and `scripts/README.md`.
- `COMPLIANCE.md` maps the full P-01..P-13 and R1..R8 with an explicit `TODO (repo owner)` on
  every row that can only be satisfied per repo. Those TODOs are your work list.
- `docs/practices-audit.md` ships pre-filled: 35 PASS, 1 PARTIAL, 3 GAP, 2 N/A on render.

---

## 2. What you must do FIRST, in the rendered repo (before any feature work)

These are small, and skipping them is how a repo drifts on day one.

1. **`git init`, first commit, push.** The template renders a tree, not a repository.
2. **Read `COMPLIANCE.md` top to bottom** and turn every `TODO (repo owner)` into an issue. They
   are the compliance backlog and nobody else is tracking them.
3. **Replace the vertical.** `domain/models.py`, `domain/triage_service.py`,
   `domain/pii.py` (jurisdictions), `eval/datasets/golden_cases.jsonl` and the demo's synthetic
   cases in `scripts/demo.py` are the EXAMPLE vertical. Keep `domain/kernel.py`.
4. **Rewrite the demo arc for your vertical.** Keep the eight-beat shape (bind, routine case,
   consequential case, redaction, reviewer queue, audit, tamper, exit) and change what each beat
   shows. Add the matching entry to `walkthrough.CHECKS`; the gate fails if you forget.
5. **Decide about `ui/` now, not later.** Keep it and wire your screens, or run `make drop-ui`.
   Leaving a half-wired UI is the worst of the three options.
6. **Record the repo in the maintainer's system tracker:** set `Implementation status` to
   `Built` and replace `(not built)` with the real remaining gaps from section 3.
7. **Check the residency story hangs together.** The region reaches Terraform through
   `infra/terraform/render.tf.json`, which cookiecutter already filled from the `region` you
   rendered with, so there is nothing to edit there; confirm `config/settings.yaml` and
   `.env.example` name the same region, then run `make tf-check` once to see the posture pass
   offline. Override the region or widen the allowlist in `terraform.tfvars`, never by editing
   the rendered locals.
8. **Re-run `docs/practices-audit.md` against the tree** and correct any row your vertical
   changes. It ships pre-filled as what the TEMPLATE can honestly claim, not as an inspection of
   your repo.

---

## 3. What the template does NOT give you (this is your work)

Nothing below is a template defect. Each is genuinely per-repo, and each is a real gap in a
rendered repo until you close it.

| # | Gap | Why the template cannot do it | Where it is recorded |
|---|---|---|---|
| 1 | **The vertical itself.** The domain models, the deterministic engine, the real policy, the retrieval/grounding port, the real screens. | It is the whole point of the repo. | `domain/`, `ui/app/` |
| 2 | **This vertical's own cloud resources, and the one real apply.** The posture baseline ships and is checked offline; what remains is per-repo: your data-plane resources (store, warehouse, buckets, any recogniser) each with their API in `apis.tf`, their CMEK service-agent binding in `kms.tf`, their least-privilege role in `iam.tf` and their entry in `vpc_sc.tf`; your vertical's own alert policies; then applying it to a real project (notification channels, IAP members, the image digest, the Access Context Manager policy id, and the two-apply `iap_audience` sequence), and enforcing the perimeter only after a full business cycle of dry-run evidence. | Needs a real project, a real org policy and a real perimeter, and the resources depend on the vertical. | practices-audit `D5`; `COMPLIANCE.md` P-01, P-03, P-09 |
| 3 | **Bank-owned policy numbers in config.** The severity bands are module constants; lift them into a frozen policy dataclass with a `policy:` block in `config/settings.yaml`. | The numbers are the client's, and the shape depends on your engine. | practices-audit `B4` |
| 4 | **`docs/ADOPTING.md`** if this repo will itself be forked. | Only you know whether it will. | practices-audit `G3` |
| 5 | **`docs/faq/`** (security, compliance, features, portability, adoption), referencing sibling systems. | The answers are vertical-specific. | practices-audit `G5` |
| 6 | **`agent-registry` registration of the agent card**, and the `agent-guardrail-gateway`, `agent-observability` and `model-quality-gate` bundle bindings. | Needs the live horizontals. | `COMPLIANCE.md` R1, R2, R4, R5 |
| 7 | **A grounded retrieval port** and the hard error on empty retrieval. | Only exists once there is a knowledge base to ground against. | `COMPLIANCE.md` P-05; practices-audit `B2` |
| 8 | **A model card** and the model routing, budget and kill-switch controls. | Needs the chosen model and the chosen limits. | `COMPLIANCE.md` P-07, P-10, P-11 |
| 9 | **Object-level authorisation from data tags.** The tenant partition is carried on outbound reviews; there is no queryable store yet to authorise against. | Arrives with your first data store. | practices-audit `C2` |
| 10 | **A real Docker image build.** The Dockerfile is asserted statically (digest-pinned base, non-root, healthcheck, lockfile install) but has never been built in template verification. | No docker in the verification environment. | build it once, early |
| 11 | **`ui/Dockerfile`** if you deploy the UI as its own service. | The base image must be digest-pinned by whoever builds it. | `ui/README.md` |
| 12 | **The anchor directory.** `audit_anchor_path` must point at a file on a DIFFERENT volume under different credentials, and the parent directory must be provisioned by the operator (the log creates its store's parent, not the anchor's). | It is a deployment decision, not a code one. | `docs/runbook.md`; `.env.example` |
| 13 | **Branch protection.** Require `gate`, `IAP negative matrix (runtime lockfile)`, `eval smoke check (pre-merge)`, `demo self-test + portability + docs` and, if you kept the UI, the UI gate. | GitHub settings, not files. | repository settings |
| 14 | **`<PREFIX>_IAP_AUDIENCE` for the managed deployment.** The IAP-protected resource the assertion must be addressed to. Until it is set, the `gcp` profile starts, stays health-checkable and refuses every end-user request with 503 naming the variable. It is not optional and there is no unverified fallback: `audience=None` means the audience is NOT verified. | Only the deployment knows its backend service id. | `docs/runbook.md`; `.env.example` |
| 15 | **Real screenshots and a rehearsed demo.** `make demo-static` produces the pages; somebody still has to look at them and rehearse the narration. | Judgement. | `DEMO.md` |

### Things that are deliberately NOT provided, and should stay that way

- **Browser automation for the demo.** A walkthrough needing Playwright cannot be installed
  offline or run in a no-egress job. If you genuinely need one for a `ui/` flow, add it as a
  SEPARATE script with its own optional dependency and leave `walkthrough.py` runnable everywhere.
- **`pip-audit` inside `make gate`.** Every gate step is offline; the audit needs a vulnerability
  feed. It lives in `make audit` and in the CI supply-chain job, where it is a hard failure.
- **An ADK `root_agent` or an A2A server.** The agent runtime is optional and the gate installs
  none. `agent/` ships tool callables plus the card; add the runtime when you have one.
- **The demo inside `make gate`.** The gate proves the service and must stay fast; the demo has
  its own required check.

---

## 4. The traps that have actually bitten, in this template

Read these before editing the TEMPLATE (not the rendered repo).

- **A literal `{{` anywhere under `{{cookiecutter.project_slug}}/` is a Jinja opener**, including
  inside a test file, a CSS string or a JSX inline style. Build such strings by concatenation.
  Files that cannot avoid it (`${{ ... }}` in workflows, all of `ui/`'s code) are listed in
  `_copy_without_render` in `cookiecutter.json` and get no variable substitution at all.
- **Nothing may depend on the LENGTH of a rendered value.** `make lint` runs in the rendered repo
  at 100 columns, so a line carrying `{{ cookiecutter.package_name }}` that fits at the default
  is red at a longer one, and the render fails while the template looks fine. This shipped once:
  a 42 character package name produced five `ruff check` errors and one `ruff format` file with
  no hand edit anywhere. Three rules, all enforced by the render matrix in
  `scripts/verify-render.sh`: no fully-qualified `<package>.<module>.<Symbol>` cross-reference in
  prose (name the file instead); every first-party import written with a magic trailing comma so
  its layout never changes; every rendered value bound to a short module constant rather than
  written inline. `hooks/pre_gen_project.py` refuses a name longer than the matrix proves.
- **Import ORDER must not depend on the package name.** `tests` is a `known-local-folder`, and
  `scripts` is deliberately absent from `[tool.ruff] src`, so a sibling import never shares an
  isort section with the package import.
- **Do not reload adapter modules in-process to prove the SDK-free claim.** Reload rebinds the
  classes and already-imported test modules keep stale objects. Use the subprocess probe.
- **Verify with `grep -nE`, not basic grep.** BSD grep has no `\|` alternation, so the obvious
  em-dash check is a silent no-op. The correct form is
  `git diff --cached -U0 -- '*.md' '*.html' | grep -nE $'\u2014|\u2013'`. The rendered repo
  enforces this itself through `make docs-check`.
- **The `ui/` toolchain writes into the rendered tree, and `verify-render.sh` never starts it.**
  The render gate runs the UI's policy tests in bare node with no `node_modules`, deliberately,
  so nothing in it has ever executed `next dev`, `next build` or a lifecycle script. Next 16.3.0
  shipped a default that generates `ui/AGENTS.md` and `ui/CLAUDE.md` on `next dev`, and it
  reached fifteen repos before anyone noticed, because it appears only when somebody starts the
  dev server and only as an untracked file. `agentRules: false` in `ui/next.config.mjs` turns
  that one off. The general rule: after bumping `next`, read its release notes for anything that
  WRITES, and prove the fix by installing and running the dev server in a scratch render by
  hand. The gate cannot do it for you, so the offline gate asserts the ARTIFACTS are absent as
  well as the flag.

## 5. Verifying a template change

```sh
scripts/verify-render.sh
```

It renders FOUR name sets (`short`, `default`, `refuted`, `max`), installs the commons from local
checkouts, and runs `make lint` plus the full offline gate on each PLUS the demo self-test, the
portability tour, the static render, the documentation checks, and the whole gate again with
`ui/` removed. Every row must be green. `scripts/verify-render.sh <label>` runs one row for an
edit loop and is NOT the gate. It proves the CODE renders and passes; it does not prove the
version PINS resolve or that the committed lockfiles install. After changing a version variable
or a lockfile, also render OUTSIDE this workspace and run `make install` (which fetches the tags
from GitHub) before trusting the template.
