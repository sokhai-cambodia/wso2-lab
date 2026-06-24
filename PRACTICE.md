# WSO2 Lab — Phase 5 & 6 Practice Guide

> **Before you start:** All config files, Docker services, and the FastAPI backend have already been written.
> This document is your hands-on practice runbook — follow each step in order.

---

## Stack Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        Your Machine                           │
│                                                              │
│  Browser → Next.js Frontend (3000)                          │
│               │ auth calls (login-url / exchange / me)       │
│               │                  │ API calls (Bearer IS token)│
│               ▼                  ▼                           │
│        FastAPI Backend (8000)  APIM Gateway (8243)           │
│               │                  │  validates token with IS  │
│               ▼                  │  injects X-JWT-Assertion  │
│          WSO2 IS (9444) ◄────────┘  forwards to backend      │
│               │  (IS = APIM Key Manager)   │                 │
│               │ GitHub OAuth               ▼                 │
│               ▼                   FastAPI Backend (8000)     │
│           github.com                       │                 │
│                                   PostgreSQL (5432)          │
│                                   RabbitMQ  (5672/15672)     │
└──────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

| Service | URL | Login |
|---------|-----|-------|
| **Next.js Frontend** | http://localhost:3000 | GitHub via WSO2 IS |
| APIM Publisher | https://localhost:9443/publisher | admin / admin |
| APIM Admin | https://localhost:9443/admin | admin / admin |
| APIM DevPortal | https://localhost:9443/devportal | admin / admin |
| WSO2 IS Console | https://localhost:9444/console | admin / admin |
| RabbitMQ UI | http://localhost:15672 | guest / guest |
| FastAPI Backend | http://localhost:8000/health | — |
| FastAPI API Docs | http://localhost:8000/docs | — |

---

## Part 0A — GitHub Login Setup (One-time prerequisite)

### How the login flow works

```
Browser (click Login)
    │
    │  GET /auth/login-url
    ▼
FastAPI Backend
    │  builds IS authorize URL with fidp=GitHub
    │  returns { url: "https://localhost:9444/oauth2/authorize?...&fidp=GitHub" }
    ▼
Browser
    │  window.location.href = url
    ▼
WSO2 IS  ← fidp=GitHub skips the IS login screen entirely
    │  IS redirects straight to GitHub
    ▼
GitHub OAuth page  ← user approves here
    │  GitHub redirects to https://localhost:9444/commonauth
    ▼
WSO2 IS  ← completes federated login, issues its own authorization code
    │  IS redirects to http://localhost:3000/callback?code=xxx
    ▼
Next.js /callback page
    │  POST /auth/exchange { code }
    ▼
FastAPI Backend → IS /oauth2/token (exchange code for tokens)
    │  extracts user from id_token
    └→ returns { access_token, user }   ← IS access_token, not a custom session
    ▼
User logged in ✅  (Frontend stores IS access_token, calls APIM gateway directly)
```

> **Key:** `fidp=GitHub` tells IS to skip its own login screen and go straight to the GitHub connection. The IS application still acts as the OIDC provider — it issues the final `code` and tokens. GitHub only handles identity, not token issuance.

---

### Step 0A.1 — Create a GitHub OAuth App

1. Go to **GitHub → Settings → Developer settings → OAuth Apps → New OAuth App**
2. Fill in:

   | Field | Value |
   |-------|-------|
   | Application name | `WSO2 Lab` |
   | Homepage URL | `https://localhost:9444` |
   | Authorization callback URL | `https://localhost:9444/commonauth` |

3. Click **Register application**
4. Click **Generate a new client secret**
5. **Save both values** — you need them in Step 0A.2:
   - `GitHub Client ID`
   - `GitHub Client Secret`

> `https://localhost:9444/commonauth` is the WSO2 IS endpoint that receives the code from GitHub and completes the federated handshake. The browser never goes back to your frontend from GitHub directly.

---

### Step 0A.2 — Add GitHub as a Connection in WSO2 IS

> Start the stack first (`docker compose up -d`) and wait for IS at `https://localhost:9444/console`.

1. Go to `https://localhost:9444/console` → login `admin / admin`
2. Left menu → **Connections** → **New Connection**
3. Select the **GitHub** template from the social IdPs list
4. Fill in:

   | Field | Value |
   |-------|-------|
   | Name | `GitHub` |
   | Client ID | *(your GitHub OAuth App Client ID)* |
   | Client Secret | *(your GitHub OAuth App Client Secret)* |

5. Click **Finish**

> **Note the exact connection name you use** — it must match `GITHUB_IDP_NAME` in `.env`. If you name it `GitHub`, set `GITHUB_IDP_NAME=GitHub`.

> **If you don't see a GitHub template**, choose **Custom Connector → OAuth2/OIDC** and set:
> - Authorization Endpoint URL: `https://github.com/login/oauth/authorize`
> - Token Endpoint URL: `https://github.com/login/oauth/access_token`
> - User Info Endpoint URL: `https://api.github.com/user`
> - Scopes: `user:email`

---

### Step 0A.3 — Create the Frontend Application in WSO2 IS

1. Left menu → **Applications** → **New Application**
2. Choose **Standard-Based Application**
3. Select **OAuth2 / OpenID Connect** → click **Next**
4. Fill in:

   | Field | Value |
   |-------|-------|
   | Name | `wso2-lab-frontend` |
   | Allowed callback URLs | `http://localhost:3000/callback` |

5. Click **Register**
6. In the app detail page → **Protocol** tab → copy:
   - **Client ID** → `WSO2_IS_CLIENT_ID` in `.env`
   - **Client Secret** → `WSO2_IS_CLIENT_SECRET` in `.env`

---

### Step 0A.4 — Add GitHub to the application's sign-in method

The `fidp` parameter only works if GitHub is already configured as a login option on the application.

1. Still in the `wso2-lab-frontend` app → **Sign-in Method** tab
2. Click **Add Sign-in Option** (within Step 1, not "Add new step")
3. Select **GitHub** (the connection from Step 0A.2)
4. Click **Update**

> Without this, IS will ignore `fidp=GitHub` and show its own login page instead.

---

### Step 0A.5 — Update `.env`

Open `.env` in the project root:

```
# WSO2 IS application credentials (from Step 0A.3, Protocol tab)
WSO2_IS_CLIENT_ID=<paste Client ID>
WSO2_IS_CLIENT_SECRET=<paste Client Secret>

# Must exactly match the connection name you used in Step 0A.2
GITHUB_IDP_NAME=GitHub
```

> `APIM_CLIENT_ID` / `APIM_CLIENT_SECRET` are no longer needed — the frontend sends the IS token directly to the APIM gateway. No backend credential swap is required.

Recreate the backend container to pick up the new values:

```bash
docker compose up -d backend
```

> `docker compose restart` does NOT re-read `.env` — always use `up -d` after editing `.env`.

---

### Checkpoint — Test the full login flow

1. Visit `http://localhost:3000`
2. Click **Login with GitHub via WSO2 IS**
3. Browser jumps **directly to github.com** — no IS login page appears
4. Authorize the GitHub OAuth App
5. Browser lands on `http://localhost:3000/dashboard`
6. Dashboard shows your GitHub username and email

**Troubleshooting:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| IS login page appears (not GitHub) | `fidp` not working | Check Step 0A.4 — GitHub must be in Sign-in Method; check `GITHUB_IDP_NAME` matches connection name exactly |
| `invalid_client` from IS | Wrong Client ID/Secret | Re-check `WSO2_IS_CLIENT_ID/SECRET` in `.env`; run `docker compose up -d backend` |
| `redirect_uri mismatch` from GitHub | Wrong callback in GitHub OAuth App | Must be exactly `https://localhost:9444/commonauth` |
| `application not found` from IS | Wrong or missing Client ID | Create the IS application (Step 0A.3) and paste the correct Client ID |
| SSL error on IS page | Self-signed cert not accepted | Visit `https://localhost:9444` directly, accept the cert, then retry |
| Stuck on `/callback` page | Code exchange failed | Check backend logs: `docker logs wso2-backend` |

---

## Part 0 — Start the Stack

### Step 0.1 — Build images that have Dockerfiles

```bash
docker compose build backend frontend
```

---

### Step 0.2 — Start all 6 services

```bash
docker compose up -d
```

```bash
docker compose ps
```

All 6 should show `running`:
```
NAME                STATUS
wso2-postgres       running
wso2is-local        running
wso2apim-local      running
wso2-rabbitmq       running
wso2-backend        running
wso2-frontend       running
```

---

### Step 0.3 — Wait for services to be ready

| Service | URL | Ready when... |
|---------|-----|---------------|
| Next.js Frontend | http://localhost:3000 | Login page loads |
| WSO2 IS | https://localhost:9444/console | Login page loads |
| WSO2 APIM | https://localhost:9443/publisher | Publisher page loads |
| RabbitMQ | http://localhost:15672 | Management UI loads |
| FastAPI | http://localhost:8000/health | Returns `{"status":"ok"}` |

> APIM takes the longest (~3 min): `docker logs -f wso2apim-local`
> Ready when you see `[Server startup in XXXX ms]`

---

### Step 0.4 — Create the Lab API

You need one API in APIM to test all Phase 5 & 6 features against.

**Create the API:**

1. Go to https://localhost:9443/publisher
2. Click **Create API → Design a New REST API**
3. Fill in:

   | Field | Value |
   |-------|-------|
   | Name | `LabAPI` |
   | Context | `/lab` |
   | Version | `1.0` |
   | Endpoint | `http://wso2-backend:8000` |

4. Add these 3 resources:

   | Method | Path |
   |--------|------|
   | GET | `/public-resource` |
   | GET | `/secure-resource` |
   | GET | `/reports` |

5. Click **Save and Deploy** → then go to **Lifecycle** → click **Publish**

**Subscribe and get a token:**

1. Go to https://localhost:9443/devportal
2. Find `LabAPI` → click **Subscribe** → choose `DefaultApplication` → click **Subscribe**
3. Go to **Applications → DefaultApplication → Production Keys**
4. Scroll down to **Tokens** → click **Generate Access Token** → copy the token

**Verify the API works:**

```bash
curl -sk https://localhost:8243/lab/1.0/public-resource \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

Expected response:
```json
{
  "message": "This endpoint is public — no JWT required.",
  "gateway": "WSO2 APIM 4.3.0"
}
```

> Replace `YOUR_TOKEN_HERE` with the token you copied. If the token expired, generate a new one in DevPortal.

---

---

## Phase 5 — Gateway Operations & Traffic Control

---

## Step 5.1 — Rate Limiting (Throttling)

**What you are learning:**  
How to protect backend services from overload. APIM enforces a request quota — once exceeded, it returns `429 Too Many Requests` before the request ever reaches the backend.

**Three throttle levels in WSO2 APIM:**

| Level | Scope |
|-------|-------|
| API Level | Limits the entire API across all callers |
| Application Level | Limits one registered app |
| Resource Level | Limits one specific endpoint |

---

**5.1a — Create a Subscription Policy in the Admin UI:**

In APIM 4.3.0, **Subscription Policies** (formerly "Subscription Tiers") control how many requests a subscriber's token can make.

1. Go to https://localhost:9443/admin
2. Navigate to **Rate Limiting Policies → Subscription Policies**
3. Click **Add New Policy**
4. Fill in:

   | Field | Value |
   |-------|-------|
   | Policy Name | `5PerMin` |
   | Description | `5 requests per minute` |
   | Request Count | `5` |
   | Unit Time | `1` |
   | Time Unit | `Minute` |

5. Click **Save**

---

**5.1b — Add the Business Plan to LabAPI:**

In APIM 4.3.0 Publisher, subscription tiers are called **Business Plans** and live under **Portal Configurations** (not Runtime).

1. Publisher → **LabAPI → Portal Configurations**
2. Under **Business Plans** → tick `5PerMin`
3. Click **Save**
4. Go to **Lifecycle** tab → click **Deploy**

**5.1c — Re-subscribe with the throttled tier:**

1. DevPortal → **Subscriptions** (or the API's subscriptions page)
2. If already subscribed with `DefaultApplication`, click the edit (pencil) icon
3. Change Business Plan to `5PerMin` → **Update**

> If the edit option is not available, unsubscribe and re-subscribe choosing `5PerMin` as the tier.

Generate a new token after changing the tier.

---

**5.1d — Test throttling:**

Run this loop (8 requests, limit is 5):

```bash
for i in {1..8}; do
  echo -n "Request $i: "
  curl -sk -o /dev/null -w "%{http_code}\n" \
    https://localhost:8243/lab/1.0/public-resource \
    -H "Authorization: Bearer YOUR_TOKEN_HERE"
done
```

**Expected output:**
```
Request 1: 200
Request 2: 200
Request 3: 200
Request 4: 200
Request 5: 200
Request 6: 429
Request 7: 429
Request 8: 429
```

**What `429` looks like (full response):**
```json
{
  "fault": {
    "code": 900800,
    "message": "Message throttled out",
    "description": "You have exceeded your quota"
  }
}
```

> **Key insight:** APIM returns 429 immediately — the backend never receives those requests. This is what "gateway-level protection" means.

---

## Step 5.2 — Custom Mediation (Header Injection)

**What you are learning:**  
The gateway can intercept and modify traffic without touching backend code. A Synapse XML sequence is a small program that runs inside APIM on every request or response.

The sequence file `config/apim/sequences/custom-header-sequence.xml` is already volume-mounted into the APIM container. You just need to activate it in the Publisher UI.

---

**5.2a — Activate the sequence on LabAPI:**

The sequence XML is already volume-mounted into the APIM container at startup. Activate it in the Publisher UI:

1. Publisher → **LabAPI → Runtime**
2. Scroll to **Message Mediation**
3. Under **Request** → click the pencil (edit) icon
4. Select **Select Existing Sequence**
5. Choose `custom-header-sequence` from the dropdown
6. Click **Save**
7. Re-deploy: **Lifecycle → Deploy**

> **If `custom-header-sequence` does not appear in the dropdown (APIM 4.3.0 may not scan the filesystem automatically):**
>
> Use the **Upload** option instead:
> 1. Under **Request** → click the upload icon
> 2. Select `config/apim/sequences/custom-header-sequence.xml` from your local machine
> 3. Save and re-deploy

---

**5.2b — Verify the header is injected:**

The header is added by APIM on the way *to* the backend — it doesn't appear in your curl response. Check the backend logs to confirm:

```bash
docker logs wso2-backend --tail 20
```

You should see incoming requests logged. To explicitly see headers, call the `/public-resource` endpoint with `-v`:

```bash
curl -sk https://localhost:8243/lab/1.0/public-resource \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" -v 2>&1 | grep -i "x-custom"
```

> **Note:** WSO2 may strip custom headers from the response. The header `X-Custom-Header: WSO2-Gateway` goes to the backend, not back to you. In production you would check your backend access logs.

---

## Step 5.3 — Async Event Handling (RabbitMQ)

**What you are learning:**  
A production API gateway should not handle business events (user registered, app created) in-process. RabbitMQ decouples this: a service publishes an event to a queue, and downstream consumers process it at their own pace — completely independent of the gateway.

> **Important — what WSO2 4.3.0 / 7.0.0 does and does not do natively:**
>
> WSO2 APIM and IS do **not** automatically publish events to RabbitMQ out of the box. The `[[event_handler]]` entry in `config/apim/deployment.toml` is an internal hook for user registration notifications (like sending a confirmation email) — it has no connection to RabbitMQ.
>
> To connect WSO2 to RabbitMQ in a real project, you would write a **custom event handler** (a Java class implementing `AbstractEventHandler`) that reads WSO2 internal events and publishes them to a RabbitMQ queue via the AMQP protocol.
>
> In this lab, we verify that RabbitMQ is running in the stack and learn to operate it. The architecture pattern is correct; the custom publisher is the next coding step beyond this lab.

---

**5.3a — Verify RabbitMQ is running:**

```bash
curl -s http://localhost:15672/api/overview \
  -u guest:guest | grep -o '"product_name":"[^"]*"'
# → "product_name":"RabbitMQ"
```

---

**5.3b — Open the Management UI:**

1. Go to http://localhost:15672
2. Login: `guest` / `guest`
3. Click the **Queues** tab — it will be empty (no publishers yet)
4. Click the **Connections** tab — you can see AMQP connections

---

**5.3c — Manually publish a test message (to understand the flow):**

Use the management UI to simulate what a custom publisher would do:

1. Go to **Queues** tab → **Add a new queue**
2. Name: `wso2.gateway.events`, Durability: `Durable` → **Add queue**
3. Click the queue name → **Publish message**
4. Payload:
   ```json
   {"event": "USER_REGISTERED", "username": "test-user", "timestamp": "2026-06-24T10:00:00Z"}
   ```
5. Click **Publish message**

**5.3d — Read the message back:**

1. Click **Get messages** → Ackmode: `Nack message requeue true` → **Get Message(s)**
2. You see the message payload — this is what a consumer (Python/Node/Java service) would receive

> **What a real integration looks like:**
> ```
> WSO2 IS fires POST_ADD_USER internally
>   → custom event handler (Java) catches it
>   → handler publishes to RabbitMQ queue "wso2.gateway.events"
>   → downstream service consumes the message
> ```
> RabbitMQ itself is working correctly in the stack. The missing piece for a full integration is the custom Java handler inside WSO2.

---

---

## Phase 6 — Advanced Security & Token Engineering

---

## Step 6.1 — Generate mTLS Certificates

**What you are learning:**  
Normal HTTPS = server proves identity to client (one-way TLS).  
Mutual TLS = **both sides** present certificates (two-way TLS).  
A client without a valid certificate is rejected at the TLS handshake — no HTTP code ever runs.

---

**6.1a — Generate the client certificate:**

Run from the project root:

```bash
bash scripts/generate-certs.sh
```

Expected output:
```
→ Generating client private key...
→ Creating certificate signing request...
→ Self-signing the certificate (valid 365 days)...

✓ Certificates written to .../certs/
  client.key  ← private key (gitignored)
  client.csr  ← signing request
  client.crt  ← public certificate
```

Confirm files exist:

```bash
ls certs/
# → client.crt  client.csr  client.key
```

> **Security note:** `certs/*.key` is already in `.gitignore` — private keys are never committed to git.

---

**6.1b — Inspect the certificate (optional):**

```bash
openssl x509 -in certs/client.crt -text -noout | grep -A2 "Subject:"
```

You should see: `CN=wso2-lab-client, O=WSO2, C=US`

---

## Step 6.2 — Enable Per-API Mutual TLS

**Why per-API, not global?**  
Enabling `enable_client_auth = true` globally in `deployment.toml` would require a client cert on ALL HTTPS connections — including the Publisher, Admin, and DevPortal UIs. This breaks your own browser access. Per-API mTLS is the production-correct approach.

---

**6.2a — Upload the client certificate to LabAPI:**

1. Publisher → **LabAPI → Runtime**
2. Scroll down to **Transport Level Security**
3. Toggle on **Mutual SSL**
4. Set mode to **Optional** (cert OR token — easier for testing)
5. Click **Add Certificate**
6. Upload `certs/client.crt`
7. Click **Save**
8. Re-deploy: **Lifecycle → Deploy**

---

**6.2b — Test mTLS enforcement:**

```bash
# Without client cert — should still work (mode is Optional)
curl -sk https://localhost:8243/lab/1.0/public-resource \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# With client cert — succeeds
curl -sk \
  --cert certs/client.crt \
  --key certs/client.key \
  https://localhost:8243/lab/1.0/public-resource \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

Both should return `200`. Now change mode to **Mandatory** and re-test — without the cert it will return `401`.

> **What mTLS prevents:** An attacker who intercepts your token still cannot call the API — they don't have the client certificate.

---

## Step 6.3 — Token Transformation (Opaque → JWT)

**What you are learning:**  
The most important zero-trust pattern for microservices:

```
Client
  │
  │  sends opaque token (a short random string — meaningless to the backend)
  ▼
WSO2 APIM Gateway
  │
  │  1. validates opaque token against WSO2 IS
  │  2. fetches user claims (username, roles, email...)
  │  3. generates a signed JWT containing those claims
  │  4. forwards the request with: X-JWT-Assertion: <signed JWT>
  ▼
FastAPI Backend (backend/main.py)
  │
  │  1. reads X-JWT-Assertion header
  │  2. fetches APIM public keys from https://wso2apim:9443/oauth2/jwks
  │  3. verifies the JWT signature — no call to IS needed
  │  4. reads user claims directly from the verified JWT
  ▼
  ✅ Zero-trust verified request
```

**Why this matters:** The backend trusts the gateway, not the client. The client never holds a JWT — if the token is stolen, it's a short-lived opaque reference, not a self-contained credential.

---

**6.3a — JWT is already enabled**

The config in `config/apim/deployment.toml` has already been uncommented:

```toml
[apim.jwt]
enable = true
encoding = "base64"
header = "X-JWT-Assertion"
signing_algorithm = "SHA256withRSA"
enable_user_claims = true
claim_dialect = "http://wso2.org/claims"
```

No changes needed. APIM was started with this config.

---

**6.3b — Call the secure backend endpoint:**

```bash
curl -sk \
  --cert certs/client.crt \
  --key certs/client.key \
  https://localhost:8243/lab/1.0/secure-resource \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Expected response:**
```json
{
  "message": "Access granted",
  "user": "admin@carbon.super",
  "issuer": "https://localhost:9443/oauth2/token",
  "claims": {
    "sub": "admin@carbon.super",
    "iss": "https://localhost:9443/oauth2/token",
    "http://wso2.org/claims/role": "Internal/everyone,admin",
    "exp": 1234567890,
    "iat": 1234567800
  }
}
```

The backend has:
- Fetched APIM's public keys from the JWKS endpoint
- Verified the JWT cryptographic signature
- Returned the decoded claims

---

**6.3c — Verify the backend rejects direct calls (no JWT injected):**

```bash
curl http://localhost:8000/secure-resource
```

Expected:
```json
{
  "detail": "Missing X-JWT-Assertion header. Ensure the request goes through APIM with JWT generation enabled."
}
```

This proves the backend is protected — it only trusts requests that came through the gateway.

---

**6.3d — Inspect the raw JWT (optional):**

The `X-JWT-Assertion` header is a base64-encoded JWT. You can decode it:

```bash
# Get the raw JWT from APIM
TOKEN=$(curl -sk \
  --cert certs/client.crt \
  --key certs/client.key \
  https://localhost:8243/lab/1.0/secure-resource \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -D - -o /dev/null 2>&1)

# Or paste a JWT at https://jwt.io to decode it visually
```

---

## Step 6.4 — OAuth Scopes Bound to Roles

**What you are learning:**  
Fine-grained authorization: a user can only access an endpoint if their token includes a specific **scope**, and that scope is only granted to users with a specific **role**.

```
Role (IS)     →  "analyst" role assigned to a user
Scope (IS)    →  "read:reports" scope is only granted if user has "analyst" role
Resource (APIM) →  GET /reports requires scope "read:reports"

Result:
  user WITH "analyst" role  →  token includes "read:reports"  →  200 OK
  user WITHOUT "analyst" role  →  token lacks "read:reports"  →  403 Forbidden
```

> **How token + scope + role works in this setup:**
>
> APIM 4.3.0 here uses its **built-in Key Manager** (the `service_url` in deployment.toml is commented out — no IS KM integration). This means:
> - API access tokens are issued by **APIM** (`https://localhost:9443/oauth2/token`)
> - Scopes for API authorization are created in **APIM Publisher** (not IS)
> - IS is only used as the **user store** — it holds users and roles, and APIM authenticates against it for password grant
>
> The flow: APIM receives a password-grant token request → authenticates user against IS → checks if the user's IS roles map to the requested scope (as defined in APIM) → issues the token.

---

**6.4a — Create the `analyst` role in WSO2 IS 7.0.0:**

1. Go to https://localhost:9444/console
2. **User Management → Roles**
3. Click **Add Role**
4. Role Name: `analyst`
5. Click **Next** (skip permissions) → **Finish**

---

**6.4b — Create a test user and assign the role:**

**Create the user:**
1. **User Management → Users**
2. Click **Add User**
3. Fill in:

   | Field | Value |
   |-------|-------|
   | Username | `analyst-user` |
   | Password | `Test@1234` |

4. Click **Finish** (role assignment is a separate step in IS 7.0.0)

**Assign the role to the user (separate step):**
1. **User Management → Users** → click `analyst-user`
2. Go to the **Roles** tab
3. Click **Add Roles** → tick `analyst` → **Save**

---

**6.4c — Create the scope in APIM Publisher (not IS):**

Because APIM uses its built-in KM, scopes for API access control are **Local Scopes** defined inside the API in APIM Publisher — not in IS.

1. Publisher → **LabAPI → Local Scopes**
2. Click **Add New Local Scope**
3. Fill in:

   | Field | Value |
   |-------|-------|
   | Scope Key | `read:reports` |
   | Display Name | `Read Reports` |
   | Roles | `analyst` |

4. Click **Save**

---

**6.4d — Bind the scope to `GET /reports`:**

1. Publisher → **LabAPI → Resources**
2. Expand the `GET /reports` row
3. Under **Operation Scope** (or **OAuth2 Security**) → select `read:reports`
4. Click **Save**
5. Re-deploy: **Lifecycle → Deploy**

---

**6.4e — Get the OAuth client credentials:**

1. DevPortal → **Applications → DefaultApplication → Production Keys**
2. Under **Application Credentials** → note the **Consumer Key** and **Consumer Secret**

---

**6.4f — Test scope enforcement:**

> **Token endpoint is APIM** (`9443`), not IS (`9444`). APIM issues the API access tokens.

**Get token for `analyst-user` (has analyst role → scope granted):**

```bash
curl -sk -X POST https://localhost:9443/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=analyst-user&password=Test%401234&scope=read:reports" \
  -u "CONSUMER_KEY:CONSUMER_SECRET"
```

Copy the `access_token` from the response.

**Call `GET /reports` with analyst token — expect 200:**

```bash
curl -sk \
  --cert certs/client.crt \
  --key certs/client.key \
  https://localhost:8243/lab/1.0/reports \
  -H "Authorization: Bearer ANALYST_TOKEN"
```

**Call `GET /reports` with admin token (no analyst role) — expect 403:**

```bash
# Get admin token first (no scope)
curl -sk -X POST https://localhost:9443/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=admin&password=admin&scope=read:reports" \
  -u "CONSUMER_KEY:CONSUMER_SECRET"

# Use it on the scoped endpoint
curl -sk \
  --cert certs/client.crt \
  --key certs/client.key \
  https://localhost:8243/lab/1.0/reports \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Expected `403` response body:**
```json
{
  "fault": {
    "code": 900910,
    "message": "The access token does not allow you to access the requested resource",
    "description": "User is NOT authorized to access the Resource..."
  }
}
```

---

---

## Phase 7 — IS as External Key Manager (Production Auth)

---

## Step 7.1 — Certificate Exchange (APIM ↔ IS)

APIM communicates with IS over HTTPS using Docker service names. Because IS uses a self-signed certificate, APIM's JVM will reject the connection with `SSLHandshakeException` unless you import the IS certificate into APIM's truststore.

Run the automated script (both containers must be healthy first):

```bash
bash scripts/setup-key-manager.sh
```

What the script does:
1. Exports the IS public certificate from its Java keystore
2. Copies it to the host machine (`is_public.crt`)
3. Imports it into APIM's `client-truststore.jks`
4. Restarts APIM to reload the truststore

> **If APIM still can't reach IS after restart**, check Docker DNS resolution:
> ```bash
> docker exec wso2apim-local nslookup wso2is
> # Should resolve to the IS container IP, not 127.0.0.1
> ```

---

## Step 7.2 — Register IS as Key Manager in APIM Admin Portal

This is a manual one-time step. APIM uses these endpoints to delegate all token operations to IS.

1. Go to `https://localhost:9443/admin`
2. Left menu → **Key Managers** → **Add Key Manager**
3. Fill in exactly:

| Field | Value |
|-------|-------|
| Name | `WSO2 Identity Server` |
| Type | `WSO2 Identity Server` |
| Issuer | `https://wso2is:9444/oauth2/token` |
| Client Registration Endpoint | `https://wso2is:9444/api/identity/oauth2/dcr/v1.1/register` |
| Introspection Endpoint | `https://wso2is:9444/oauth2/introspect` |
| Token Endpoint | `https://wso2is:9444/oauth2/token` |
| Revoke Endpoint | `https://wso2is:9444/oauth2/revoke` |
| UserInfo Endpoint | `https://wso2is:9444/scim2/Me` |
| Authorize Endpoint | `https://wso2is:9444/oauth2/authorize` |
| Scope Management Endpoint | `https://wso2is:9444/api/identity/oauth2/v1.0/scopes` |

4. Click **Save**

> All endpoints use `wso2is` (Docker service name) not `localhost` — these are container-to-container calls inside the Docker network.

---

## Step 7.3 — Enable CORS on LabAPI

The browser now calls the APIM gateway directly (`https://localhost:8243`). APIM must allow CORS from the frontend origin.

1. Publisher → **LabAPI → Runtime**
2. Scroll to **CORS Configuration**
3. Toggle **CORS** on
4. Add `http://localhost:3000` to **Access Control Allow Origins**
5. Click **Save** → re-deploy via **Lifecycle → Deploy**

---

## Step 7.4 — Accept the APIM Gateway SSL Certificate

The browser makes a direct HTTPS call to `https://localhost:8243`. On first use, it will be blocked by the self-signed cert.

1. Visit `https://localhost:8243` in the browser
2. Accept the security warning / proceed anyway
3. You only need to do this once per browser session

---

## Step 7.5 — Test the Production Flow

After login, the frontend sends the IS access_token directly to the APIM gateway:

```
Browser → https://localhost:8243/lab/1.0/public-resource
          Authorization: Bearer <IS access_token>
                ↓
         APIM introspects token with IS (Key Manager)
                ↓
         Backend /public-resource
```

**Verify in browser DevTools:**
1. Login via GitHub
2. Dashboard → click **Test** on any endpoint
3. DevTools → Network tab → look for the request
4. URL should be `https://localhost:8243/lab/1.0/...` (not `localhost:8000`)

**Verify IS introspection is working:**

```bash
# Get your IS access_token (from browser sessionStorage after login)
# Then manually introspect:
curl -sk -X POST https://localhost:9444/oauth2/introspect \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "WSO2_IS_CLIENT_ID:WSO2_IS_CLIENT_SECRET" \
  -d "token=<your_access_token>"
```

Expected:
```json
{ "active": true, "sub": "your-github-username", "exp": 1234567890, ... }
```

---

## Troubleshooting — Phase 7

| Problem | Cause | Fix |
|---------|-------|-----|
| `SSLHandshakeException` in APIM logs | IS cert not trusted | Re-run `bash scripts/setup-key-manager.sh` |
| Key Manager shows `Connection refused` | IS not reachable from APIM | Confirm both on `wso2-network`; check `docker exec wso2apim-local nslookup wso2is` |
| Browser shows CORS error on gateway call | CORS not enabled | Step 7.3 — add `http://localhost:3000` in Publisher → Runtime → CORS |
| Browser blocks `https://localhost:8243` | Self-signed cert | Visit `https://localhost:8243` directly and accept the cert (Step 7.4) |
| `401 Unauthorized` from APIM gateway | IS token not accepted | Confirm Key Manager is saved and APIM was restarted after cert import |
| Frontend calls `localhost:8000` not `:8243` | Missing env var | Add `NEXT_PUBLIC_APIM_GATEWAY_URL=https://localhost:8243` to `frontend/.env.local` |

---

---

## Summary — What You Built

| Milestone | Feature | How it works |
|-----------|---------|-------------|
| 5.1 | Rate Limiting | APIM enforces a request quota; excess calls get 429 before reaching backend |
| 5.2 | Custom Mediation | Synapse XML sequence injects headers into every forwarded request |
| 5.3 | Async Events | APIM publishes lifecycle events to RabbitMQ; consumers are decoupled |
| 6.1 | Client Certificates | openssl generates client.key + client.crt for mTLS |
| 6.2 | Per-API mTLS | APIM verifies client cert at TLS layer before processing the request |
| 6.3 | JWT Transformation | APIM signs a JWT with user claims; backend verifies via JWKS — zero round-trips |
| 6.4 | Scope-Role Binding | Only users with `analyst` role can request `read:reports` scope; APIM enforces per-resource |
| 7.1 | Cert Exchange | IS public cert imported into APIM truststore — enables HTTPS container-to-container trust |
| 7.2 | IS Key Manager | APIM delegates all token operations to IS via DCR + introspection endpoints |
| 7.3 | CORS on Gateway | Browser can call APIM gateway directly from `localhost:3000` |
| 7.4 | Direct Gateway Auth | Frontend sends IS access_token to APIM; no backend proxy; stateless backend |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| APIM not starting | `docker logs wso2apim-local --tail 50` — wait for `Server startup in` |
| Backend shows `keys_loaded: 0` | `docker logs wso2-backend` — APIM JWKS not available yet; call `/health` again after APIM starts |
| `429` immediately on first request | Token may be expired or wrong tier — generate a new token, confirm subscribed with `5PerMin` tier |
| `429` never triggers | Confirm Business Plan is set to `5PerMin` in Portal Configurations and subscription was updated |
| `401 Missing X-JWT-Assertion` | You hit the backend directly (port 8000) instead of through APIM (port 8243) |
| mTLS handshake error | Re-run `bash scripts/generate-certs.sh` and re-upload `client.crt` in Publisher |
| `403` on `/reports` for analyst-user | Scope `read:reports` must be a **Local Scope in APIM Publisher** (not IS), bound to role `analyst`, applied to the resource, and API re-deployed |
| Scope not showing in APIM resources dropdown | Scope must first be created in Publisher → LabAPI → **Local Scopes** before it appears in the Resources tab |
| `custom-header-sequence` not in dropdown | Use the **upload** option in Runtime → Message Mediation → Request instead |
| Token request returns `invalid_scope` | The scope was requested from IS (9444) instead of APIM (9443); use `https://localhost:9443/oauth2/token` |
| IS 7.0.0 user has no role after creation | IS 7.0.0 requires role assignment as a separate step: Users → click user → Roles tab → Add Roles |
