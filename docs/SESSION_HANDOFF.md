# Session Handoff — APIM Gateway Migration Debugging

> Written for a fresh model/session to pick up where this one left off. Full technical detail already lives in [`LEARNING.md` Phase 9](../LEARNING.md#-phase-9-apim-gateway-migration--tls-ingress) and [`README.md`](../README.md) — this doc is the "what happened and what's left" summary, not a duplicate of either.

## What this project is

A local Docker lab for WSO2 API Manager (APIM) + Identity Server (IS), backed by Postgres. A Next.js frontend logs users in via GitHub (federated through IS), then calls a FastAPI backend for both auth endpoints and business APIs — **all traffic routed through the APIM gateway**, not hitting the backend directly. See `README.md` for the full stack and `docker-compose.yml` for wiring.

## Git state as of this handoff

- ~~Branch: `feature/apim-gateway-migration`, pushed to `origin`. **Not yet merged to `main`.**~~
  **Update (Jul 2026):** merged to `main` as PR #1. Later sessions added Microsoft
  Entra ID as a second federated IdP (see `LEARNING.md` Phase 10) — this doc is
  kept as the historical record of the gateway-migration debugging itself.
- Last two commits on the migration branch:
  1. `Complete APIM gateway migration and fix federated auth claims` — nginx TLS ingress, `/auth/me` claim-source fix, frontend keeps login-time user data instead of re-deriving it
  2. `Persist regenerated IS/APIM certs via volume mount, document Phase 9` — makes the cert fix survive `docker compose down`, adds the Phase 9 journal entry

## What got fixed this session (in the order the bugs actually surfaced)

The end-to-end login → dashboard flow was broken by a *chain* of independent issues, each masking the next once fixed. In order encountered:

1. **Postgres shutdown cascaded into IS/APIM DB errors** — both products share Postgres for everything; killing it broke registry/tenant/synapse state in both.
2. **Docker Desktop/WSL2 stuck port-forwarder state** — after an unclean container death, IS/APIM got stuck `Exited` with `address already in use` on every restart attempt, even though nothing showed bound to that port in `docker ps`. Fixed by `wsl --shutdown` + reopening Docker Desktop.
3. **Expired WSO2 demo cert** — the bundled `wso2carbon.jks` cert shipped already expired (`NotAfter: Jan 2025`), breaking IS↔APIM JWKS trust (`PKIX path building failed` → generic `900900` errors at the gateway). Regenerated via `keytool`, re-trusted on **both** APIM's and IS's own truststores (IS makes internal self-referencing calls too).
4. **Dev Portal subscription missing** — a valid token isn't enough to call a secured API; the token's `client_id` also needs an active Dev Portal Application subscription to `LabAPI` (`900908` error). Mapped the existing IS Service Provider's client ID into a Dev Portal Application, subscribed it under Production keys.
5. **`/auth/me` used the wrong auth mechanism** — it expected the raw `Authorization` header and did IS introspection, but APIM strips `Authorization` on secured routes (only forwards `X-JWT-Assertion`). Rewrote it to read `X-JWT-Assertion` claims instead, same pattern as `/secure-resource`/`/reports`.
6. **Claim key names were guessed wrong initially** — assumed `http://wso2.org/claims/username` URIs; actual claims (with `apim.jwt.convert_dialect = true`) are flat `name`/`email` keys. Fixed after capturing a real payload.
7. **Federated user claims still came back empty for `/auth/me` in some cases** — because APIM's claim injection depends on IS's local user-store lookup, unreliable for federated users. Real fix: frontend now keeps the `id_token`-derived `{sub, name, email}` from `/auth/exchange` (captured once at login) instead of re-deriving display data from `/auth/me` on every page load. `/auth/me` is now a pure liveness check.
8. **The cert fix didn't survive `docker compose down`** — it only ever existed inside the (ephemeral) container filesystem. Fixed by exporting the regenerated keystores to `config/is/` and `config/apim/` and volume-mounting them in `docker-compose.yml`, same pattern as `deployment.toml`.
9. **A Docker image-pull DNS failure** (`registry-1.docker.io: no such host`) turned out to be an unrelated transient Docker Desktop/WSL2 networking hiccup, resolved by retry/Docker Desktop restart — not a repo issue.

## Known, accepted gaps (not bugs, but worth knowing)

- **`/auth/logout` doesn't actually revoke tokens anymore.** It still expects the raw `Authorization` header (same problem `/auth/me` had, not yet fixed here) — APIM strips it on the secured route, so the revoke call always 401s server-side. Currently masked by the frontend's `.catch(() => {})`; the session still clears client-side, so it *looks* like logout works, but the IS token stays valid until natural expiry. **This is item #1 in the pending cleanup plan below.**

## Pending work — ✅ ALL EXECUTED (cleanup pass complete)

All nine items from the review were applied in a follow-up session:

1. ✅ `/auth/logout` — removed entirely (backend endpoint + frontend fetch). Revocation is *impossible* behind the secured gateway route (raw token never arrives), so logout is now honestly client-side: clear `sessionStorage`, token expires at natural TTL. Code comments at both sites explain why.
2. ✅ `NEXT_PUBLIC_BACKEND_URL` — single source of truth: Dockerfile `ARG` (with default), overridable via compose `build.args`. Dead runtime `environment:` entries removed from compose.
3. ✅ `_introspect()` and `_get_bearer()` deleted (both dead after the logout removal).
4. ✅ `NEXT_PUBLIC_APIM_GATEWAY_URL` removed from Dockerfile and docker-compose.yml. **⚠️ One manual step remains:** `frontend/.env.local.example` still references it — that file is blocked by tool permission settings (`.env*` deny pattern). Replacement content is in the session notes; update it by hand.
5. ✅ `main.py` docstring rewritten — documents the header-stripping rule ("THE ONE RULE") and the `convert_dialect` claim-shape dependency.
6. ✅ Python env defaults updated to `https://portal.local.test[/callback]`.
7. ✅ `config/apim/deployment.toml.bak` deleted.
8. ✅ `nginx.conf` `Host` header choice documented in a comment (deliberate, for APIM dispatch).
9. ✅ Standardized on compose service name `wso2is` (docker-compose backend env + `main.py` default).

Also added: `docs/ARCHITECTURE.md` — full runtime lifecycle (login a→z, per-request gateway flow, failure-mode table, config→behavior map, trust chain).

## Also worth doing soon

- ~~Open a PR to merge `feature/apim-gateway-migration` → `main`~~ ✅ merged (PR #1).
- A fresh-clone / `docker compose down -v` dry run to confirm the README's Quick Start actually works from zero, not just on a machine with leftover state.

## Where to look for more detail

- `LEARNING.md` — full phase-by-phase journal, Phase 9 covers this session's architecture and includes a copy-pasteable cert-recovery runbook.
- `README.md` — Quick Start (a-z setup) and a Troubleshooting table mapping error codes (`900900`, `900908`, etc.) to fixes.
- `docs/tasks/apim-gateway-migration.md` — original task checklist for the gateway migration itself (T1–T9, all done).
