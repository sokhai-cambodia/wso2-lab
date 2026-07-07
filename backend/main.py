"""
WSO2 Lab Backend — every endpoint here sits behind the APIM gateway
(https://gateway.local.test, LabAPI context /lab/1.0). Nothing calls this
service directly; it has no exposed host port.

Login flow (WSO2 IS as OIDC broker; GitHub and Microsoft as federated IdPs):
  Browser → GET /auth/login-url            (GitHub)
         or GET /auth/login-url/microsoft  (Microsoft Entra ID)
          → IS authorize URL with fidp=<IS connection name>
          → IS skips its login screen, redirects straight to that IdP
          → IdP auth → IS /commonauth → https://portal.local.test/callback?code=xxx
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

GATEWAY_MODE=false (standalone / no-gateway mode): the browser calls this
service directly and THE ONE RULE no longer applies — there is no APIM in
front, so the backend becomes the trust boundary itself. Secured endpoints then
read the raw `Authorization: Bearer` JWT and verify its signature against the
IdP's JWKS. Works with any external WSO2 IS — Asgardeo, cloud, or dev/UAT
on-prem — as long as it issues JWT access tokens. See docker-compose.standalone.yml.
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
GITHUB_IDP_NAME    = os.getenv("GITHUB_IDP_NAME", "github")  # must match IS connection name exactly
MICROSOFT_IDP_NAME = os.getenv("MICROSOFT_IDP_NAME", "Microsoft")  # must match IS connection name exactly

APIM_URL = os.getenv("WSO2_APIM_URL", "https://wso2apim:9443")  # for JWKS only

AUTH_CALLBACK_URL = os.getenv("AUTH_CALLBACK_URL", "https://portal.local.test/callback")
FRONTEND_URL      = os.getenv("FRONTEND_URL",      "https://portal.local.test")

# true  → behind APIM: caller identity arrives as X-JWT-Assertion (signed by APIM)
# false → no gateway (e.g. Asgardeo): backend verifies the raw Bearer JWT itself
GATEWAY_MODE = os.getenv("GATEWAY_MODE", "true").lower() != "false"

# Where the signing keys for incoming tokens live, per mode
TOKEN_JWKS_URL = f"{APIM_URL}/oauth2/jwks" if GATEWAY_MODE else f"{IS_URL}/oauth2/jwks"

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
# JWKS — signing keys for incoming-token verification (APIM's keys in gateway
# mode, the IdP's own keys in no-gateway mode)
# ---------------------------------------------------------------------------
def _load_jwks() -> None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(TOKEN_JWKS_URL, context=ctx) as resp:
        data = json.loads(resp.read())
    for key_data in data.get("keys", []):
        kid = key_data.get("kid", "default")
        _public_keys[kid] = RSAAlgorithm.from_jwk(json.dumps(key_data))
    print(f"Loaded {len(_public_keys)} signing key(s) from {TOKEN_JWKS_URL}.")


def _verify_jwt(token: str) -> dict:
    """Verify a JWT's signature/expiry against the loaded JWKS and return claims."""
    if not _public_keys:
        try:
            _load_jwks()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Cannot load signing keys: {exc}")
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed JWT: {exc}")
    kid = unverified_header.get("kid", "default")
    public_key = _public_keys.get(kid) or next(iter(_public_keys.values()), None)
    if not public_key:
        raise HTTPException(status_code=503, detail="No signing key available.")
    try:
        # verify_aud=False: APIM's X-JWT-Assertion omits 'aud'; Asgardeo sets it
        # to the client_id, which isn't a secret worth gating on in this lab.
        return jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


def _caller_claims(x_jwt_assertion: str | None, authorization: str | None, verify: bool) -> dict:
    """Resolve caller claims for the current mode.

    Gateway mode: claims come from X-JWT-Assertion; `verify` controls whether we
    check APIM's signature (the gateway already validated the real token, so
    unverified reads are acceptable for display-only endpoints).
    No-gateway mode: claims always come from the raw Bearer token and are always
    signature-verified — the backend is the trust boundary here.
    """
    if GATEWAY_MODE:
        if not x_jwt_assertion:
            raise HTTPException(
                status_code=401,
                detail="Missing X-JWT-Assertion. Request must come through APIM with jwt.enable=true.",
            )
        if verify:
            return _verify_jwt(x_jwt_assertion)
        try:
            return jwt.decode(x_jwt_assertion, options={"verify_signature": False})
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JWT: {exc}")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer token.")
    return _verify_jwt(authorization[len("Bearer "):])


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
def secure_resource(x_jwt_assertion: str = Header(default=None), authorization: str = Header(default=None)):
    payload = _caller_claims(x_jwt_assertion, authorization, verify=True)
    return {
        "message": "Access granted",
        "user": payload.get("sub"),
        "issuer": payload.get("iss"),
        "claims": payload,
    }


@app.get("/reports")
def reports(x_jwt_assertion: str = Header(default=None), authorization: str = Header(default=None)):
    # Gateway mode: APIM already enforced the read:reports scope upstream, claims
    # are display-only. No-gateway mode: the backend IS the scope gate.
    payload = _caller_claims(x_jwt_assertion, authorization, verify=False)
    scope = payload.get("scope", "")
    if not GATEWAY_MODE and "read:reports" not in scope.split():
        raise HTTPException(status_code=403, detail="Missing required scope: read:reports")
    return {
        "message": "Reports access granted — read:reports scope verified by "
                   + ("APIM" if GATEWAY_MODE else "backend"),
        "user": payload.get("sub"),
        "scope": scope or "—",
    }


# ===========================================================================
# Section 2 — Auth flow (called by frontend, via the gateway)
#
# GET  /auth/login-url            → returns IS authorize URL, fidp=GitHub
# GET  /auth/login-url/microsoft  → same, fidp=Microsoft
#                         (fidp skips IS's login screen for that connection)
# POST /auth/exchange   → exchanges IS code for tokens; returns access_token +
#                         the id_token-derived user profile (frontend stores both)
# GET  /auth/me         → session liveness check; echoes X-JWT-Assertion claims
# ===========================================================================

def _build_login_url(idp_name: str) -> dict:
    if not IS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="WSO2_IS_CLIENT_ID not configured.")
    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    _add_state(state, verifier)
    query = {
        "response_type":         "code",
        "client_id":             IS_CLIENT_ID,
        "redirect_uri":          AUTH_CALLBACK_URL,
        "scope":                 "openid profile email",
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    }
    # Empty IdP name → no fidp param → the IdP shows its own login page with
    # every configured sign-in option (useful for Asgardeo's hosted login).
    if idp_name:
        query["fidp"] = idp_name
    params = urllib.parse.urlencode(query)
    return {"url": f"{IS_PUBLIC_URL}/oauth2/authorize?{params}"}


@app.get("/auth/login-url")
def auth_login_url():
    return _build_login_url(GITHUB_IDP_NAME)


@app.get("/auth/login-url/microsoft")
def auth_login_url_microsoft():
    return _build_login_url(MICROSOFT_IDP_NAME)


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
def auth_me(x_jwt_assertion: str = Header(default=None), authorization: str = Header(default=None)):
    # Gateway mode: APIM already validated the caller's token and injects claims
    # via X-JWT-Assertion. No-gateway mode: verify the raw Bearer token instead.
    payload = _caller_claims(x_jwt_assertion, authorization, verify=False)
    return {
        "sub":   payload.get("sub"),
        "name":  payload.get("name") or payload.get("sub"),
        "email": payload.get("email"),
    }


# No /auth/logout endpoint: revoking at IS needs the raw access token, but APIM
# strips the Authorization header on this secured route, so a backend revoke can
# never receive it. Logout is client-side (frontend clears sessionStorage); the
# IS token simply expires at its natural TTL (~1h).


