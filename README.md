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

All frontend traffic (auth **and** business API calls) goes through the APIM gateway — there's no direct browser→backend path. See [LEARNING.md Phase 9](LEARNING.md#-phase-9-apim-gateway-migration--tls-ingress) for why.

## Quick Start

> `POSTGRES_DB` only creates the `wso2db` placeholder database — it does **not** create `shared_db`, `identity_db`, or `apim_db`. Those must be created and seeded *before* WSO2 IS/APIM first boot, otherwise they fail their initial DB connection and get stuck (WSO2 doesn't retry — see step 6 if this happens to you).

1. Start Postgres only (first run only):
   ```bash
   docker compose up -d postgres
   ```

2. Create the 3 databases:
   ```bash
   docker exec wso2-postgres psql -U wso2 -d wso2db -c "CREATE DATABASE shared_db;"
   docker exec wso2-postgres psql -U wso2 -d wso2db -c "CREATE DATABASE identity_db;"
   docker exec wso2-postgres psql -U wso2 -d wso2db -c "CREATE DATABASE apim_db;"
   ```

3. Load the schema (see [LEARNING.md](LEARNING.md#phase-4-state-persistence--production-database-separation) for which script maps to which database):
   ```bash
   docker exec -i wso2-postgres psql -U wso2 -d shared_db < scripts/shared.sql
   docker exec -i wso2-postgres psql -U wso2 -d identity_db < scripts/identity_correct.sql
   docker exec -i wso2-postgres psql -U wso2 -d identity_db < scripts/consent.sql
   docker exec -i wso2-postgres psql -U wso2 -d apim_db < scripts/apim.sql
   ```
   On PowerShell, use `Get-Content` instead of `<` redirection.

   ```bash
   Get-Content scripts/shared.sql          | docker exec -e PGPASSWORD=wso2123 -i wso2-postgres psql -U wso2 -d shared_db
   Get-Content scripts/identity_correct.sql | docker exec -e PGPASSWORD=wso2123 -i wso2-postgres psql -U wso2 -d identity_db
   Get-Content scripts/consent.sql         | docker exec -e PGPASSWORD=wso2123 -i wso2-postgres psql -U wso2 -d identity_db
   Get-Content scripts/apim.sql            | docker exec -e PGPASSWORD=wso2123 -i wso2-postgres psql -U wso2 -d apim_db
   ```

4. Generate local trusted TLS certs (one-time per machine — `certs/` is gitignored):
   ```bash
   mkcert -install
   mkdir -p certs
   mkcert -cert-file certs/local.pem -key-file certs/local-key.pem \
     portal.local.test gateway.local.test is.local.test
   cp "$(mkcert -CAROOT)/rootCA.pem" certs/rootCA.pem
   ```

5. Add `/etc/hosts` entries so the browser resolves the `.local.test` names to the nginx container:
   ```bash
   echo -e "127.0.0.1  portal.local.test\n127.0.0.1  gateway.local.test\n127.0.0.1  is.local.test" | sudo tee -a /etc/hosts
   ```
   On Windows, add the same three lines to `C:\Windows\System32\drivers\etc\hosts` as Administrator.

6. Start the full stack:
   ```bash
   docker compose up -d
   ```
   Services start in dependency order via healthchecks — postgres → IS/APIM (parallel, ~2 min each) → backend → frontend → nginx. Watch progress with:
   ```bash
   docker compose ps   # STATUS column shows (healthy) when each service is ready
   ```
   > **If you skipped steps 1–3** and started everything before the databases exist, IS/APIM will fail their DB connection on first boot. Fix: create and seed the databases (steps 2–3), then `docker compose up -d` again — the backend will start once IS and APIM pass their healthchecks.

7. One-time WSO2 console setup (skip if you're reusing an existing `postgres_data` volume where this is already configured):
   - **IS Console** (`https://is.local.test/console`, `admin`/`admin`) — confirm the GitHub connection exists with JIT Provisioning enabled ([Phase 3](LEARNING.md#-phase-3-identity-brokerage--federation)), and that its OAuth2/OIDC app has `https://portal.local.test/callback` as an authorized redirect URL.
   - **APIM Publisher** (`https://gateway.local.test/publisher`) — confirm `LabAPI` is published, secured (OAuth2), and deployed to the `Default` gateway environment.
   - **APIM Dev Portal** (`https://gateway.local.test/devportal`) — create (or map) an Application using the **same client ID/secret** as the IS Service Provider above, generate **Production** keys, then **Subscribe** that Application to `LabAPI`. Without this, every gateway call returns `900908 API Subscription validation failed` even with a valid token — see [Phase 9](LEARNING.md#-phase-9-apim-gateway-migration--tls-ingress).

8. Access the app: `https://portal.local.test`. Direct console access (bypassing nginx) is also available at `https://localhost:9444/console`, `https://localhost:9443/publisher`, `https://localhost:9443/devportal`.

9. Tear down:
   ```bash
   docker compose down
   ```
   Add `-v` to also remove the `postgres_data` volume (this wipes the databases — you'd redo steps 1–3 and 7 next time).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `900900 Unclassified Authentication Failure`, or APIM log shows `PKIX path building failed` | IS↔APIM certificate trust expired/broken | Regenerate and re-exchange certs — runbook in [LEARNING.md Phase 9](LEARNING.md#runbook-recovering-from-an-expired-isapim-trust-chain) |
| `900908 API Subscription validation failed` | Token's client isn't subscribed to the API being called | Dev Portal → Applications → your app → Subscriptions → subscribe to `LabAPI` (step 7 above) |
| IS/APIM stuck `Exited` with `address already in use` on restart, even though `docker ps` shows nothing on that port | Docker Desktop/WSL2 leftover port-forwarder state after an unclean shutdown | `wsl --shutdown` (elevated PowerShell) → reopen Docker Desktop → `docker compose up -d` |
| `invalid_client` / `application.not.found` at `/oauth2/authorize` | The OAuth app behind that client ID doesn't exist in IS (e.g. `postgres_data` was reset) | Recreate the Service Provider in IS Console, update `WSO2_IS_CLIENT_ID`/`SECRET` in `.env` |
| Logged in, but `/auth/me` shows the right `sub` with no name/email | Federated (GitHub) user claims come from `X-JWT-Assertion`, whose shape depends on `apim.jwt.convert_dialect` | See [Phase 9, Milestone 3](LEARNING.md#milestone-3-claim-dialect-for-x-jwt-assertion) |
