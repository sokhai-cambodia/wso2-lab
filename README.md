# wso2-lab

A local Docker lab for WSO2 API Manager (APIM) and Identity Server (IS), backed by PostgreSQL. Used to learn API gateway architecture, identity federation, and gateway security hands-on.

See [LEARNING.md](LEARNING.md) for the full phase-by-phase journal.

## Stack

| Service | Image | Port |
|---------|-------|------|
| WSO2 IS | `wso2/wso2is:7.0.0` | `9444` |
| WSO2 APIM | `wso2/wso2am:4.3.0` | `9443`, `8243`, `8280` |
| PostgreSQL | `postgres:15` | `5432` |

## Project Layout

```
wso2-lab/
├── README.md           ← this file
├── LEARNING.md          ← detailed phase-by-phase journal
├── docker-compose.yml
├── libs/                ← JDBC drivers mounted into containers
├── config/              ← deployment.toml per service (is/, apim/)
├── scripts/             ← PostgreSQL schema scripts (shared, identity, consent, apim)
├── nginx/nginx.conf     ← TLS termination + reverse proxy for *.local.test
└── certs/               ← mkcert output (gitignored, regenerate per machine — see step 5)
```

All frontend traffic (auth **and** business API calls) goes through the APIM gateway — there's no direct browser→backend path. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full request lifecycle and [LEARNING.md Phase 9](LEARNING.md#-phase-9-apim-gateway-migration--tls-ingress) for how it got this way.

> Note: logout is client-side only (session cleared in the browser; the IS token expires at its ~1h TTL). Server-side revocation is impossible behind the gateway — see "The one rule" in ARCHITECTURE.md.

## Quick Start (clone → run → test)

Everything is pre-baked: the repo commits the TLS certs, the WSO2 keystores, *and*
seed dumps of the fully configured databases (IS Service Provider + GitHub
connection, APIM Key Manager, LabAPI published + subscribed). On first boot with
an empty volume, Postgres auto-creates and seeds all three databases — **no manual
IS/APIM console setup needed.**

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

3. *(Optional, kills browser warnings)* Trust the lab CA: import `certs/rootCA.pem`
   into your OS/browser trust store. Skipping this just means clicking through a
   self-signed-cert warning — everything still works.

4. Open `https://portal.local.test` → **Login with GitHub** → dashboard → hit the
   three API test buttons. Consoles (if you want to poke around): IS at
   `https://localhost:9444/console`, APIM Publisher/DevPortal at
   `https://localhost:9443/publisher` / `/devportal` — all `admin`/`admin`.

5. Tear down:
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

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `900900 Unclassified Authentication Failure`, or APIM log shows `PKIX path building failed` | IS↔APIM certificate trust expired/broken | Regenerate and re-exchange certs — runbook in [LEARNING.md Phase 9](LEARNING.md#runbook-recovering-from-an-expired-isapim-trust-chain) |
| `900908 API Subscription validation failed` | Token's client isn't subscribed to the API being called | Dev Portal → Applications → your app → Subscriptions → subscribe to `LabAPI` (step 7 above) |
| IS/APIM stuck `Exited` with `address already in use` on restart, even though `docker ps` shows nothing on that port | Docker Desktop/WSL2 leftover port-forwarder state after an unclean shutdown | `wsl --shutdown` (elevated PowerShell) → reopen Docker Desktop → `docker compose up -d` |
| `invalid_client` / `application.not.found` at `/oauth2/authorize` | The OAuth app behind that client ID doesn't exist in IS (e.g. `postgres_data` was reset) | Recreate the Service Provider in IS Console, update `WSO2_IS_CLIENT_ID`/`SECRET` in `.env` |
| Logged in, but `/auth/me` shows the right `sub` with no name/email | Federated (GitHub) user claims come from `X-JWT-Assertion`, whose shape depends on `apim.jwt.convert_dialect` | See [Phase 9, Milestone 3](LEARNING.md#milestone-3-claim-dialect-for-x-jwt-assertion) |
