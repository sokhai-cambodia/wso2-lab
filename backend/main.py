"""
WSO2 Lab Backend — two responsibilities:
  1. API resource endpoints  — called by APIM gateway (receive X-JWT-Assertion header)
  2. Auth endpoints          — called by the Next.js frontend

Login flow (WSO2 IS as OIDC broker, GitHub as federated IdP):
  Browser → GET /auth/login-url
          → IS authorize URL with fidp=<GitHub connection name>
          → IS skips its login screen, redirects straight to GitHub
          → GitHub auth → IS /commonauth → http://localhost:3000/callback?code=xxx
          → POST /auth/exchange {code} → IS /oauth2/token → returns IS access_token to frontend
          → frontend sends IS access_token directly to APIM gateway (IS is APIM's Key Manager)
          → APIM validates token with IS, injects X-JWT-Assertion, forwards to backend

APIM is configured to use IS as its Key Manager — IS tokens are valid at the APIM gateway.
All WSO2 credentials live here. Frontend needs NEXT_PUBLIC_BACKEND_URL + NEXT_PUBLIC_APIM_GATEWAY_URL.
"""

import os
import json
import ssl
import secrets
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager

import httpx
import jwt
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
IS_URL        = os.getenv("WSO2_IS_URL",        "https://wso2is-local:9444")  # Docker-internal
IS_PUBLIC_URL = os.getenv("WSO2_IS_PUBLIC_URL", "https://localhost:9444")     # browser-accessible
IS_CLIENT_ID  = os.getenv("WSO2_IS_CLIENT_ID",  "")
IS_CLIENT_SECRET = os.getenv("WSO2_IS_CLIENT_SECRET", "")
GITHUB_IDP_NAME  = os.getenv("GITHUB_IDP_NAME", "github")  # must match IS connection name exactly

APIM_URL = os.getenv("WSO2_APIM_URL", "https://wso2apim:9443")  # for JWKS only

AUTH_CALLBACK_URL = os.getenv("AUTH_CALLBACK_URL", "http://localhost:3000/callback")
FRONTEND_URL      = os.getenv("FRONTEND_URL",      "http://localhost:3000")
APIM_JWKS_URL     = f"{APIM_URL}/oauth2/jwks"

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
_public_keys: dict = {}    # kid → RSA public key
_pending_states: set = set()  # short-lived OAuth state values for CSRF protection

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _load_jwks()
    except Exception as exc:
        print(f"Warning: JWKS pre-load failed ({exc}). Will retry on first request.")
    yield


app = FastAPI(title="WSO2 Lab Backend", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# JWKS — load APIM signing keys for X-JWT-Assertion verification
# ---------------------------------------------------------------------------
def _load_jwks() -> None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(APIM_JWKS_URL, context=ctx) as resp:
        data = json.loads(resp.read())
    for key_data in data.get("keys", []):
        kid = key_data.get("kid", "default")
        _public_keys[kid] = RSAAlgorithm.from_jwk(json.dumps(key_data))
    print(f"Loaded {len(_public_keys)} APIM signing key(s).")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _get_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    return authorization.removeprefix("Bearer ")


async def _introspect(token: str) -> dict:
    """Validate IS access token and return its claims. Raises 401 if inactive."""
    async with httpx.AsyncClient(verify=False) as client:
        res = await client.post(
            f"{IS_URL}/oauth2/introspect",
            data={"token": token},
            auth=(IS_CLIENT_ID, IS_CLIENT_SECRET),
        )
    data = res.json()
    if not data.get("active"):
        raise HTTPException(status_code=401, detail="Token inactive or expired. Please log in again.")
    return data


# ===========================================================================
# Health
# ===========================================================================

@app.get("/health")
def health():
    return {"status": "ok", "signing_keys_loaded": len(_public_keys)}


# ===========================================================================
# Section 1 — API resource endpoints (called by APIM gateway)
# APIM validates the opaque token, then forwards the request here with
# X-JWT-Assertion containing a signed JWT of the caller's claims.
# ===========================================================================

@app.get("/public-resource")
def public_resource():
    return {"message": "This endpoint is public — no JWT required.", "gateway": "WSO2 APIM 4.3.0"}


@app.get("/secure-resource")
def secure_resource(x_jwt_assertion: str = Header(default=None)):
    if not x_jwt_assertion:
        raise HTTPException(
            status_code=401,
            detail="Missing X-JWT-Assertion. Request must come through APIM with jwt.enable=true.",
        )
    if not _public_keys:
        try:
            _load_jwks()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Cannot load signing keys: {exc}")

    try:
        unverified_header = jwt.get_unverified_header(x_jwt_assertion)
    except jwt.DecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed JWT: {exc}")

    kid = unverified_header.get("kid", "default")
    public_key = _public_keys.get(kid) or next(iter(_public_keys.values()), None)
    if not public_key:
        raise HTTPException(status_code=503, detail="No APIM signing key available.")

    try:
        payload = jwt.decode(
            x_jwt_assertion, public_key,
            algorithms=["RS256"], options={"verify_aud": False},
        )
        return {
            "message": "Access granted",
            "user": payload.get("sub"),
            "issuer": payload.get("iss"),
            "claims": payload,
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


@app.get("/reports")
def reports(x_jwt_assertion: str = Header(default=None)):
    # APIM enforces read:reports scope before forwarding here — scope check already passed.
    if not x_jwt_assertion:
        raise HTTPException(status_code=401, detail="Missing X-JWT-Assertion.")
    try:
        payload = jwt.decode(x_jwt_assertion, options={"verify_signature": False})
        return {
            "message": "Reports access granted — read:reports scope verified by APIM",
            "user": payload.get("sub"),
            "scope": payload.get("scope", "—"),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JWT: {exc}")


# ===========================================================================
# Section 2 — Auth flow (called by frontend)
#
# GET  /auth/login-url  → returns IS authorize URL (fidp skips IS login screen)
# POST /auth/exchange   → exchanges IS code for tokens, returns IS access_token to frontend
# GET  /auth/me         → introspects IS token, returns user claims
# GET  /auth/logout     → revokes IS token
# ===========================================================================

@app.get("/auth/login-url")
def auth_login_url():
    if not IS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="WSO2_IS_CLIENT_ID not configured.")
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id":     IS_CLIENT_ID,
        "redirect_uri":  AUTH_CALLBACK_URL,
        "scope":         "openid profile email",
        "state":         state,
        "fidp":          GITHUB_IDP_NAME,
    })
    return {"url": f"{IS_PUBLIC_URL}/oauth2/authorize?{params}"}


class ExchangeRequest(BaseModel):
    code:  str
    state: str = ""


@app.post("/auth/exchange")
async def auth_exchange(body: ExchangeRequest):
    if body.state not in _pending_states:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter.")
    _pending_states.discard(body.state)

    async with httpx.AsyncClient(verify=False) as client:
        token_res = await client.post(
            f"{IS_URL}/oauth2/token",
            data={
                "grant_type":   "authorization_code",
                "code":         body.code,
                "redirect_uri": AUTH_CALLBACK_URL,
            },
            auth=(IS_CLIENT_ID, IS_CLIENT_SECRET),
        )
    tokens = token_res.json()

    if "access_token" not in tokens:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {tokens}")

    payload = jwt.decode(tokens["id_token"], options={"verify_signature": False})
    user = {
        "sub":   payload.get("sub"),
        "name":  payload.get("username") or payload.get("nickname") or payload.get("given_name") or payload.get("sub"),
        "email": payload.get("email"),
    }

    return {
        "access_token": tokens["access_token"],
        "expires_in":   tokens.get("expires_in"),
        "user":         user,
    }


@app.get("/auth/me")
async def auth_me(authorization: str = Header(default=None)):
    token = _get_bearer(authorization)
    claims = await _introspect(token)
    return {
        "sub":   claims.get("sub"),
        "name":  claims.get("username") or claims.get("sub"),
        "email": claims.get("email"),
    }


@app.get("/auth/logout")
async def auth_logout(authorization: str = Header(default=None)):
    token = _get_bearer(authorization)
    async with httpx.AsyncClient(verify=False) as client:
        await client.post(
            f"{IS_URL}/oauth2/revoke",
            data={"token": token},
            auth=(IS_CLIENT_ID, IS_CLIENT_SECRET),
        )
    return {"ok": True}


