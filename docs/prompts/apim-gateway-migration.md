I need to refactor my Docker Compose setup so the Next.js frontend calls 
WSO2 APIM as the gateway, instead of calling the FastAPI backend directly. 
I also need local HTTPS with proper subdomains to test cookie behavior 
correctly. Here is my current docker-compose.yml — use these exact 
service names, do not assume anything different:

[paste your docker-compose.yml here]

## Current (incorrect) architecture

- frontend calls backend directly: NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
- wso2apim is only used for separate resource APIs via X-JWT-Assertion, 
  not for the auth flow or general frontend traffic

## Target architecture

- frontend should call wso2apim for ALL backend traffic — both the auth 
  flow (login-url, callback/exchange, refresh) AND business APIs — 
  instead of hitting `backend` directly
- wso2apim proxies these requests through to `backend` (APIM acts as the 
  single entry point / gateway in front of FastAPI)
- backend still owns the WSO2 IS client credentials and does the actual 
  GitHub OIDC exchange with wso2is-local — that logic doesn't change, 
  only how the frontend reaches it (via APIM, not directly)

## What I need you to do

1. First, explain what's needed in WSO2 APIM to expose `backend`'s auth 
   endpoints (e.g. /auth/login-url, /auth/callback, /auth/refresh) as a 
   published API in APIM — including whether these specific endpoints 
   need to be unauthenticated/"open" in APIM (since no access token 
   exists yet pre-login), versus the rest of backend's business endpoints 
   which should require a valid Bearer token validated by APIM.

2. Update the relevant frontend environment variable so all calls 
   (currently going to NEXT_PUBLIC_BACKEND_URL) instead go to APIM's 
   gateway URL. Show me exactly which frontend code/env vars need to 
   change.

3. Update backend's AUTH_CALLBACK_URL and FRONTEND_URL to reflect that 
   the callback URL the browser hits will now be reached via APIM's 
   gateway hostname, not backend's own port directly — clarify whether 
   the callback should still land on the frontend (Next.js API route) 
   or on APIM-fronted backend directly, and explain the tradeoff briefly 
   before deciding.

## Then, layer in local HTTPS testing

Use the .test reserved TLD with these hostnames:
   - portal.local.test   → frontend
   - gateway.local.test  → wso2apim (now the single entry point for 
                            everything frontend calls)
   - is.local.test       → wso2is-local

(backend no longer needs a public hostname once APIM fronts it — confirm 
this and don't expose it via nginx unless I tell you otherwise)

1. Generate local trusted certs with mkcert covering portal.local.test, 
   gateway.local.test, and is.local.test, output to ./certs, and copy the 
   mkcert root CA into that same directory.

2. Add an nginx service to docker-compose.yml that terminates TLS on 443 
   and reverse-proxies each hostname to the correct service by Docker 
   Compose service name, with proper X-Forwarded-Proto/Host headers, and 
   disabled upstream SSL verification for wso2is-local and wso2apim 
   (self-signed certs).

3. Update frontend and backend environment variables to use the new 
   https://*.local.test hostnames instead of localhost.

4. Give me exact /etc/hosts entries for both WSL and Windows.

5. Check frontend's Dockerfile for NODE_TLS_REJECT_UNAUTHORIZED=0 and 
   replace it with NODE_EXTRA_CA_CERTS pointing at the mounted mkcert 
   root CA.

## Before making changes

Walk me through the APIM configuration plan first (which endpoints get 
published as "open" vs "secured" APIs) since that's the part most likely 
to need adjustment based on how I've already set up APIM. Then show me 
the docker-compose.yml diff and nginx.conf before applying anything. Ask 
me to confirm before modifying any existing service's environment 
variables, ports, or APIM API definitions.