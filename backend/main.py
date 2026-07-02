"""
WSO2 Lab Backend — every endpoint here sits behind the APIM gateway
(https://gateway.local.test, LabAPI context /lab/1.0). Nothing calls this
service directly; it has no exposed host port.

Login flow (WSO2 IS as OIDC broker, GitHub as federated IdP):
  Browser → GET /auth/login-url
          → IS authorize URL with fidp=<GitHub connection name>
          → IS skips its login screen, redirects straight to GitHub
          → GitHub auth → IS /commonauth → https://portal.local.test/callback?code=xxx
          → POST /auth/exchange {code} → IS /oauth2/token → access_token + id_token
          → frontend keeps the id_token-derived user profile and sends the
            access_token to the APIM gateway on every call (IS is APIM's Key Manager)

THE ONE RULE for this file: APIM consumes the Authorization header on secured
routes and does NOT forward it — the only caller identity that reaches us is
the X-JWT-Assertion header (a JWT APIM signs after validating the real token).
Any handler that needs the raw access token cannot exist behind this gateway.

Claim shape inside X-JWT-Assertion follows apim.jwt.convert_dialect in
config/apim/deployment.toml — currently `true`, so keys are flat (name, email),
not http://wso2.org/claims/* URIs.
"""

import os
import json
import ssl
import time
import base64
import hashlib
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
IS_URL        = os.getenv("WSO2_IS_URL",        "https://wso2is:9444")     # Docker-internal
IS_PUBLIC_URL = os.getenv("WSO2_IS_PUBLIC_URL", "https://localhost:9444")  # browser-accessible
IS_CLIENT_ID  = os.getenv("WSO2_IS_CLIENT_ID",  "")
IS_CLIENT_SECRET = os.getenv("WSO2_IS_CLIENT_SECRET", "")
GITHUB_IDP_NAME  = os.getenv("GITHUB_IDP_NAME", "github")  # must match IS connection name exactly

APIM_URL = os.getenv("WSO2_APIM_URL", "https://wso2apim:9443")  # for JWKS only

AUTH_CALLBACK_URL = os.getenv("AUTH_CALLBACK_URL", "https://portal.local.test/callback")
FRONTEND_URL      = os.getenv("FRONTEND_URL",      "https://portal.local.test")
APIM_JWKS_URL     = f"{APIM_URL}/oauth2/jwks"

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
_public_keys: dict = {}          # kid → RSA public key
_pending_states: dict[str, tuple[float, str]] = {}  # state → (expiry, code_verifier)
_STATE_TTL = 300  # seconds; abandoned flows (tab closed mid-redirect) are cleaned up on next use


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and its S256 code_challenge."""
    verifier = secrets.token_urlsafe(43)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _add_state(state: str, verifier: str) -> None:
    _pending_states[state] = (time.monotonic() + _STATE_TTL, verifier)


def _consume_state(state: str) -> str | None:
    """Return code_verifier and remove the state if present and not expired, else None."""
    entry = _pending_states.pop(state, None)
    if entry is None or time.monotonic() > entry[0]:
        return None
    now = time.monotonic()
    for k in [k for k, v in _pending_states.items() if v[0] < now]:
        del _pending_states[k]
    return entry[1]

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _load_jwks()
    except Exception as exc:
        print(f"Warning: JWKS pre-load failed ({exc}). Will retry on first request.")
    missing = [v for v in ("WSO2_IS_CLIENT_ID", "WSO2_IS_CLIENT_SECRET") if not os.getenv(v)]
    if missing:
        print(f"WARNING: Required env vars not set: {', '.join(missing)}")
        print("  Auth endpoints will fail. Set these in .env and run: docker compose up -d backend")
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
        # verify_aud=False: APIM's X-JWT-Assertion omits the 'aud' claim by design.
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
        # verify_signature=False: APIM enforces the scope gate upstream; backend only reads claims for display.
        payload = jwt.decode(x_jwt_assertion, options={"verify_signature": False})
        return {
            "message": "Reports access granted — read:reports scope verified by APIM",
            "user": payload.get("sub"),
            "scope": payload.get("scope", "—"),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JWT: {exc}")


# ===========================================================================
# Section 2 — Auth flow (called by frontend, via the gateway)
#
# GET  /auth/login-url  → returns IS authorize URL (fidp skips IS login screen)
# POST /auth/exchange   → exchanges IS code for tokens; returns access_token +
#                         the id_token-derived user profile (frontend stores both)
# GET  /auth/me         → session liveness check; echoes X-JWT-Assertion claims
# ===========================================================================

@app.get("/auth/login-url")
def auth_login_url():
    if not IS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="WSO2_IS_CLIENT_ID not configured.")
    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    _add_state(state, verifier)
    params = urllib.parse.urlencode({
        "response_type":         "code",
        "client_id":             IS_CLIENT_ID,
        "redirect_uri":          AUTH_CALLBACK_URL,
        "scope":                 "openid profile email",
        "state":                 state,
        "fidp":                  GITHUB_IDP_NAME,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })
    return {"url": f"{IS_PUBLIC_URL}/oauth2/authorize?{params}"}


class ExchangeRequest(BaseModel):
    code:  str
    state: str = ""


@app.post("/auth/exchange")
async def auth_exchange(body: ExchangeRequest):
    verifier = _consume_state(body.state)
    if verifier is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter.")

    async with httpx.AsyncClient(verify=False, timeout=httpx.Timeout(10.0)) as client:
        token_res = await client.post(
            f"{IS_URL}/oauth2/token",
            data={
                "grant_type":    "authorization_code",
                "code":          body.code,
                "redirect_uri":  AUTH_CALLBACK_URL,
                "code_verifier": verifier,
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
def auth_me(x_jwt_assertion: str = Header(default=None)):
    # Routed through the secured LabAPI — APIM already validated the caller's token
    # and injects the claims here. No raw Authorization header reaches the backend
    # for secured resources, so we read claims instead of introspecting.
    if not x_jwt_assertion:
        raise HTTPException(status_code=401, detail="Missing X-JWT-Assertion.")
    try:
        payload = jwt.decode(x_jwt_assertion, options={"verify_signature": False})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JWT: {exc}")
    return {
        "sub":   payload.get("sub"),
        "name":  payload.get("name") or payload.get("sub"),
        "email": payload.get("email"),
    }


# No /auth/logout endpoint: revoking at IS needs the raw access token, but APIM
# strips the Authorization header on this secured route, so a backend revoke can
# never receive it. Logout is client-side (frontend clears sessionStorage); the
# IS token simply expires at its natural TTL (~1h).


