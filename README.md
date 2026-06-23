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
└── scripts/             ← PostgreSQL schema scripts (shared, identity, consent, apim)
```

## Quick Start

> `POSTGRES_DB` only creates the `wso2db` placeholder database — it does **not** create `shared_db`, `identity_db`, or `apim_db`. Those must be created and seeded *before* WSO2 IS/APIM first boot, otherwise they fail their initial DB connection and get stuck (WSO2 doesn't retry — see step 4 if this happens to you).

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

4. Start WSO2 IS and APIM:
   ```bash
   docker compose up -d
   ```
   First boot takes ~1 min for IS and a few minutes for APIM. If you ever start `docker compose up -d` for *all* services before the databases/schema exist (skipping steps 1–3), IS/APIM will log a fatal DB error and hang instead of crash-looping — fix with `docker restart wso2is-local wso2apim-local` once the databases are ready.

5. Access the portals:
   - WSO2 IS Console: https://localhost:9444/console (`admin` / `admin`)
   - WSO2 APIM Publisher: https://localhost:9443/publisher
   - WSO2 APIM Dev Portal: https://localhost:9443/devportal

6. Tear down:
   ```bash
   docker compose down
   ```
   Add `-v` to also remove the `postgres_data` volume (this wipes the databases — you'd redo steps 1–3 next time).
