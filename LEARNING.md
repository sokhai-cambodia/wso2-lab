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

### Final docker-compose.yml
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: wso2-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: wso2
      POSTGRES_PASSWORD: wso2123
      POSTGRES_DB: wso2db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - wso2-network

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
    networks:
      - wso2-network

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
    networks:
      - wso2-network

networks:
  wso2-network:
    driver: bridge

volumes:
  postgres_data:
```

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

> **Status: 🔲 Planned — Continue from office**

### What You Will Learn
- How to protect backend microservices from traffic overload
- Rate limiting and throttling at multiple levels
- Custom mediation logic at the gateway
- Async event handling with message queues

### Milestone 1: Rate Limiting Tiers (Throttling Policies)

WSO2 APIM supports throttling at 3 levels:

| Level | Description |
|-------|-------------|
| API Level | Limit total requests to the entire API |
| Application Level | Limit requests per registered app |
| Resource Level | Limit requests per individual endpoint |

**Steps:**
1. Go to `https://localhost:9443/admin`
2. Navigate to **Rate Limiting → Advanced Policies**
3. Create a new policy (e.g. `10PerMin` — 10 requests per minute)
4. Apply it to your API via **Publisher → API → Runtime → Subscription Tiers**

**Test throttling with curl:**
```bash
for i in {1..15}; do
  curl -X GET "https://localhost:8243/your-api/v1/resource" \
    -H "Authorization: Bearer YOUR_TOKEN"
  echo "Request $i"
done
```

After the limit is hit, APIM returns:
```json
{
  "fault": {
    "code": 900800,
    "message": "Message throttled out",
    "description": "You have exceeded your quota"
  }
}
```

### Milestone 2: Custom Mediation Logic

Use **Velocity templates** or **mediation sequences** to intercept and transform gateway traffic.

**Example: Add custom header to all requests**
1. Go to **Publisher → API → Runtime → Request Mediation**
2. Add a custom sequence:
```xml
<sequence xmlns="http://ws.apache.org/ns/synapse">
  <header name="X-Custom-Header" value="WSO2-Gateway" scope="transport"/>
</sequence>
```

### Milestone 3: Async Event Handling (RabbitMQ + Celery)

Connect message queues to handle events when an application is created/updated.

**docker-compose.yml addition:**
```yaml
rabbitmq:
  image: rabbitmq:3-management
  container_name: wso2-rabbitmq
  ports:
    - "5672:5672"
    - "15672:15672"
  networks:
    - wso2-network
```

**Event listener config in APIM deployment.toml:**
```toml
[[event_handler]]
name = "userPostSelfRegistration"
subscriptions = ["POST_ADD_USER"]
```

---

## 🟣 Phase 6: Advanced Security & Token Engineering

> **Status: 🔲 Planned — Continue from office**

### What You Will Learn
- Zero-trust gateway security with mTLS
- Token transformation: opaque token → signed JWT
- Fine-grained access control with OAuth scopes bound to roles

### Milestone 1: Mutual TLS (mTLS) at the Gateway Edge

mTLS requires **both client and server** to present certificates — not just the server.

**Step 1: Generate client certificate**
```bash
# Generate client key and certificate
openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr -subj "/CN=client/O=wso2"
openssl x509 -req -days 365 -in client.csr -signkey client.key -out client.crt
```

**Step 2: Import client cert into WSO2 truststore**
```bash
keytool -import -alias client \
  -file client.crt \
  -keystore client-truststore.jks \
  -storepass wso2carbon
```

**Step 3: Enable mTLS in APIM deployment.toml**
```toml
[transport.https]
enable_client_auth = true
```

**Step 4: Test with mTLS curl**
```bash
curl --cert client.crt --key client.key \
  https://localhost:8243/your-api/v1/resource
```

### Milestone 2: Token Transformation (Opaque → JWT)

This is the most critical pattern for microservices security:

```
Client App
    │
    │  (1) sends opaque reference token
    ▼
WSO2 APIM Gateway
    │
    │  (2) validates token against WSO2 IS
    │  (3) exchanges for signed JWT with user claims
    ▼
Backend FastAPI Microservice
    │
    │  (4) receives JWT, verifies signature locally
    ▼
    ✅ Zero-trust verified request
```

**Enable JWT generation in APIM deployment.toml:**
```toml
[apim.jwt]
enable = true
encoding = "base64"
header = "X-JWT-Assertion"
signing_algorithm = "SHA256withRSA"
enable_user_claims = true
claim_dialect = "http://wso2.org/claims"
```

**FastAPI JWT verification example:**
```python
from fastapi import FastAPI, Header, HTTPException
import jwt

app = FastAPI()

WSO2_PUBLIC_KEY = "your-wso2-public-key"

@app.get("/secure-resource")
async def secure_resource(x_jwt_assertion: str = Header(None)):
    if not x_jwt_assertion:
        raise HTTPException(status_code=401, detail="Missing JWT")
    try:
        payload = jwt.decode(
            x_jwt_assertion,
            WSO2_PUBLIC_KEY,
            algorithms=["RS256"]
        )
        return {"user": payload.get("sub"), "claims": payload}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### Milestone 3: OAuth Scopes Bound to Roles

Fine-grained access control: only users with the correct **role** can access specific API resources.

**Step 1: Create a scope in WSO2 IS**
1. Go to `https://localhost:9444/console`
2. Navigate to **API Resources → Scopes**
3. Create scope: `read:reports` bound to role `analyst`

**Step 2: Bind scope to API resource in APIM**
1. Go to **Publisher → API → Resources**
2. Select a resource (e.g. `GET /reports`)
3. Under **OAuth2 Security** → add scope `read:reports`

**Step 3: Test scope enforcement**
```bash
# Request token with scope
curl -X POST https://localhost:9444/oauth2/token \
  -d "grant_type=password&username=testuser&password=testpass&scope=read:reports" \
  -u "client_id:client_secret"

# Use scoped token
curl -X GET https://localhost:8243/your-api/v1/reports \
  -H "Authorization: Bearer SCOPED_TOKEN"
```

If the user doesn't have the `analyst` role, APIM returns `403 Forbidden`.

---

## 📁 Final Project Folder Structure
```
wso2-lab/
├── README.md
├── LEARNING.md
├── docker-compose.yml
├── libs/
│   └── postgresql-42.7.3.jar
├── config/
│   ├── is/
│   │   └── deployment.toml
│   └── apim/
│       └── deployment.toml
├── certs/                    # Phase 6
│   ├── client.key
│   ├── client.crt
│   └── client.csr
└── scripts/
    ├── identity_correct.sql
    ├── consent.sql
    ├── shared.sql
    └── apim.sql
```

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

---

*Document complete — Phases 1 through 6 covered.*
