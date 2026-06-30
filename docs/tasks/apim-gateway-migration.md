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
**Status:** ⬜ pending

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

**Status:** ⬜ pending

---

### T3 — Add nginx service to docker-compose.yml
**File(s):** `docker-compose.yml`  
**What:** Add `nginx` service block — image `nginx:alpine`, bind port
`443:443`, mount `./nginx/nginx.conf` and `./certs`, `depends_on`
frontend / wso2apim / wso2is, on `wso2-network`.  
**Status:** ⬜ pending

---

### T4 — Update backend env vars in docker-compose.yml
**File(s):** `docker-compose.yml` → `backend` service  
**What:**
- `AUTH_CALLBACK_URL` → `https://portal.local.test/callback`
- `FRONTEND_URL` → `https://portal.local.test`
- Remove exposed port `8000:8000` (backend is internal-only)

**Status:** ⬜ pending

---

### T5 — Update frontend env vars in docker-compose.yml
**File(s):** `docker-compose.yml` → `frontend` service  
**What:**
- `NEXT_PUBLIC_BACKEND_URL` → `https://gateway.local.test`
  (auth calls now route through APIM, not directly to backend)
- `NEXT_PUBLIC_APIM_GATEWAY_URL` → `https://gateway.local.test`
  (same host — single entry point for everything)

**Status:** ⬜ pending

---

### T6 — Fix frontend/Dockerfile TLS config
**File(s):** `frontend/Dockerfile`  
**What:** Replace the blanket `NODE_TLS_REJECT_UNAUTHORIZED=0` with
`NODE_EXTRA_CA_CERTS=/certs/rootCA.pem` so Node.js trusts the mkcert
root CA specifically rather than disabling all TLS verification.  
Also add a volume mount for `./certs:/certs` on the `frontend` service in
`docker-compose.yml` so the CA file is available at runtime.  
**Status:** ⬜ pending

---

### T7 — Consolidate frontend gateway URL in dashboard/page.tsx
**File(s):** `frontend/app/dashboard/page.tsx`  
**What:** Remove the separate `APIM_GATEWAY` constant and its env var
(`NEXT_PUBLIC_APIM_GATEWAY_URL`). All API calls (`/lab/1.0/*`,
`/auth/me`, `/auth/logout`) go through `NEXT_PUBLIC_BACKEND_URL` which is
now the gateway URL. Update the `callApi` fetch URL accordingly.  
**Status:** ⬜ pending

---

### T8 — Provide /etc/hosts entries
**File(s):** documentation only (no file change)  
**What:** Print the exact lines to add to `/etc/hosts` on both WSL
(`/etc/hosts`) and Windows (`C:\Windows\System32\drivers\etc\hosts`) for
the three `.local.test` hostnames pointing to `127.0.0.1`.  
**Status:** ⬜ pending

---

### T9 — Document APIM API configuration steps
**File(s):** documentation only (no file change)  
**What:** Step-by-step instructions for configuring two APIs in the WSO2
APIM Publisher UI:
1. **BackendAuth API** — context `/auth`, security None (open), backend
   endpoint `http://backend:8000`
2. **LabAPI** — context `/lab`, security OAuth2 (existing), backend
   endpoint `http://backend:8000` (change from whatever it currently points
   to if needed)

**Status:** ⬜ pending

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
