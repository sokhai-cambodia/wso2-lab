#!/usr/bin/env bash
# Generates a self-signed client certificate for mTLS testing against WSO2 APIM.
# Run once from the repo root: bash scripts/generate-certs.sh
# Output lands in certs/ — private keys are gitignored.

set -euo pipefail

CERTS_DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"
mkdir -p "$CERTS_DIR"

echo "→ Generating client private key..."
openssl genrsa -out "$CERTS_DIR/client.key" 2048

echo "→ Creating certificate signing request..."
openssl req -new \
  -key "$CERTS_DIR/client.key" \
  -out "$CERTS_DIR/client.csr" \
  -subj "/CN=wso2-lab-client/O=WSO2/C=US"

echo "→ Self-signing the certificate (valid 365 days)..."
openssl x509 -req \
  -days 365 \
  -in "$CERTS_DIR/client.csr" \
  -signkey "$CERTS_DIR/client.key" \
  -out "$CERTS_DIR/client.crt"

echo ""
echo "✓ Certificates written to $CERTS_DIR/"
echo "  client.key  ← private key (gitignored)"
echo "  client.csr  ← signing request"
echo "  client.crt  ← public certificate"
echo ""
echo "Next steps:"
echo "  1. Import client.crt into APIM via Publisher → API → Runtime → Mutual SSL"
echo "  2. Test: curl --cert certs/client.crt --key certs/client.key -k https://localhost:8243/YOUR-API/v1/resource"
