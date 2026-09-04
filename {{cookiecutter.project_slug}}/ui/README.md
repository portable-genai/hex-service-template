# ui: the embeddable micro-frontend

A Next.js App Router console for {{ cookiecutter.friendly_name }}.
It runs standalone for a demo and embeds into a client's existing web application as an iframe,
with the same security posture either way.

It ships with the repo on purpose. A UI-bearing repo that had to hand-build this would rebuild
the identity boundary each time, and each rebuild is a chance to get it wrong. **If this repo
genuinely has no user-facing surface, delete the UI rather than leaving it half-wired:**

```bash
make drop-ui     # removes ui/, its dependabot ecosystem and its CI job, in one step
```

Deleting by hand is not enough: `tests/unit/test_ui_surface.py` fails the offline gate if `ui/`
is present without its npm watch and CI job, and equally if those are left behind after `ui/` is
gone. The consistency is checked in both directions, so neither half can rot.

## Running it

```bash
cd ui
npm ci                 # exact versions from the committed package-lock.json
npm run lint           # tsc --noEmit
npm test               # the embedding and identity policy tests (plain node, no browser)
npm run build          # production build; refuses if the CSP and the render mode disagree
npm run assert-hydratable   # serves the built app and proves the page can hydrate
npm run build          # production build
npm run dev            # http://localhost:3000, proxying to the service on 127.0.0.1:8080
```

Start the service first (`make run-api` in the repo root). The UI talks only to its own origin.

## The identity contract (the part that must not be edited casually)

**The client never asserts who it is.** Every actor, principal, tenant, role, ACL and
authorization header arriving from the browser is discarded in `lib/embed-policy.mjs`
(`stripClientIdentity`) before the request is forwarded. Identity is then resolved server-side in
`lib/identity-policy.mjs` (the decisions, covered by `npm test`) behind the typed seam
`lib/server/identity.ts`, and the resolved headers are added afterwards, so a stripped header
cannot be reintroduced by the same request.

**`UI_PROFILE` has three states, and there is no default.** Absence is not consent: a deployment
that lost the variable from its environment must not start seeding dev personas, which is the
same rule the service's own seeded-persona adapter enforces.

| `UI_PROFILE` | Who the user is | Notes |
|---|---|---|
| unset | nobody | REFUSED with 401. No persona is seeded, because nobody chose the profile that seeds them. |
| set to an empty value | nobody | REFUSED. An emptied variable is an expressed intent that names no profile, so it never inherits the unset behaviour. |
| `local` | a seeded dev persona | Chosen deliberately. No IdP, no AD, no LDAP. The picker is a hint; the server validates it against its own list, so a hand-crafted request cannot invent a persona or an ACL. |
| `secure` | the platform's signed assertion | This UI must sit behind an identity-aware proxy. The assertion is FORWARDED to the service, which verifies it. The UI never parses it and never trusts a parsed copy. A request with no assertion is refused with 401, never downgraded. |
| `onprem` | the client's own IdP | Deliberately unimplemented: it raises. A silent fallback to dev personas here would turn a misconfigured deployment into an unauthenticated one. |
| anything else, including `Local` | nobody | REFUSED. A mis-capitalised value is a typo, not a synonym, and coercing it would turn the typo into a silent choice. |

The service-to-service credential (`AGENT_S2S_TOKEN`) is read from the SERVER environment inside
the route handler. It is never sent to the browser and never reaches a client bundle. That is the
reason the UI proxies at all instead of calling the service directly.

## Framing and CORS

Both are allowlists, and both refuse a wildcard however it is written (`*`, `'*'`, `null`).

## The script policy, and why the page is rendered dynamically

The document is served with `script-src 'self' 'nonce-<n>' 'strict-dynamic'`, a fresh nonce per
request. This is not decoration, and it is not safely simplified.

Next serves its hydration bootstrap as an INLINE `<script>` carrying the Flight payload. Under a
plain `script-src 'self'` the browser blocks it, `__next_f` never fills, React never attaches, and
what a host application embeds is a static picture of a console: every control visible, none of
them working. This shipped across the whole catalog, and the correct headers, a clean type-check,
green policy tests, a successful build and accurate screenshots were all consistent with it.

Three pieces make it work, and any two of them are worse than none, because `'strict-dynamic'`
disables the `'self'` fallback that was at least loading the chunk scripts:

| Piece | Where | Why it is required |
|---|---|---|
| The nonce in the policy | `lib/embed-policy.mjs` | Allows the inline bootstrap without allowing every inline script |
| The nonce on the REQUEST `Content-Security-Policy` header | `proxy.ts` | The only header name Next reads a nonce from; a custom name is ignored |
| `export const dynamic = "force-dynamic"` | `app/layout.tsx` | Next can only stamp a nonce onto a dynamically rendered route; a prerendered page was built before the nonce existed |

`'unsafe-inline'` would also hydrate, and would also let an injected inline script run, which is
the whole thing the policy exists to prevent. It is not an acceptable substitute.

If you embed this console under your own reverse proxy, do not re-emit a
`Content-Security-Policy` for the document. Two policies are intersected by the browser and the
stricter one wins, so a host-level `script-src 'self'` silently switches the console back off.

`npm run assert-hydratable` is the check: it serves the production build and asserts every script
tag in the served document carries the served nonce. Run it after any change to the policy, the
proxy or the layout.

## Every variable, in three states

**Unset, set-and-empty and set-and-valid are three states, not two.** A variable an operator
deliberately empties has expressed an intent, and it never inherits the unset default. This
mattered here: `frameAncestors` used to answer `'self'` for unset, `""`, `"   "` and `","`
alike, byte for byte, so a deliberate lockdown could not be told apart from a deployment that
lost the variable.

| Variable | Unset | Set and empty | Set to a value |
|---|---|---|---|
| `UI_FRAME_ANCESTORS` | `'self'`: framed by nobody but itself | REFUSES at build and boot | the named parent origins, or `'none'` to refuse framing outright |
| `UI_TENANT_ORIGINS` | empty allowlist, which denies | REFUSES at build and boot | the origins allowed to call the API route cross-origin |
| `UI_PROFILE` | REFUSES: nobody chose a posture | REFUSES | `local`, `secure` or `onprem`, honoured exactly |
| `AGENT_API_URL` | `http://127.0.0.1:8080` | REFUSES: an empty string is not a URL | the address of the service this UI fronts |
| `AGENT_S2S_TOKEN` | no `Authorization` header | no `Authorization` header, deliberately | presented as `Authorization: Bearer` |

A value that is present but names nothing usable refuses too: `UI_FRAME_ANCESTORS=","` and
`UI_FRAME_ANCESTORS=*` are refused rather than quietly downgraded to the shipped default.

`AGENT_S2S_TOKEN` is the one deliberate two-state read, and it follows
`hex_service_kit.s2s.client_headers`. This is the CALLING side: omitting an outbound credential
grants nobody anything, because the receiver decides, and the service this proxy calls refuses an
emptied secret itself. Raising here would turn a receiver-enforced 401 into a caller crash and
move the decision to the end of the call with no authority over it. The exemption is written down
in `tests/three-state-env-reads.test.mjs`, which fails the build on every other two-state read in
this directory.

The refusals for the two allowlists run from `next.config.mjs`, which `next build` and
`next start` both evaluate, so a UI whose allowlist rendered empty never comes up at all. A
refusal at boot is the one outcome a two-state read cannot imitate.

`next.config.mjs` also sets `agentRules: false`. Left at its default, `next dev` detects an AI
coding agent and writes `AGENTS.md` and `CLAUDE.md` into this directory. This repo's working
agreement is the `AGENTS.md` at its root and there is no tool-specific alias of it, so a second
one here is a second agreement to keep in step; the generated prose also carries an em-dash,
which `make docs-check` fails on. If either file ever turns up in `ui/` anyway, the offline gate
fails on it: the flag has stopped working, which is a template fix rather than a repo one.

`proxy.ts` applies the header baseline to every response, including the error ones, from the same
policy module the API route uses for CORS. One policy, three consumers: a header set in two places
is a header that disagrees with itself.

`X-Frame-Options` is sent ONLY for the two policies it can express: `SAMEORIGIN` for `'self'` and
`DENY` for `'none'`. A named allowlist gets none, because the header has no allowlist form and
sending one alongside a real `frame-ancestors` list would contradict it in older agents.

## Embedding it in a client application

1. Register the parent origin: `UI_FRAME_ANCESTORS=https://portal.client.example`.
2. Register the same origin for data calls if the host page calls the API route directly:
   `UI_TENANT_ORIGINS=https://portal.client.example`.
3. Put the UI behind the client's identity-aware proxy and set `UI_PROFILE=secure`.
4. Embed: `<iframe src="https://agent.client.example/" title="Agent console"></iframe>`.

The host page passes no identity. That is the design: anything it passed would be a client
assertion, and this UI discards those.

## What lives where

| Path | What it owns |
|---|---|
| `lib/env-setting.mjs` | The three-state environment read, the JavaScript twin of the commons' `read_env_setting`. The only module that touches `env[name]`. |
| `lib/embed-policy.mjs` | Framing, CORS and header-stripping policy. Pure, no framework, covered by `npm test`. |
| `lib/stages.mjs` | Which stage of a multi-step console is in focus, and when the reader has taken one over. Pure, covered by `npm test`. |
| `app/StageStack.tsx` | The stage stack: as each step completes, the ones above collapse to a summary line so the newest content is in view without scrolling. |
| `lib/server/identity.ts` | The only place an actor is decided. Never reads a browser-supplied value except the validated dev persona. |
| `app/api/agent/[...path]/route.ts` | The same-origin reverse proxy: strip, resolve, forward, answer. |
| `proxy.ts` | The document-layer header baseline on every response. |
| `app/page.tsx` | The console itself. It reads the service's agent card for its own title, so no product name is hardcoded here. |
| `tests/` | Node tests for the policy modules, plus the scanner that fails the build on a two-state environment read anywhere in `ui/`. No browser engine, so they run anywhere. |

## Showing a long console without making the reader scroll

A console that shows its evidence honestly gets tall: inputs, then the arithmetic over them,
then whatever was generated. By the time the last part arrives, the thing the reader came for
is below the fold, and embedded in a portal, where the host sets the iframe height, it is
further down still.

`app/StageStack.tsx` handles that by collapsing what is ABOVE rather than scrolling to what is
below. Wrap each step in a `<Stage>`, say which ones are `ready`, and the last ready one is
open while the rest close to a one-line summary:

```tsx
const { taken, onTakeOver } = useStageTakeover();
const active = activeStage([
  { id: "inputs", ready: inputs !== null },
  { id: "result", ready: result !== null },
]);

<Stage id="inputs" active={active === "inputs"} taken={taken} onTakeOver={onTakeOver}
       summary={<>Inputs <span>{inputs.rows.length} rows</span></>}>
  <InputsPanel inputs={inputs} />
</Stage>
```

Two rules worth keeping when you use it:

- **Put figures in `summary`, never just a title.** A stage that collapses to its name has
  deleted the evidence it existed to show. `12 positions · 1,200,000 SGD · 2 outside band` is
  the point; `Portfolio` is not.
- **Leave the provenance banner out of it.** It is mounted in `app/layout.tsx` outside
  `children` so no stage can collapse or push it off screen. A provenance strip that scrolled
  out of view is a defect this fleet has already shipped once, in eight consoles at the same
  time.

Scrolling is deliberately not used: `scrollIntoView` on a page that is still growing lands
wherever the layout happened to be when it fired, and it takes the scroll position away from
the reader, who then cannot tell whether they moved or the page did.

## Bounds of this UI

It is a working console and a correct security boundary, not a finished product surface. It does
not carry this vertical's real screens, a design system, internationalisation, or accessibility
review. Those are the repo owner's work; the boundary is not.
