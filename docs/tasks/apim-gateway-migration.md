# APIM Gateway Migration — Task List

Route all frontend traffic through WSO2 APIM (gateway) instead of calling
the FastAPI backend directly, and add local HTTPS with `.local.test`
subdomains using mkcert + nginx.

---

## Architecture decision (settled before execution)

| Concern | Decision |
|---|---|
| Auth endpoints (`/auth/*`) in APIM | **Open / no-auth** — no token exists pre-login |
| Business endpoints (`/lab/1.0/*`) in APIM | **Secured** — Bearer required, APIM validates IS JWT |
| OAuth callback landing point | **Frontend** (`https://portal.local.test/callback`) — keeps current Next.js flow |
| Backend public hostname | **None** — backend is internal-only, reachable only from APIM inside Docker network |

---

## Tasks

### T1 — Generate mkcert certificates
**File(s):** `certs/` directory (new)  
**What:** Run `mkcert` to create trusted local certs for the three `.local.test`
hostnames and copy the mkcert root CA into `./certs`.  
**Command to run (user runs this on host):**
```bash
mkcert -install
mkdir -p certs
mkcert -cert-file certs/local.pem -key-file certs/local-key.pem \
  portal.local.test gateway.local.test is.local.test
cp "$(mkcert -CAROOT)/rootCA.pem" certs/rootCA.pem
```
**Output:** `certs/local.pem`, `certs/local-key.pem`, `certs/rootCA.pem`  
**Status:** ⬜ pending (user must run on host)

---

### T2 — Create nginx/nginx.conf
**File(s):** `nginx/nginx.conf` (new)  
**What:** TLS termination on port 443 for three virtual hosts. Proxy each
to the correct Docker service. Disable upstream SSL verification for
`wso2apim` and `wso2is` (self-signed certs). Set `X-Forwarded-Proto` and
`X-Forwarded-Host` headers.

| Hostname | Upstream |
|---|---|
| `portal.local.test` | `http://frontend:3000` |
| `gateway.local.test` | `https://wso2apim:8243` |
| `is.local.test` | `https://wso2is:9444` |

**Status:** ✅ done — `nginx/nginx.conf` created

---

### T3 — Add nginx service to docker-compose.yml
**File(s):** `docker-compose.yml`  
**What:** Add `nginx` service block — image `nginx:alpine`, bind port
`443:443`, mount `./nginx/nginx.conf` and `./certs`, `depends_on`
frontend / wso2apim / wso2is, on `wso2-network`.  
**Status:** ✅ done

---

### T4 — Update backend env vars in docker-compose.yml
**File(s):** `docker-compose.yml` → `backend` service  
**What:**
- `AUTH_CALLBACK_URL` → `https://portal.local.test/callback`
- `FRONTEND_URL` → `https://portal.local.test`
- Remove exposed port `8000:8000` (backend is internal-only)

**Status:** ✅ done

---

### T5 — Update frontend env vars in docker-compose.yml
**File(s):** `docker-compose.yml` → `frontend` service  
**What:**
- `NEXT_PUBLIC_BACKEND_URL` → `https://gateway.local.test`
  (auth calls now route through APIM, not directly to backend)
- `NEXT_PUBLIC_APIM_GATEWAY_URL` → `https://gateway.local.test`
  (same host — single entry point for everything)

**Status:** ✅ done

---

### T6 — Fix frontend/Dockerfile TLS config
**File(s):** `frontend/Dockerfile`  
**What:** Replace the blanket `NODE_TLS_REJECT_UNAUTHORIZED=0` with
`NODE_EXTRA_CA_CERTS=/certs/rootCA.pem` so Node.js trusts the mkcert
root CA specifically rather than disabling all TLS verification.  
Also add a volume mount for `./certs:/certs` on the `frontend` service in
`docker-compose.yml` so the CA file is available at runtime.  
**Status:** ✅ done

---

### T7 — Consolidate frontend gateway URL in dashboard/page.tsx
**File(s):** `frontend/app/dashboard/page.tsx`  
**What:** Remove the separate `APIM_GATEWAY` constant and its env var
(`NEXT_PUBLIC_APIM_GATEWAY_URL`). All API calls (`/lab/1.0/*`,
`/auth/me`, `/auth/logout`) go through `NEXT_PUBLIC_BACKEND_URL` which is
now the gateway URL. Update the `callApi` fetch URL accordingly.  
**Status:** ✅ done

---

### T8 — Provide /etc/hosts entries
**File(s):** documentation only (no file change)  
**What:** Add the following lines to `/etc/hosts` (WSL) and
`C:\Windows\System32\drivers\etc\hosts` (Windows):

```
127.0.0.1  portal.local.test
127.0.0.1  gateway.local.test
127.0.0.1  is.local.test
```

On WSL run: `echo -e "127.0.0.1  portal.local.test\n127.0.0.1  gateway.local.test\n127.0.0.1  is.local.test" | sudo tee -a /etc/hosts`  
On Windows: open `C:\Windows\System32\drivers\etc\hosts` as Administrator and add the three lines.  
**Status:** ✅ done (docs provided)

---

### T9 — Document APIM API configuration steps
**File(s):** documentation only (no file change)  
**What:** Step-by-step instructions for configuring two APIs in the WSO2
APIM Publisher UI:

#### BackendAuth API (open — no auth)
1. Log in to `https://gateway.local.test/publisher` (or `https://localhost:9443/publisher`)
2. Create a new REST API — name `BackendAuth`, version `1.0`, context `/auth`
3. Add resources: `GET /me`, `POST /login`, `GET /logout` (or wildcard `/*`)
4. Under **Runtime** → **Backend** set endpoint to `http://backend:8000/auth`
5. Under **Runtime** → **Application Level Security** uncheck all — set to **None** (open)
6. Deploy to the Gateway and Publish

#### LabAPI (secured — Bearer / IS JWT)
1. Open the existing LabAPI (context `/lab`) in the Publisher
2. Under **Runtime** → **Backend** verify endpoint is `http://backend:8000` (update if needed)
3. Under **Runtime** → **Application Level Security** ensure **OAuth2** is checked
4. Deploy and Publish (no change needed if already published with correct endpoint)

**Status:** ✅ done (docs provided)

---

## Execution order

```
T1 (certs) ──► T2 (nginx.conf) ──► T3 (add nginx to compose)
                                         │
                              T4 (backend env) ──► T5 (frontend env)
                                                         │
                              T6 (Dockerfile TLS) ────────┤
                                                         │
                              T7 (dashboard.tsx) ────────┘
                                                         │
                                              T8 (hosts) + T9 (APIM docs)
```

T1 requires `mkcert` installed on your host — all other tasks are code/config
changes that can be applied without it, but the stack won't start cleanly
until certs exist.
