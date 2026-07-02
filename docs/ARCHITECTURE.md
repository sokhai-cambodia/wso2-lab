# Architecture — How a Request Actually Flows

> Companion to [`README.md`](../README.md) (setup) and [`LEARNING.md`](../LEARNING.md) (phase journal).
> This doc explains the runtime behavior: what happens between clicking "Login" and seeing data on the dashboard.

## Components

| Component | Hostname (browser) | Docker service | Role |
|---|---|---|---|
| nginx | `*.local.test:443` | `nginx` | TLS termination (mkcert), reverse proxy — the only thing the browser talks to |
| Next.js frontend | `portal.local.test` | `frontend` | UI; stores token + user profile in `sessionStorage` |
| WSO2 APIM 4.3.0 | `gateway.local.test` | `wso2apim` | Gateway: token validation, subscription check, JWT injection |
| WSO2 IS 7.0.0 | `is.local.test` / `localhost:9444` | `wso2is` | OIDC broker (GitHub federation), APIM's Key Manager |
| FastAPI backend | *none — internal only* | `backend` | Auth flow + resource endpoints; reachable only from APIM |
| PostgreSQL | — | `postgres` | `shared_db`, `identity_db`, `apim_db` — both WSO2 products depend on it |

## The one rule

**APIM consumes the `Authorization` header on secured routes and does not forward it.**
The only caller identity that reaches the backend is `X-JWT-Assertion` — a JWT that APIM signs
*after* it has already validated the real access token against IS. Consequences:

- Backend handlers read claims from `X-JWT-Assertion` and may skip signature verification
  (the gateway is the trust boundary; nothing reaches the backend without passing it).
- Any endpoint that needs the **raw** access token (e.g. IS `/oauth2/revoke`) cannot exist
  behind the gateway. This is why logout is client-side only.

## Login lifecycle (a → z)

```
1. portal.local.test            Browser clicks "Login"
2. GET  /auth/login-url         Backend builds IS authorize URL: PKCE pair generated,
                                state stored server-side, fidp=github skips IS's login page
3. IS → GitHub → IS             User approves on GitHub; IS mints an authorization code,
                                redirects to https://portal.local.test/callback?code=...&state=...
4. POST /auth/exchange          Backend validates state, exchanges code+verifier at IS
                                /oauth2/token → { access_token, id_token }
5. Frontend stores BOTH:        wso2_token  = access_token          (for API calls)
                                wso2_user   = {sub,name,email}      (decoded from id_token)
```

**Why the user profile comes from the `id_token`, not from `/auth/me`:** APIM's injected
claims are looked up in IS's *local user store* at request time — which is empty or partial
for federated GitHub users (unless JIT provisioning is configured just right). The `id_token`
captured once at login reflects what GitHub actually sent. The dashboard displays the stored
profile; `/auth/me` is only a liveness check (its 200/401 matters, its body doesn't).

## API request lifecycle (every dashboard call)

```
Browser ── Authorization: Bearer <access_token> ──► nginx (gateway.local.test, TLS)
  └─► wso2apim:8243
        1. JWT validation      signature checked against IS JWKS
                               (https://wso2is:9444/oauth2/jwks — needs cert trust, see below)
        2. Subscription check  token's client_id must map to a Dev Portal Application
                               with an active subscription to LabAPI → else 900908
        3. JWT injection       [apim.jwt] mints X-JWT-Assertion (claim shape depends on
                               convert_dialect); Authorization header is DROPPED
  └─► backend:8000 (Docker-internal only)
        reads X-JWT-Assertion → responds
```

## Failure modes and where they live

| Error seen by client | Failing step | Root cause |
|---|---|---|
| `900900 Unclassified Authentication Failure` | JWKS fetch | IS↔APIM cert trust broken (expired `wso2carbon` cert) — runbook in LEARNING.md Phase 9 |
| `900908 Resource forbidden / Subscription validation failed` | Subscription check | Token's client has no Dev Portal subscription to the API |
| `404 Not Found` from gateway | API dispatch | No API published at that context (e.g. `/auth` was never created as its own API — everything rides on `/lab/1.0`) |
| `401 Missing X-JWT-Assertion` from backend | Backend | Request bypassed the gateway (only possible from inside the Docker network) |
| `sub` present but `name`/`email` empty in `/auth/me` | Claim injection | Federated user has no local IS user-store record — expected; display data comes from the stored login-time profile instead |

## Configuration → behavior map

| Config | File | Controls |
|---|---|---|
| `[[apim.jwt.issuer]]` + `jwks.url` | `config/apim/deployment.toml` | Which issuer's tokens the gateway accepts and where it fetches keys |
| `[apim.jwt] convert_dialect` | `config/apim/deployment.toml` | Claim key shape in `X-JWT-Assertion`: `true` → flat `name`/`email`; `false` → `http://wso2.org/claims/*` URIs. Backend code must match. |
| `wso2carbon.jks` / `client-truststore.jks` mounts | `docker-compose.yml` | Persist the regenerated (non-expired) certs across `docker compose down` — the stock image cert shipped expired |
| `NEXT_PUBLIC_BACKEND_URL` build arg | `frontend/Dockerfile` + compose `build.args` | Baked into the JS bundle at build time. Changing it requires `docker compose up -d --build frontend`; a runtime env var would be silently ignored. |
| `proxy_set_header Host wso2apim:8243` | `nginx/nginx.conf` | Deliberate — APIM dispatches APIs against its own hostname, not the public one |

## Trust chain summary

```
browser ──trusts──► mkcert root CA ──signs──► *.local.test cert (nginx)
nginx   ──proxy_ssl_verify off────► WSO2 self-signed certs (lab tradeoff)
APIM    ──client-truststore.jks───► IS's wso2carbon cert (regenerated, 10y validity)
IS      ──its own truststore──────► same cert (IS makes self-referencing HTTPS calls)
backend ──verify=False / no-verify─► IS + APIM (lab tradeoff; gateway is the trust boundary)
```
