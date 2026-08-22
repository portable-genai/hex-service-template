# hex-service-template

The shared working agreement is [`.github/AGENTS.md`](https://github.com/portable-genai/.github/blob/main/AGENTS.md).
It carries the architecture rules, the gate contract, the fleet invariants, the
falsification discipline, versions and house style, and it holds in every repository
here. Read it first. This file carries only what is specific to this one.

## What this is

`hex-service-template` is a reusable CI
workflow + a cookiecutter template that starts a new hexagonal agent repo at Doc1 parity.
Siblings: `pii-kit`, `hex-service-kit`, `agent-eval-kit`.

## Layout

- `reusable-workflows/hard-gate.yaml` and `.github/workflows/hard-gate.yaml` are the SAME file
  (canonical source + hosted copy so the `uses:` ref resolves). Keep them in sync.
- `cookiecutter.json` declares the variables (`friendly_name`, `project_slug`, `package_name`,
  `catalog_id`, `description`, `env_prefix`, `region`, and a PAIR per commons package: a version
  variable naming the release TAG that `pyproject.toml` declares, and a commit variable carrying
  the 40-character COMMIT that tag resolves to, which is what the lockfiles pin. The four pairs
  are `commons_version`/`commons_commit` for `hex-service-kit`,
  `eval_kit_version`/`eval_kit_commit` for `agent-eval-kit`, `pii_kit_version`/`pii_kit_commit`
  for `pii-kit`, `review_kit_version`/`review_kit_commit` for `review-kit`. Bump both
  halves together; the rendered `tests/unit/test_repo_artifacts.py` asserts they agree.)
- `hooks/pre_gen_project.py` runs BEFORE generation and refuses a name the template has never
  been proved to render green: each variable has a maximum length (`MAX_LENGTHS`) and a shape.
  The limits are exactly what the `max` row of `scripts/verify-render.sh` renders at, and that
  script fails if the two ever drift apart.
- `{{cookiecutter.project_slug}}/` is the generated repo. Files under it use Jinja
  (`{{ cookiecutter.x }}`); the src package dir is `src/{{cookiecutter.package_name}}`. A literal
  brace pair inside a TEST file is a template opener too, so build strings like `${VAR:-}` by
  concatenation rather than with an f-string.
- `{{cookiecutter.project_slug}}/scripts/` is the DEMO surface and `{{cookiecutter.project_slug}}/ui/`
  is the embeddable micro-frontend. Both are rendered into every repo. `ui/`'s code files, all
  workflow files and every `infra/terraform/*.tf` and `*.tftest.hcl` are listed in
  `_copy_without_render`, so they receive no variable substitution at all (a JSX inline style, a
  `${{ ... }}` expression and a Terraform `${...}` interpolation are all Jinja openers).
- `{{cookiecutter.project_slug}}/infra/terraform/render.tf.json` is the ONE Terraform file
  cookiecutter renders, and the reason the rest can be copied verbatim. It is JSON so it can hold
  no interpolation at all, and it carries four locals (`render_region`, `render_package_name`,
  `render_env_prefix`, `render_catalog_id`) whose shapes the pre-gen hook already validates, so a
  render can break neither the JSON nor the HCL. `naming.tf` derives every name from them. A
  `*.tf` glob cannot match `.tf.json`, which is what keeps the split clean;
  `terraform.tfvars.example` renders too, and is the only other file there that may carry Jinja.
- `ui-base/` is the older shared skeleton, kept only as a reference for repos that predate the
  rendered `ui/`. New work goes in `{{cookiecutter.project_slug}}/ui/`, which IS render-verified.
- `BOOTSTRAP-CHECKLIST.md` is the contract the repo-building agents follow: what a rendered repo
  already has, what must be done first, and what remains genuinely per-repo. Update it in the
  same change that closes or opens a gap, or the 31 repos work from a stale contract.

## Lockfiles

`{{cookiecutter.project_slug}}/requirements-dev.lock` and `requirements-gcp.lock` are compiled
artifacts, not hand-written. To refresh them: render the template, run `make lock` in the output,
then copy both files back, replacing the rendered project slug with
`{{ cookiecutter.project_slug }}` and each commons COMMIT with the matching
`{{ cookiecutter.<name>_commit }}` variable.

Each lockfile header carries a `tag = commit` map, so the rendered
`tests/unit/test_repo_artifacts.py` can prove the three-way agreement between `pyproject.toml`,
that header and the pins, offline. Catalog repos have pinned `review-kit` at its ANNOTATED
tag object in bulk instead of at the commit the tag resolves to.

A shape check cannot catch that (a tag object's sha is also 40 hex, and swapping it in both
lockfiles and the header map leaves all three agreeing), so the rendered
`tests/unit/test_repo_artifacts.py` asks GIT what the pinned object is:
`test_each_locked_sha_is_a_commit_object_and_not_a_tag_object` runs `cat-file -t` against the
first local object store that knows the sha (a sibling checkout, `COMMONS_GIT_CHECKOUT_ROOT`, or
the directory an editable/local install came from) and also checks `rev-list -n 1 <tag>` against
the pin. It skips only where no store can answer, which is why `verify-render.sh` asserts it did
NOT skip there: the render harness installs the commons from their sibling checkouts, so evidence
is always available.

## Editing and verifying the template

The template is NOT rendered in place, so you cannot run its gate directly. After editing any file
under `{{cookiecutter.project_slug}}/`, run:

```sh
scripts/verify-render.sh
```

It renders the template FOUR TIMES, once per row of its name-length matrix, and runs the whole
verification on each: `make lint`, then `ruff` + `ruff format --check` + `mypy src` + `pytest` +
`python eval/run_eval.py`, THEN the socket-level exposure matrix, the pin object-type check, the
demo self-test, the portability tour, the static render, the documentation checks and the ui
policy tests, THEN the whole thing again with `ui/` removed. Each render installs the four
commons packages from their local sibling checkouts (so the git+https pins do not need to
resolve) and the rendered repo with `--no-deps`. All rows must pass. It shells out to `uvx --from
cookiecutter cookiecutter`, so it needs `uv` on PATH but not a system cookiecutter install.

The four rows are `short`, `default`, `refuted` and `max`. `scripts/verify-render.sh <label>`
runs one row for a fast edit loop and says so loudly; it is NOT the gate.

That script installs the commons from local checkouts, which means it proves the CODE renders and
passes, not that the PINS resolve. Those are different failures. After changing a version
variable, also render once with `pip install -e ".[dev]"` (no `--no-deps`, no local checkouts) so
the git tags are actually fetched from GitHub, and render outside this workspace so a throwaway is
never mistaken for a real repo.

## Invariants

- **The rendered repo's offline gate must stay green.** That is the whole value: a new repo starts
  at parity, not converging toward it.
- **Keep the two hard-gate.yaml copies identical.** When the workflow BODY changes, cut and push a
  new tag AND bump the `uses:` ref in `{{cookiecutter.project_slug}}/.github/workflows/ci.yaml`,
  or every repo rendered afterwards calls a stale workflow. The rendered
  `tests/test_repo_artifacts.py` enforces that the ref is a tag, never a branch.
- **Rule R8 is wired, not documented.** The rendered service routes every escalated result to the
  Hrz7 console through `review-kit`, in the same request that produced it, with a
  `ReviewRouterPort` bound in all three families. A local adapter that silently did nothing would
  let 31 repos ship with R8 unwired and a green gate, so the local binding uses the kit's outbox
  and `tests/test_review_routing.py` asserts the routing, not the flag.
- **NOTHING in a rendered repo may depend on the LENGTH of a rendered value, and a matrix proves
  it.** `make lint` is the first step of the rendered gate and of the shared hard-gate workflow,
  and it enforces 100 columns, so a line that fits at `example_agent` (13 characters) can be red
  at a 42 character package name with no hand edit anywhere. That is not a hypothetical: it
  shipped, and a single-row render gate declared the template green while it was true. Three
  rules keep the emitted source insensitive to length, and `scripts/verify-render.sh` renders
  `short` / `default` / `refuted` / `max` and runs the WHOLE verification on each:
  1. **No fully-qualified cross-reference in prose.** Write ``` ``VERIFIED`` (see
     ``ports/identity.py``) ```, never `` :data:`~<package>.ports.identity.VERIFIED` ``. The
     package name plus a long dotted suffix plus any sentence around it does not fit.
  2. **Every first-party import carries a magic trailing comma.** `from {{ cookiecutter.package_name }}.x import (\n    Name,\n)`
     has the SAME layout at every name length, so neither `ruff format` nor isort can want a
     different one. A one-line import is a line whose length the renderer chooses.
  3. **A rendered value goes in a short module-level constant, never inline in a statement or a
     literal.** `_ROUTING_ACTOR`, `_APP_TITLE`, `_APP_DESCRIPTION`. `ruff format` cannot wrap a
     string literal for you.
- **The bound is enforced, not assumed.** `hooks/pre_gen_project.py` refuses a render whose
  `project_slug` / `package_name` / `env_prefix` / `catalog_id` / `friendly_name` / `region` /
  `description` is longer than the `max` matrix row, or the wrong shape. "Any valid name renders
  green" is only testable with a stated boundary: a 300 character package name breaks any import
  line ever written. `verify-render.sh` fails if `MAX_LENGTHS` and the `max` row ever disagree,
  in either direction, so raising a limit without re-proving it is a build failure.
- The generated code must obey the shared working agreement in full. Do NOT introduce a
  `${{ ... }}` GitHub expression into a rendered file (it collides with Jinja); such files go in
  `cookiecutter.json` `_copy_without_render`.
- Bump BOTH halves of a commons pin in `cookiecutter.json` when a tag moves: the `*_version`
  (the tag `pyproject.toml` declares) and the `*_commit` (what the lockfiles install). One pair
  per package: they are separate release lines and must never share a value by accident.
- **A new repo must be born fail-closed, never converging toward it.** The rendered
  `api/app.py` binds `add_loopback_exposure_guard` at MODULE scope (the Dockerfile `CMD` and
  `make run-api` serve the app object, so anything living only in `main()` never runs in a shipped
  process), and `config.PROFILE_CHOICE` resolves the profile AT IMPORT into a `ProfileChoice`: an
  emptied, unknown or mis-capitalised value kills the process before it serves a request, and an
  UNSET one is carried forward as "nobody chose" rather than as a silent `local`. Relaxations key
  off the derived `exposure_profile` (`unconfigured` when nobody chose) and the loopback bound off
  the derived `bind_profile` (`local` when nobody chose), because the two fail closed in opposite
  directions. The standing gates are `tests/unit/test_serving_path_exposure.py` (which boots the
  app with the variable ABSENT and an S2S token present, and asserts every route refuses a LAN
  peer), `tests/unit/test_profile_single_source.py` and `tests/unit/test_three_state_env_reads.py`,
  the last of which fails the build for ANY two-state `os.environ.get` read in `src/`, `scripts/`
  or `eval/`, not only for the profile variable.
- **The exposure guard's posture comes from the IDENTITY BINDING, never from a credential.** An
  end-user route is authenticated when the bound identity adapter can produce a verified principal
  without trusting a client-written header, and the adapter declares that on itself
  (`ports/identity.py`: `VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`; silence and typos read
  as client-asserted). `<PREFIX>_S2S_TOKEN` authenticates a calling SERVICE and NO end user, so it
  takes no part: while it did, SETTING it disabled the guard for the end-user routes it was
  protecting, and a LAN peer with no credential got `/v1/personas` in full and a real
  `/v1/triage` decision. `tests/unit/test_end_user_auth_posture.py` expands the guard's argument
  through the module constants it names and fails the build if a credential reappears at any
  depth; `scripts/prove-exposure-matrix.sh` drives the whole matrix (profile x token x persona
  header) against a real socket from this machine's LAN address, and `verify-render.sh` runs it.
- **The `VERIFIED` declaration must be EARNED, and the adapter that makes it must be TESTED.**
  `adapters/gcp/identity.py` is the only adapter whose declaration stands the exposure guard down,
  and it shipped calling `id_token.verify_token(assertion, Request())` with no `audience=`, no
  `certs_url=` and no `try`, under a `# pragma: no cover - needs live GCP`. google-auth documents
  `audience=None` as "the audience is not verified", so any Google-signed OIDC token from any
  project became a verified principal; `certs_url` defaulted to the OAuth2 federated set rather
  than IAP's; and `MalformedError` (a `ValueError`, not an `IdentityError`) escaped the route as a
  bare 500. The audience is CONFIGURATION (`iap_audience` in `config/settings.yaml`, three-state,
  unset or emptied refuses), the key set is pinned, both the call and the lazy import are wrapped,
  and the issuer is checked here because `verify_token` does not check it. Two suites hold it:
  `tests/unit/test_iap_identity.py` (SDK-free, in every rendered `make gate`) and
  `tests/unit/test_iap_crypto_matrix.py` (the REAL verifier over a locally minted key, offline).
  The second cannot run in the SDK-free gate, so `verify-render.sh` installs google-auth and
  asserts it PASSED rather than skipped, and the shared workflow's `iap-verifier` job does the
  same against the runtime lockfile. A skip there is a failure, not a tick.
- **The interactive docs follow the exposure profile.** `/docs`, `/redoc` and `/openapi.json` are
  registered only under a deliberate `local`; under `gcp` an uncredentialed LAN peer was getting
  the whole route inventory and every schema from a process bound to `0.0.0.0`. The routes are
  ABSENT rather than guarded, because the guard is exactly what has stood down there.
- **A gate test must never PIN the defect.** `test_an_absent_or_blank_variable_is_the_offline_default`
  asserted that unset and set-and-empty both equalled `LOCAL_PROFILE`, so a repo owner who fixed
  the resolver broke a green test. When a fail-open is removed, find the test that was asserting
  it and rewrite it into the regression guard for the fix.
- **Observability is two ports, and neither Protocol lives here.** `tracer` and `evaluation` are
  imported from `hex-service-kit` and `agent-eval-kit` and re-exported by `ports/observability.py`,
  exactly as `IdentityPort` is. Sixteen repos had each hand-copied these and they had already
  drifted: one lost the evaluation port entirely, two lost its `gate` method, one changed a return
  type. Do not redeclare them here to "make the file self-contained"; that is the defect.
- **The tracer is the one seam that neither refuses on-prem nor refuses offline.** Every other
  placeholder raises, because a control that silently does nothing has been removed. Tracing is a
  diagnostic: an exporter fault must never become a request fault, and a fatal on-prem tracer would
  oblige every operator to stand up a tracing stack before the service would answer. The exemption
  is DECLARED (`demo.EXIT_ABSENT`, an empty `managed_refusal` in `canonical.py`) and asserted in
  both directions, so a tracer that starts raising fails the portability tour and the parity suite.
- **A port must be impossible to half-register.** A port lives in five places: `PORT_PROTOCOLS`,
  `config.DEFAULT_BINDINGS`, the `Container` accessor, `config/settings.yaml` and the canonical
  call table in `tests/contract/canonical.py`. `tests/contract/test_port_parity.py` asserts set
  equality across all five, because four out of five is a port with zero enforcement and a green
  build. When you add a port to the template, add it to all five and to the touch list in the
  rendered `CONTRIBUTING.md`.
- **Import order must not depend on the package name.** `tests` is configured as
  `known-local-folder` in the rendered `pyproject.toml`, so `import <package>` and `import tests`
  never share an isort section. Without that, the correct import order would depend on how the
  rendered package name sorts against the word "tests", and some renders would fail `ruff check`
  while the defaults passed. Same class of trap as the line-length one above.
- **A rendered repo must be DEMOABLE on the first try, not merely green.** `scripts/` renders a
  full demo surface (scripted arc, static renderer, live server, presenter walkthrough that
  doubles as the headless self-test, executable portability claim, documentation checker), all
  stdlib-only and offline. `verify-render.sh` runs it; a rendered repo that passes the gate but
  cannot be demoed has not reached parity, because 31 repos start from that output.
- **A demo step exists in exactly two places and they are held equal.** `demo.STEPS` and
  `walkthrough.CHECKS`; `tests/unit/test_demo_surface.py` asserts set equality, so a narrated
  claim nobody verifies cannot exist. Keep the demo OUT of `make gate`: it has its own required
  workflow, and the gate must stay fast and offline.
- **`ui/` is rendered, and its removal is a supported path.** Most catalog repos have no UI, so
  `make drop-ui` removes the directory, the npm dependabot ecosystem and the ui-gate workflow
  together, and `tests/unit/test_ui_surface.py` fails the gate if the three ever disagree in
  EITHER direction. `verify-render.sh` proves the gate is green both with and without the UI.
- **The UI's security boundary is three plain policy modules behind a typed seam.**
  `ui/lib/env-setting.mjs` (the three-state environment read, the JavaScript twin of the commons'
  `read_env_setting`, and the ONLY module allowed to touch `env[name]`),
  `ui/lib/embed-policy.mjs` (framing, CORS, header stripping) and `ui/lib/identity-policy.mjs`
  (the `UI_PROFILE` read and the persona/assertion decision) hold every decision, in plain
  JavaScript so `npm test` runs them in bare node; `ui/lib/server/identity.ts` is types and
  re-exports only. The browser never asserts an actor, the service credential never leaves the
  server, framing and CORS are per-tenant allowlists that refuse a wildcard, and every variable
  behind them is three-state: unset takes the documented restrictive default, EMPTIED refuses.
  `next.config.mjs` resolves the embedding policy at module scope, so an emptied allowlist is a
  build and boot refusal rather than a surprise on a later request. Changing that is a security
  change, not a refactor.
- **The document CSP is nonce-based, and the route is forced dynamic, and both are required.**
  `script-src 'self'` blocks Next's INLINE hydration bootstrap, so the console renders and
  never becomes interactive. The nonce alone does not fix it: Next can only stamp a nonce onto
  a DYNAMICALLY rendered route, and on a prerendered one `'strict-dynamic'` additionally
  disables the `'self'` fallback, so half the fix blocks more than the defect did. So
  `securityHeaders(env, nonce)` emits the nonce policy, `proxy.ts` sets it on the REQUEST
  `Content-Security-Policy` header (the only name Next reads a nonce from), `app/layout.tsx`
  sets `force-dynamic`, and `assertHydratableCsp` fails the build when they disagree.
  `'unsafe-inline'` is not the fix. This shipped fleet-wide and NOTHING caught it: correct
  headers, clean `tsc`, green policy tests, successful build, correct-looking screenshots.
  The only check that can see it is `ui/scripts/assert-hydratable.mjs`, which starts the built
  server and asserts every script tag in the served document carries the served nonce.
- **The two-state scan covers `ui/` too, in node, because the Python one cannot.**
  `tests/unit/test_three_state_env_reads.py` parses Python with `ast` and never reads a `.mjs`,
  which is how `env.UI_TENANT_ORIGINS || "*"` once survived the whole gate: 247 Python tests, 19
  node tests, `tsc` clean. `ui/tests/three-state-env-reads.test.mjs` scans every shipped
  `.mjs`/`.js`/`.ts`/`.tsx` under `ui/` with the same rule and the same two escapes (an
  exact-match comparison against a literal, or a variable listed in
  `TWO_STATE_READS_WITH_A_REASON` with a written reason), carries the exact mutant as a
  self-proof, and runs in `npm test`, in the ui-gate workflow and in `verify-render.sh`. The
  rendered `tests/unit/test_ui_surface.py` fails the offline gate if it is deleted or unwired.
- **The rendered test tree is split, and the split is enforced.** `tests/{unit,contract,
  integration,fixtures}` with `__init__.py` and a shared `conftest.py`; integration modules carry
  a module-scope mark so the offline gate deselects them, and `tests/unit/test_test_layout.py`
  fails the build if one does not, or if a test is dropped back into `tests/` root.
