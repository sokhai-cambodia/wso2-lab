# Learning Journal

> A hands-on, phase-by-phase engineering journal covering local setup through gateway security. See [README.md](README.md) for project overview and quick start.

---

## 🗺️ Roadmap Overview

| Phase | Title | Status |
|-------|-------|--------|
| Phase 1 | Local Foundations & Gateway Architecture | ✅ Complete |
| Phase 2 | Core Synthesis (The Integrated Cluster) | ✅ Complete |
| Phase 3 | Identity Brokerage & Federation | ✅ Complete |
| Phase 4 | State Persistence & Production Database Separation | ✅ Complete |
| Phase 5 | Gateway Operations & Traffic Control | ✅ Complete |
| Phase 6 | Advanced Security & Token Engineering | ✅ Complete |
| Phase 7 | Production Auth — IS as External Key Manager | ✅ Complete |
| Phase 8 | Configuration Audit & Hardening | ✅ Complete |

---

## 🟢 Phase 1: Local Foundations & Gateway Architecture

### What You Learned
- The decoupled planes of WSO2 APIM: **Publisher, Developer Portal, Admin Portal, Gateway Engine**
- How to deploy WSO2 APIM as a standalone Docker container
- How to mock backend APIs using **inline JavaScript Script Mediators**
- How to publish, subscribe, and execute API calls using the resident Key Manager via `curl`

### Key Concepts
- WSO2 APIM separates the **control plane** (Publisher/Admin) from the **data plane** (Gateway Engine)
- The **resident Key Manager** handles OAuth token issuance by default
- Script Mediators allow lightweight backend mocking without a real service

---

## 🔵 Phase 2: Core Synthesis (The Integrated Cluster)

### What You Learned
- Cross-container **Docker bridge networking**
- **Dynamic Client Registration (DCR)** handshake between APIM and external Key Manager
- Java Truststore **certificate exchange** to resolve SSL PKIX errors
- How to isolate system routing using internal container ports and hostname mapping

### Key Concepts
- APIM and IS must share a **Docker network** to communicate by container name
- Self-signed SSL certificates require importing into `client-truststore.jks`
- DCR allows APIM to dynamically register itself as an OAuth client with WSO2 IS

### Docker Network Setup
```yaml
networks:
  wso2-network:
    driver: bridge
```

Both `wso2is` and `wso2apim` services must declare:
```yaml
networks:
  - wso2-network
```

---

## 🟡 Phase 3: Identity Brokerage & Federation

### What You Learned
- How to configure **GitHub as an external OIDC Identity Provider**
- How to use WSO2 IS 7.0.0's **visual Login Flow engine**
- How **Just-In-Time (JIT) Provisioning** works
- The difference between the **GitHub template** and **Standard-Based IdP** template
- Why the `admin` account doesn't automatically work with GitHub login (identity linking)

### Milestone 1: GitHub as External IdP

**GitHub OAuth App Settings:**
| Field | Value |
|-------|-------|
| Homepage URL | `https://localhost:9444` |
| Authorization callback URL | `https://localhost:9444/commonauth` |

**WSO2 IS Connection Settings:**
| Field | Value |
|-------|-------|
| Authorization endpoint | `https://github.com/login/oauth/authorize` |
| Token endpoint | `https://github.com/login/oauth/access_token` |
| User info endpoint | `https://api.github.com/user` |
| Scopes | `user:email`, `openid` |

### Milestone 2: Visual Login Flow Engine
- Navigate to **Applications → My Account → Login Flow**
- Add **Sign In With GitHub-Auth** as a login option
- The visual flow: `Step 1: GitHub-Auth → ✅ Success`

### Milestone 3: JIT Provisioning
- Navigate to **Connections → GitHub-Auth → Just-in-Time Provisioning**
- Enable JIT → set userstore to **PRIMARY**
- This auto-creates a local IS account on first GitHub login

### Architecture Decision
Keeping both `Username & Password` AND `GitHub` login options is **production best practice** — always maintain a local admin fallback.

### Key Insight
```
GitHub IdP  = the DOOR (how to talk to GitHub)
Application = the ROOM (who can use that door and what happens after)
```

---

## 🟠 Phase 4: State Persistence & Production Database Separation

### What You Learned
- Why H2 in-memory databases are unsuitable for production
- How to deploy **PostgreSQL** as a persistent third container
- WSO2's **3-database separation** pattern
- How to correctly identify and run WSO2 DB scripts
- How to mount JDBC drivers and config files via Docker volumes

### Database Architecture
```
┌─────────────────┐     ┌─────────────────┐
│   WSO2 APIM     │     │   WSO2 IS       │
│   :9443         │     │   :9444         │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └──────────┬────────────┘
                    ▼
         ┌─────────────────────┐
         │     PostgreSQL      │
         │  shared_db          │
         │  identity_db        │
         │  apim_db            │
         └─────────────────────┘
```

### Database Separation Pattern
| Database | Owner | Purpose |
|----------|-------|---------|
| `shared_db` | APIM + IS | Management registry, shared operational definitions |
| `identity_db` | IS | User store, OAuth scopes, active sessions |
| `apim_db` | APIM | Subscriptions, application metrics, API definitions |

### Correct DB Scripts (Critical Lesson)
WSO2 IS ships **3 separate PostgreSQL scripts** — using the wrong one causes missing tables:

```
/dbscripts/postgresql.sql            → shared_db
/dbscripts/identity/postgresql.sql   → identity_db
/dbscripts/consent/postgresql.sql    → identity_db (also needed)
```

APIM script:
```
/dbscripts/apimgt/postgresql.sql     → apim_db
```

### Running Scripts on PowerShell
PowerShell does not support `<` redirection. Use `Get-Content` instead:
```powershell
Get-Content ./identity.sql | docker exec -i wso2-postgres psql -U wso2 -d identity_db
```

### docker-compose.yml (current — includes all phases)
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: wso2-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-wso2}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-wso2123}
      POSTGRES_DB: ${POSTGRES_DB:-wso2db}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - wso2-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U wso2 -d wso2db"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  wso2is:
    image: wso2/wso2is:7.0.0
    container_name: wso2is-local
    ports:
      - "9444:9444"
    command: ["sh", "-c", "/home/wso2carbon/docker-entrypoint.sh -DportOffset=1 -Dorg.wso2.IdentityRESTAPISecurity.disableBasicAuth=false"]
    environment:
      - JVM_MEM_OPTS=-Xms1g -Xmx2g
    volumes:
      - ./libs/postgresql-42.7.3.jar:/home/wso2carbon/wso2is-7.0.0/repository/components/lib/postgresql-42.7.3.jar
      - ./config/is/deployment.toml:/home/wso2carbon/wso2is-7.0.0/repository/conf/deployment.toml
    restart: unless-stopped
    stop_grace_period: 60s
    networks:
      - wso2-network
    healthcheck:
      test: ["CMD-SHELL", "curl -sf https://localhost:9444/api/health-check/v1.0/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 120s

  wso2apim:
    image: wso2/wso2am:4.3.0
    container_name: wso2apim-local
    ports:
      - "9443:9443"
      - "8243:8243"
      - "8280:8280"
    environment:
      - JVM_MEM_OPTS=-Xms1g -Xmx2g
    volumes:
      - ./libs/postgresql-42.7.3.jar:/home/wso2carbon/wso2am-4.3.0/repository/components/lib/postgresql-42.7.3.jar
      - ./config/apim/deployment.toml:/home/wso2carbon/wso2am-4.3.0/repository/conf/deployment.toml
    restart: unless-stopped
    stop_grace_period: 60s
    networks:
      - wso2-network
    healthcheck:
      test: ["CMD-SHELL", "curl -sf https://localhost:9443/api/am/publisher/v4/apis || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 120s

networks:
  wso2-network:
    driver: bridge

volumes:
  postgres_data:
```

> The full `docker-compose.yml` also includes rabbitmq (Phase 5), backend (Phase 6), and frontend (Phase 7) services with matching healthchecks and `depends_on: condition: service_healthy` so containers start in the correct order automatically.

### WSO2 IS deployment.toml (PostgreSQL)
```toml
[server]
hostname = "localhost"
node_ip = "127.0.0.1"
base_path = "https://$ref{server.hostname}:${carbon.management.port}"

[super_admin]
username = "admin"
password = "admin"
create_admin_account = true

[user_store]
type = "database_unique_id"

[database.identity_db]
type = "postgre"
url = "jdbc:postgresql://wso2-postgres:5432/identity_db"
username = "wso2"
password = "wso2123"
driver = "org.postgresql.Driver"

[database.shared_db]
type = "postgre"
url = "jdbc:postgresql://wso2-postgres:5432/shared_db"
username = "wso2"
password = "wso2123"
driver = "org.postgresql.Driver"

[keystore.primary]
file_name = "wso2carbon.jks"
password = "wso2carbon"
type = "JKS"

[truststore]
file_name = "client-truststore.jks"
password = "wso2carbon"
type = "JKS"
```

### WSO2 APIM deployment.toml (PostgreSQL — changed sections only)
```toml
[database.apim_db]
type = "postgre"
url = "jdbc:postgresql://wso2-postgres:5432/apim_db"
username = "wso2"
password = "wso2123"
driver = "org.postgresql.Driver"

[database.shared_db]
type = "postgre"
url = "jdbc:postgresql://wso2-postgres:5432/shared_db"
username = "wso2"
password = "wso2123"
driver = "org.postgresql.Driver"
```

---

---

## 🔴 Phase 5: Gateway Operations & Traffic Control

### What You Learned
- How to protect backend microservices from traffic overload using throttling policies
- How to inject custom Synapse mediation sequences into gateway traffic
- How to add an async event queue (RabbitMQ) so gateway events are decoupled from the gateway process

### Milestone 1: Rate Limiting Tiers (Throttling Policies)

WSO2 APIM supports throttling at 3 levels:

| Level | Description |
|-------|-------------|
| API Level | Limit total requests to the entire API |
| Application Level | Limit requests per registered app |
| Resource Level | Limit requests per individual endpoint |

**Config change (`config/apim/deployment.toml`):**
```toml
[apim.throttling]
enable_data_publishing = true
enable_policy_deploy = true
enable_blacklist_condition = true
enable_persistence = true
```

**Steps to create a policy (Admin UI):**
1. Go to `https://localhost:9443/admin`
2. Navigate to **Rate Limiting → Advanced Policies**
3. Create a new policy (e.g. `10PerMin` — 10 requests per minute)
4. Apply it via **Publisher → API → Runtime → Subscription Tiers**

**Test throttling with curl:**
```bash
for i in {1..15}; do
  curl -sk -X GET "https://localhost:8243/your-api/v1/resource" \
    -H "Authorization: Bearer YOUR_TOKEN"
  echo "Request $i"
done
```

After the limit is hit, APIM returns HTTP 429:
```json
{
  "fault": {
    "code": 900800,
    "message": "Message throttled out",
    "description": "You have exceeded your quota"
  }
}
```

### Milestone 2: Custom Mediation Logic (Header Injection)

A Synapse XML sequence that the gateway applies to every forwarded request — useful for injecting tracing headers, routing hints, or auth metadata that backends rely on.

**File: `config/apim/sequences/custom-header-sequence.xml`**
```xml
<sequence name="custom-header-sequence" xmlns="http://ws.apache.org/ns/synapse">
    <header name="X-Custom-Header" value="WSO2-Gateway" scope="transport"/>
    <header name="X-Gateway-Version" value="4.3.0" scope="transport"/>
</sequence>
```

This file is **volume-mounted** into the APIM container at:
```
/home/wso2carbon/wso2am-4.3.0/repository/deployment/server/synapse-configs/default/sequences/
```

**Activate in the Publisher UI:**
1. Go to **Publisher → your API → Runtime**
2. Under **Request Mediation** → click the pencil icon
3. Choose **Select Existing Sequence** → pick `custom-header-sequence`
4. Save and re-deploy the API

### Milestone 3: Async Event Handling (RabbitMQ)

RabbitMQ is added to the stack as the message broker for gateway lifecycle events. The architecture pattern: services publish events to a queue, downstream consumers process them independently — completely decoupled from the gateway.

**docker-compose.yml addition:**
```yaml
rabbitmq:
  image: rabbitmq:3-management
  container_name: wso2-rabbitmq
  ports:
    - "5672:5672"    # AMQP
    - "15672:15672"  # Management UI
  networks:
    - wso2-network
```

**Verify RabbitMQ is running:** Navigate to `http://localhost:15672` (login: `guest` / `guest`).

> **Important limitation in WSO2 4.3.0 / IS 7.0.0:** WSO2 does **not** automatically publish events to RabbitMQ out of the box. A real integration requires a custom Java event handler that reads WSO2's internal events and publishes them via AMQP. For the lab, RabbitMQ is confirmed running and operable; the custom publisher is the next extension step.
> Note: the `[[event_handler]]` block that was previously in `config/apim/deployment.toml` (a user-registration notification hook) was an IS-level config that was cleaned up in Phase 8 — it had no connection to RabbitMQ. The `[[event_listener]]` block that remains is for token revocation notifications, also unrelated to RabbitMQ.

### Key Concepts
- **Throttling** protects backend services from overload; APIM enforces quotas before requests ever reach the backend
- **Synapse sequences** let you transform requests/responses at the gateway without touching backend code
- **Event-driven architecture** keeps the gateway lean — lifecycle events land in a queue and consumers process them at their own pace; WSO2 4.3.0 requires a custom Java event handler to publish to RabbitMQ (not built-in)

---

## 🟣 Phase 6: Advanced Security & Token Engineering

### What You Learned
- Zero-trust gateway security with per-API mutual TLS (mTLS)
- Token transformation: APIM signs a JWT and forwards it to the backend so the backend verifies locally
- Fine-grained access control: OAuth scopes bound to IS roles control which users reach which endpoints

### Milestone 1: Mutual TLS (mTLS) at the Gateway Edge

Normal HTTPS: the server proves its identity to the client.  
mTLS: **both sides** present certificates. A client without a valid cert is rejected at the TLS handshake — no HTTP code ever runs.

**Step 1: Generate client certificate**
```bash
bash scripts/generate-certs.sh
# writes: certs/client.key (gitignored), certs/client.csr, certs/client.crt
```

**Step 2: Enable mTLS per-API in the Publisher UI (recommended for lab)**
1. Go to **Publisher → your API → Runtime**
2. Under **Transport Level Security** → enable **Mutual SSL**
3. Upload `certs/client.crt` as a trusted client certificate
4. Re-deploy the API

**Step 3: Test**
```bash
# With client cert — succeeds (HTTP 200)
curl -sk --cert certs/client.crt --key certs/client.key \
  https://localhost:8243/your-api/v1/resource \
  -H "Authorization: Bearer YOUR_TOKEN"

# Without client cert — rejected at TLS layer
curl -sk https://localhost:8243/your-api/v1/resource \
  -H "Authorization: Bearer YOUR_TOKEN"
# → SSL handshake failure (no HTTP response at all)
```

> **Why not enable_client_auth = true globally?**  
> Setting it globally in deployment.toml forces mTLS on ALL HTTPS connections, including the Publisher, Admin, and Dev Portal UIs — which breaks the web console. Per-API mTLS in the Publisher is the production-correct approach.

### Milestone 2: Token Transformation (Opaque → JWT)

The most important pattern for microservices security. The client never has to present a JWT — APIM transforms the token before it reaches the backend.

```
Client App
    │
    │  (1) sends opaque reference token to APIM
    ▼
WSO2 APIM Gateway
    │
    │  (2) validates opaque token against WSO2 IS
    │  (3) generates signed JWT with user claims
    │  (4) forwards request with X-JWT-Assertion: <signed JWT>
    ▼
Backend (backend/main.py — FastAPI)
    │
    │  (5) fetches APIM JWKS from https://wso2apim:9443/oauth2/jwks
    │  (6) verifies JWT signature locally — no round-trip to IS
    ▼
    ✅ Zero-trust verified request
```

**Config change (`config/apim/deployment.toml`):**
```toml
[apim.jwt]
enable = true
encoding = "base64"
header = "X-JWT-Assertion"
signing_algorithm = "SHA256withRSA"
enable_user_claims = true
claim_dialect = "http://wso2.org/claims"
```

**Backend (`backend/main.py`):**  
The FastAPI service fetches APIM's public keys from the JWKS endpoint and verifies every JWT locally. See `backend/main.py` for the full implementation.

**Test:**
```bash
# Hit the backend through APIM (JWT is injected automatically)
curl -sk https://localhost:8243/your-api/v1/secure-resource \
  -H "Authorization: Bearer YOUR_OPAQUE_TOKEN"
# → {"user": "john@example.com", "claims": {...}}

# Hit the backend directly (no JWT injected — returns 401)
curl http://localhost:8000/secure-resource
# → {"detail": "Missing X-JWT-Assertion header"}
```

### Milestone 3: OAuth Scopes Bound to Roles

Fine-grained authorization at the resource level. A JWT is only issued with a scope if the user has the matching role. APIM enforces the scope on every request — the backend receives nothing it isn't authorized to handle.

> **Key setup fact (Phase 6):** At this phase APIM used its **built-in Key Manager** — IS KM integration was not yet configured. API access tokens were issued by APIM and scopes were **Local Scopes in APIM Publisher**. IS provided only the user store. Phase 7 upgrades this to full IS Key Manager integration.

**Step 1: Create role in WSO2 IS 7.0.0**
1. Go to `https://localhost:9444/console`
2. Navigate to **User Management → Roles** → click **Add Role**
3. Create role `analyst`
4. Create user `analyst-user` in **User Management → Users** → **Add User**
5. Assign role separately: Users → click `analyst-user` → **Roles** tab → **Add Roles** → tick `analyst`

**Step 2: Create scope in APIM Publisher (not IS)**
1. Publisher → your API → **Local Scopes** → **Add New Local Scope**
2. Scope Key: `read:reports`, Roles: `analyst`
3. Save

**Step 3: Bind scope to API resource**
1. Publisher → your API → **Resources**
2. Expand `GET /reports` → set **Operation Scope** to `read:reports`
3. Re-deploy the API

**Step 4: Test scope enforcement — token comes from APIM (port 9443)**
```bash
# Get token for analyst-user — APIM checks IS role, finds analyst → grants scope
curl -sk -X POST https://localhost:9443/oauth2/token \
  -d "grant_type=password&username=analyst-user&password=Test%401234&scope=read:reports" \
  -u "CLIENT_ID:CLIENT_SECRET" \
  -H "Content-Type: application/x-www-form-urlencoded"
# → token includes read:reports scope → /reports returns 200

# Admin has no analyst role → scope not granted → /reports returns 403
```

### Key Concepts
- **mTLS at the API level** — per-API mutual TLS is the production pattern; global transport mTLS breaks the management UI
- **JWKS endpoint** — WSO2 APIM exposes `GET /oauth2/jwks` so any backend can verify JWTs without calling IS at runtime
- **Opaque → JWT transformation** — clients send cheap opaque tokens; the gateway handles the expensive validation and enriches the downstream request
- **Scope ≠ Role** — a scope is a permission label on the API resource (defined in APIM Local Scopes); a role is assigned to users in IS; APIM maps role → scope at token issuance time
- **Built-in KM vs. IS KM** — when APIM uses its built-in Key Manager (default), scopes live in APIM Publisher; when IS is the external KM, scopes can be managed in IS. Check whether a `[[apim.jwt.issuer]]` block pointing at IS is present to know which mode you are in

---

## 📁 Final Project Folder Structure
```
wso2-lab/
├── README.md
├── LEARNING.md
├── docker-compose.yml
├── is_public.crt                       ← generated by scripts/setup-key-manager.sh (Phase 7)
├── libs/
│   └── postgresql-42.7.3.jar
├── config/
│   ├── is/
│   │   └── deployment.toml
│   └── apim/
│       ├── deployment.toml
│       └── sequences/
│           └── custom-header-sequence.xml   ← Phase 5: Synapse mediation
├── certs/                              ← Phase 6: mTLS certificates
│   ├── client.key                          (gitignored — never commit)
│   ├── client.crt
│   └── client.csr
├── backend/                            ← Phase 6: FastAPI JWT-verified service
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
└── scripts/
    ├── generate-certs.sh               ← Phase 6: mTLS cert generation
    ├── setup-key-manager.sh            ← Phase 7: IS cert exchange + Key Manager setup guide
    ├── identity_correct.sql
    ├── consent.sql
    ├── shared.sql
    └── apim.sql
```

---

---

## 🟤 Phase 7: Production Auth — IS as External Key Manager

### What You Learned
- How to configure **WSO2 IS as the APIM external Key Manager** — IS owns all token operations
- **Java truststore certificate exchange** between APIM and IS to resolve `SSLHandshakeException`
- Why the frontend can now send IS tokens **directly to the APIM gateway** — no backend proxy
- The full **DCR (Dynamic Client Registration)** endpoint set required by APIM to talk to IS
- Why backend sessions (`_sessions` dict) are an anti-pattern and how IS introspection replaces them

### Architecture Change

**Before (lab shortcut):**
```
Frontend → Backend /api-test/{endpoint}
             ↓ client_credentials token swap
           APIM Gateway → Backend resource
```

**After (production):**
```
Frontend → APIM Gateway (IS access_token)
             ↓ IS introspects token (Key Manager)
           Backend resource endpoint
```

### Key Manager Endpoints

All use Docker service name `wso2is` (container-to-container, not `localhost`):

| Endpoint | URL |
|----------|-----|
| Issuer | `https://wso2is:9444/oauth2/token` |
| Client Registration | `https://wso2is:9444/api/identity/oauth2/dcr/v1.1/register` |
| Introspection | `https://wso2is:9444/oauth2/introspect` |
| Token | `https://wso2is:9444/oauth2/token` |
| Revoke | `https://wso2is:9444/oauth2/revoke` |
| UserInfo | `https://wso2is:9444/oauth2/userinfo` |
| Authorize | `https://wso2is:9444/oauth2/authorize` |
| Scope Management | `https://wso2is:9444/api/identity/oauth2/v1.0/scopes` |

### Key Concepts
- **IS as Key Manager** = APIM delegates all OAuth operations to IS; one token works everywhere
- **Certificate exchange is required** — APIM's JVM rejects self-signed IS certs without importing them into `client-truststore.jks`
- **`wso2is` not `localhost`** — Key Manager endpoints must use Docker service names for container-to-container calls
- **DCR** — APIM auto-registers itself as an OAuth client in IS using the Client Registration endpoint; no manual IS app creation needed for APIM
- **CORS on gateway** — when the browser calls APIM directly, the API must allow the frontend origin
- **Stateless backend** — IS introspects tokens on every request; no custom session storage; any backend instance can serve any request
- **Logout revokes at IS** — `POST /oauth2/revoke` invalidates the token at the source; no dict to clean up

---

## 🔑 Key Lessons Learned

1. **Docker networking is required** — APIM and IS must be on the same bridge network to communicate
2. **WSO2 ships multiple DB scripts** — always use the correct script for each database
3. **PowerShell uses Get-Content** — not `<` for piping files to Docker exec
4. **JIT Provisioning** — required to auto-create users who log in via external IdPs
5. **Keep local admin fallback** — never remove BasicAuthenticator from production login flows
6. **JDBC driver must be mounted** — PostgreSQL driver jar must be in `/repository/components/lib/`
7. **Volume mounts persist data** — Docker named volumes survive container restarts
8. **Throttling has 3 levels** — API, Application, and Resource level policies
9. **Token transformation is zero-trust** — never trust raw tokens in microservices; always exchange to JWT
10. **Scopes + Roles = fine-grained access** — bind scopes to roles for per-endpoint authorization
11. **mTLS per-API, not globally** — enabling client auth globally breaks the management UI; use per-API mTLS in Publisher
12. **JWKS > static public key** — backends should fetch signing keys from the APIM JWKS endpoint, not hardcode them
13. **Synapse sequences are volume-mounted** — drop the XML file into the sequences directory and activate in the UI without restarting APIM
14. **RabbitMQ decouples events** — gateway lifecycle events (user created, app registered) land in a queue; consumers process independently
15. **IS as Key Manager eliminates token swapping** — frontend sends IS token directly to APIM; no backend credential proxy needed
16. **Java truststore exchange is mandatory** — APIM's JVM won't trust self-signed IS certs without importing them into `client-truststore.jks` via `keytool`
17. **DCR auto-registers APIM with IS** — once Key Manager is saved, APIM uses the Client Registration endpoint to create its own IS OAuth client dynamically
18. **Stateless auth via IS introspection** — no in-memory session store; every backend instance validates tokens by calling IS introspect
19. **CORS must be enabled per-API** — when the browser calls APIM gateway directly, each API must allowlist the frontend origin in APIM Publisher → Runtime → CORS

---

---

## 🔧 Phase 8: Configuration Audit & Hardening

### What You Learned
- How misplaced config blocks silently fail when IS is the external Key Manager
- Why the UserInfo endpoint for a Key Manager must be the OIDC standard endpoint, not a SCIM endpoint
- How `[[apim.jwt.issuer]]` differs from `[apim.jwt]` and why both are needed
- The importance of OAuth state validation for CSRF protection in custom auth flows

### Changes Applied

| File | Change | Reason |
|------|--------|--------|
| `config/apim/deployment.toml` | `[apim.ai] enable = false` | Empty token/endpoint caused startup errors |
| `config/apim/deployment.toml` | Removed `[oauth.grant_type.token_exchange]` | IS-level config — silently ignored in APIM |
| `config/apim/deployment.toml` | Removed `[[event_handler]]` and `[service_provider]` | IS-level blocks copy-pasted into APIM config |
| `config/apim/deployment.toml` | Added `[[apim.jwt.issuer]]` pointing at IS JWKS | Required for APIM to validate self-contained IS JWTs |
| `config/is/deployment.toml` | Added `[oauth.grant_type.token_exchange]` | Token exchange must be enabled on IS, not APIM |
| `scripts/setup-key-manager.sh` | `UserInfo: /oauth2/userinfo` (was `/scim2/Me`) | SCIM endpoint is not OIDC-compliant; APIM expects UserInfo |
| `backend/main.py` | OAuth state stored and validated in `/auth/exchange` | State was generated but never checked — CSRF protection was non-functional |

### Key Concepts
- **`[apim.jwt]`** — controls the _outbound_ JWT APIM injects into backend requests (X-JWT-Assertion). Always lives in APIM.
- **`[[apim.jwt.issuer]]`** — tells APIM how to validate _incoming_ JWT access tokens from an external issuer. Required when IS is the Key Manager.
- **`[oauth.grant_type.*]`** — all grant type configs belong in IS when IS is the Key Manager. APIM does not process these when it delegates tokens.
- **UserInfo vs. SCIM** — `GET /oauth2/userinfo` returns OIDC claims; `GET /scim2/Me` returns SCIM user attributes. APIM Key Manager integration expects the OIDC UserInfo endpoint.
- **OAuth state parameter** — state must be stored server-side and validated on code exchange to prevent cross-site request forgery; generating a state without validating it provides no protection.

---

*Document complete — Phases 1 through 8 covered.*
