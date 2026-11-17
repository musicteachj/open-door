# 0020. One production image serves the API and the web app from one origin, under a nonce-based CSP

Status: Accepted · Date: 2026-11-05

## Context

Nothing builds a production image yet, and nothing serves the built web app: in development, Vite
serves it and forwards `/api` to uvicorn. The app already assumes one origin. Its session cookies
are `__Host-` cookies, the CSRF check is double-submit, the same-origin middleware compares
`Origin` with `APP_ORIGIN`, and there is deliberately no CORS.

A strict Content Security Policy has one obstacle. Radix's scroll lock (through
`react-style-singleton` and `get-nonce`) and Radix Select's viewport insert `<style>` elements at
runtime, which a policy without `'unsafe-inline'` blocks unless they carry a nonce. The app has no
inline scripts.

## Decision

- **One multi-stage image:** Node builds the web app; the final stage is a slim Python image that
  runs uvicorn as a non-root user and serves both the API (`/api/`) and the built app (everything
  else). Hashed assets are cached for a year; `index.html` is never cached.
- **`index.html` is rendered per response** with a fresh nonce, in the CSP header and in a
  `<meta name="csp-nonce">` tag that the app reads before rendering and hands to `get-nonce` and to
  Radix Select. The Turnstile site key travels the same way, so one image serves any environment.
- **The policy:** scripts from `'self'` and Cloudflare's challenge host only, no inline script and
  no `eval`; styles from `'self'` and the nonce; frames from Cloudflare's challenge host only;
  `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`, `form-action 'self'`, and
  `connect-src 'self'`. HSTS, `nosniff`, `Referrer-Policy: no-referrer`, a closed
  `Permissions-Policy`, and `Cross-Origin-Opener-Policy: same-origin` go on every response.
- **CI builds the image** and runs the browser suite and the proxy check against it (a test variant
  carries the component gallery), and fails on any CSP violation.

## Rejected alternatives

- **`style-src 'unsafe-inline'`:** simpler, and inline styles are a smaller risk than inline
  scripts, but it gives up part of "strict" for one small piece of code that the nonce removes.
- **The web app on S3 and CloudFront, the API on Fargate:** two origins (or a CloudFront path rule
  in front of both), a second deploy path, and the CSP set in two places. It is worth it at scale,
  not for a demo. Phase 9 can still put CloudFront in front of this one image.
- **An nginx container beside the API:** a second process to configure and keep patched, when the
  load balancer already does what nginx would (TLS, buffering off for the stream).
- **The nonce in a build-time variable:** a nonce must be new for every response, or it protects
  nothing.

## Consequences

- The API gains a small static-file layer and an `index.html` renderer, tested like any route.
- `make dev` is unchanged and runs without a CSP; the browser suite against the image is where the
  policy is proven, so a new library that injects styles fails CI there.
- The proxy check starts the container, so the graceful-shutdown run exercises the real
  entrypoint.

## Amendment (2026-11-10): `Referrer-Policy: same-origin`

Phase 8's Stage 2 review found that `no-referrer` makes a browser send `Origin: null` on the app's
own writes (the Fetch standard ties the `Origin` of a non-`GET` request to the referrer policy).
The same-origin check accepts a write by `Sec-Fetch-Site: same-origin`, or, from a browser that
doesn't send Fetch Metadata (Safari before 16.4, or behind a proxy that strips it), by an `Origin`
equal to the app's. Under `no-referrer` that second path would refuse every write. The policy is
`same-origin` instead: the full referrer on the app's own requests, and none to any other site,
which keeps the decision's intent.
