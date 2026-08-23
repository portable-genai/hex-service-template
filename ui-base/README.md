# ui-base (shared Next.js micro-frontend skeleton)

A minimal starting point for a repo's embeddable `ui/`, aligned to the catalog's clean framework
set (`next` 16.x / `react` 19.x, the versions that clear the high-severity advisories the older
`14.2.35` pin carried). Copy it into a new repo's `ui/` and wire it to that repo's API.

**This is a skeleton, not a gate-verified package.** The Python offline gate does not run a JS
toolchain, so these files are provided as a reference App Router base (a security-header
middleware and the local persona-picker pattern), not something this template renders and tests.
Run `npm install && npm run build` in the target repo after copying.

## What it carries
- `package.json` pinned to the catalog's clean `next` / `react` set.
- `middleware.ts`: the CSP `frame-ancestors` + transport + content-type header baseline at the
  Next.js document layer (mirrors the API-side `add_security_headers` from `hex-service-kit`).
- `app/`: an App Router shell with the dev persona picker (the `X-Dev-Persona` header the local
  `IdentityPort` reads).
- `app/favicon.ico`: the catalog mark, carried by App Router's file convention rather than a
  `<link>` tag, so a copied UI has a tab icon without editing `layout.tsx`. Regenerate from
  `org-metadata/images/favicon/` if the mark changes; it is a build input, not a stray binary.

Consolidating the UI base means a framework bump is one version change here rather than a blind
upgrade in every UI-bearing repo.
