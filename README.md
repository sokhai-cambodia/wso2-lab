# wso2-lab

A local Docker lab for WSO2 API Manager (APIM) and Identity Server (IS), backed by PostgreSQL. Used to learn API gateway architecture, identity federation, and gateway security hands-on.

See [LEARNING.md](LEARNING.md) for the full phase-by-phase journal.

## Stack

| Service | Image | Host port | Role |
|---------|-------|-----------|------|
| nginx | `nginx` | `443` | TLS ingress for `*.local.test` — the only thing the browser talks to |
| Next.js frontend | built from `frontend/` | — (behind nginx) | Portal UI: login buttons, callback, dashboard |
| WSO2 APIM | `wso2/wso2am:4.3.0` | `9443`, `8243`, `8280` | API gateway: token validation, subscriptions, JWT injection |
| WSO2 IS | `wso2/wso2is:7.0.0` | `9444` | OIDC broker (GitHub + Microsoft federation), APIM's Key Manager |
| FastAPI backend | built from `backend/` | `8000` | Auth flow + demo API endpoints, called only via the gateway |
| PostgreSQL | `postgres:15` | `5433` | `shared_db`, `identity_db`, `apim_db` for both WSO2 products |
| RabbitMQ | `rabbitmq:3-management` | `5672`, `15672` | Async event queue (Phase 5 experiments) |

## Project Layout

```
wso2-lab/
├── README.md            ← this file
├── LEARNING.md          ← detailed phase-by-phase journal
├── .env.example         ← every overridable variable with its default (.env is optional)
├── docker-compose.yml
├── backend/             ← FastAPI service (auth flow + demo API endpoints)
├── frontend/            ← Next.js portal (login, callback, dashboard)
├── docs/                ← ARCHITECTURE.md (runtime flows) + session notes
├── libs/                ← JDBC drivers mounted into containers
├── config/              ← deployment.toml + keystores per service (is/, apim/)
├── scripts/             ← PostgreSQL schemas + first-boot seed dumps (scripts/init/)
├── nginx/nginx.conf     ← TLS termination + reverse proxy for *.local.test
└── certs/               ← mkcert output (committed on purpose — lab-only)
```

All frontend traffic (auth **and** business API calls) goes through the APIM gateway — there's no direct browser→backend path. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full request lifecycle and [LEARNING.md Phase 9](LEARNING.md#-phase-9-apim-gateway-migration--tls-ingress) for how it got this way.

> Note: logout is client-side only (session cleared in the browser; the IS token expires at its ~1h TTL). Server-side revocation is impossible behind the gateway — see "The one rule" in ARCHITECTURE.md.

## Quick Start (clone → run → test)

Everything is pre-baked: the repo commits the TLS certs, the WSO2 keystores, *and*
seed dumps of the fully configured databases (IS Service Provider + GitHub
connection, APIM Key Manager, LabAPI published + subscribed). On first boot with
an empty volume, Postgres auto-creates and seeds all three databases — **no manual
IS/APIM console setup needed**, except pasting your own IdP OAuth credentials once
(steps 3–4 — the secrets a public repo can't ship; GitHub required, Microsoft optional).

1. Add hosts entries (the one unavoidable host-machine step):
   ```
   127.0.0.1  portal.local.test
   127.0.0.1  gateway.local.test
   127.0.0.1  is.local.test
   ```
   Linux/WSL: append to `/etc/hosts` with sudo. Windows: add to
   `C:\Windows\System32\drivers\etc\hosts` as Administrator.

2. Start everything:
   ```bash
   docker compose up -d
   ```
   First boot takes ~3–4 min: postgres seeds the databases, then IS/APIM start in
   parallel (~2 min each), then backend → frontend → nginx. Watch with:
   ```bash
   docker compose ps   # wait for wso2is-local and wso2apim-local to show (healthy)
   ```

3. Connect your own GitHub OAuth app (one-time, ~3 min — the seed ships with the
   secret scrubbed, since GitHub auto-revokes OAuth secrets found in public repos):
   1. GitHub → Settings → Developer settings → OAuth Apps → **New OAuth App**
      - Homepage URL: `https://localhost:9444`
      - Authorization callback URL: `https://localhost:9444/commonauth`
   2. IS Console (`https://localhost:9444/console`, `admin`/`admin`) →
      **Connections** → **github** → paste your Client ID and Client Secret → save.

4. *(Optional)* Connect **Login with Microsoft** (~5 min — the connection ships in
   the seed dumps with its secret scrubbed, same as GitHub; the GitHub path works
   without this step):
   1. [Azure portal](https://portal.azure.com) → **Microsoft Entra ID** → **App
      registrations** → **New registration**: account type *"Any org directory +
      personal Microsoft accounts"*, platform **Web**, redirect URI
      `https://localhost:9444/commonauth`. Copy the **Application (client) ID**,
      then **Certificates & secrets** → new secret → copy its **Value** (shown once).
   2. IS Console → **Connections** → **microsoft login** → paste your Client ID
      and Client Secret → save. (The connection is a Standard-Based OIDC IdP
      against `login.microsoftonline.com/common`, JIT provisioning enabled, and
      already wired into the app's Login Flow — only the credentials are missing.)

5. *(Optional, kills browser warnings)* Trust the lab CA: import `certs/rootCA.pem`
   into your OS/browser trust store. Skipping this just means clicking through a
   self-signed-cert warning — everything still works.

6. Open `https://portal.local.test` → **Login with GitHub** (or **Microsoft**, if
   you did step 4) → dashboard → hit the three API test buttons. Consoles (if you
   want to poke around): IS at `https://localhost:9444/console`, APIM
   Publisher/DevPortal at `https://localhost:9443/publisher` / `/devportal` —
   all `admin`/`admin`.

7. Tear down:
   ```bash
   docker compose down        # keeps DB volume — instant restart later
   docker compose down -v     # wipes the volume — next `up` re-seeds from scratch
   ```

> **How the zero-config works:** all IS/APIM configuration lives in Postgres
> (Phase 4), secrets in those DBs are encrypted against the committed keystores
> (Phase 9), and `scripts/init/00-init.sh` seeds the databases from
> `scripts/init/seed/*.sql` on first boot. Everything committed here is
> lab-only by design — do not reuse this pattern with real credentials.

<details>
<summary><b>Rebuilding from scratch (no seed dumps — vanilla WSO2)</b></summary>

If the seed dumps are absent, `00-init.sh` falls back to loading the vanilla WSO2
schemas (`scripts/shared.sql`, `identity_correct.sql`, `consent.sql`, `apim.sql`).
The stack boots clean but unconfigured — you then need the manual console setup:
IS Service Provider + GitHub connection with JIT ([Phase 3](LEARNING.md#-phase-3-identity-brokerage--federation)),
IS as Key Manager ([Phase 7](LEARNING.md#-phase-7-production-auth--is-as-external-key-manager)),
LabAPI published and a Dev Portal Application subscribed to it
([Phase 9](LEARNING.md#-phase-9-apim-gateway-migration--tls-ingress) — without the
subscription every gateway call returns `900908`). To regenerate certs per-machine
instead of using the committed ones: `mkcert -install && mkcert -cert-file
certs/local.pem -key-file certs/local-key.pem portal.local.test
gateway.local.test is.local.test && cp "$(mkcert -CAROOT)/rootCA.pem" certs/`.

To refresh the seed dumps after changing WSO2 config (run against a working stack):
```bash
for db in shared_db identity_db apim_db; do
  docker exec wso2-postgres pg_dump -U wso2 -d $db --no-owner --clean --if-exists -f /tmp/$db.sql
  docker cp wso2-postgres:/tmp/$db.sql scripts/init/seed/$db.sql
done
```
</details>

## Configuration

`.env` is **optional** — every value in `docker-compose.yml` has a default that
matches the seeded lab. To override anything (IdP connection names, ports, JVM
heap, URLs), copy `.env.example` to `.env`, edit, and `docker compose up -d`.
The one exception: `NEXT_PUBLIC_BACKEND_URL` is baked into the frontend bundle
at **build** time, so changing it needs `docker compose build frontend` first.

## Standalone mode (external IdP, no gateway)

An alternative lightweight setup: only **frontend + backend** run locally
(`http://localhost:3000` / `:8000`), and identity comes from **any external
WSO2 IS** — [Asgardeo](https://console.asgardeo.io) (WSO2's SaaS IS), another
cloud instance, or a dev/UAT on-prem IS. With no gateway in front, the backend
verifies the raw Bearer JWT itself (`GATEWAY_MODE=false`) against the IdP's JWKS.

1. On the IdP, register an OIDC web application (in Asgardeo:
   **Applications → New Application → Traditional Web Application**; on-prem IS:
   a Service Provider / Standard-Based App):
   - Authorized redirect URL: `http://localhost:3000/callback`
   - Allowed origin: `http://localhost:3000`
   - **Access token type: JWT** (required — the backend can't self-validate
     opaque tokens; in Asgardeo this is on the app's Protocol tab)
   - Request the **Email** + **Profile** user attributes
2. Add Microsoft login on the IdP: [Azure portal](https://portal.azure.com) →
   app registration as in step 4 above, but with redirect URI
   `<IdP base URL>/commonauth` (Asgardeo: `https://api.asgardeo.io/t/<org>/commonauth`).
   Then on the IdP: **Connections → New Connection → Microsoft** → paste the
   Azure Client ID/Secret → add it to the application's **Login Flow**.
3. Set in `.env` (see `.env.example`):
   ```
   IDP_BASE_URL=https://api.asgardeo.io/t/<org>     # or https://is-dev.example.com
   IDP_CLIENT_ID=...
   IDP_CLIENT_SECRET=...
   ```
4. Run it (stop the full lab first — it also binds ports 3000/8000):
   ```bash
   docker compose -f docker-compose.standalone.yml -p wso2-lab-standalone up -d --build
   ```
5. Open `http://localhost:3000` → **Login with Microsoft**. (The GitHub button
   lands on the IdP's own login page in this mode unless you configure a GitHub
   connection there and set `IDP_GITHUB_NAME`.)

Notes: the *Reports* card 403s in this mode unless the IdP issues a
`read:reports` scope — that's the backend enforcing scope itself, which APIM
did for you in gateway mode. Tear down with
`docker compose -p wso2-lab-standalone down`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `900900 Unclassified Authentication Failure`, or APIM log shows `PKIX path building failed` | IS↔APIM certificate trust expired/broken | Regenerate and re-exchange certs — runbook in [LEARNING.md Phase 9](LEARNING.md#runbook-recovering-from-an-expired-isapim-trust-chain) |
| `900908 API Subscription validation failed` | Token's client isn't subscribed to the API being called | Dev Portal → Applications → your app → Subscriptions → subscribe to `LabAPI` |
| Microsoft button redirects to IS's own login page instead of Microsoft | `fidp` value doesn't match any IS connection name | The IS connection must be named exactly `Microsoft`, or set `MICROSOFT_IDP_NAME` in `.env` and `docker compose up -d backend` |
| Microsoft login fails at IS with an id_token/issuer validation error | `common` tenant endpoints + strict issuer check, or WSL2 clock drift | Use your tenant ID (or `consumers`) instead of `common` in all connection URLs; for clock drift, `wsl --shutdown` |
| IS/APIM stuck `Exited` with `address already in use` on restart, even though `docker ps` shows nothing on that port | Docker Desktop/WSL2 leftover port-forwarder state after an unclean shutdown | `wsl --shutdown` (elevated PowerShell) → reopen Docker Desktop → `docker compose up -d` |
| `invalid_client` / `application.not.found` at `/oauth2/authorize` | The OAuth app behind that client ID doesn't exist in IS (e.g. `postgres_data` was reset) | Recreate the Service Provider in IS Console, update `WSO2_IS_CLIENT_ID`/`SECRET` in `.env` |
| Logged in, but `/auth/me` shows the right `sub` with no name/email | Federated (GitHub) user claims come from `X-JWT-Assertion`, whose shape depends on `apim.jwt.convert_dialect` | See [Phase 9, Milestone 3](LEARNING.md#milestone-3-claim-dialect-for-x-jwt-assertion) |
