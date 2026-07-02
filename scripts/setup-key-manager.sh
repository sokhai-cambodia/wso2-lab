#!/bin/bash
# Sets up WSO2 IS as the external Key Manager for WSO2 APIM.
# Run once after both containers are healthy.
set -euo pipefail

echo "→ Extracting IS public certificate..."
docker exec wso2is-local keytool -exportcert \
  -alias wso2carbon \
  -keystore /home/wso2carbon/wso2is-7.0.0/repository/resources/security/wso2carbon.jks \
  -storepass wso2carbon \
  -file /tmp/is_public.crt

echo "→ Copying certificate to host..."
docker cp wso2is-local:/tmp/is_public.crt ./is_public.crt

echo "→ Injecting IS certificate into APIM Java truststore..."
docker cp ./is_public.crt wso2apim-local:/tmp/is_public.crt
docker exec wso2apim-local keytool -importcert \
  -alias wso2is_trusted_cluster \
  -keystore /home/wso2carbon/wso2am-4.3.0/repository/resources/security/client-truststore.jks \
  -storepass wso2carbon \
  -file /tmp/is_public.crt \
  -noprompt

echo "→ Restarting APIM to load updated trust parameters..."
docker restart wso2apim-local

echo ""
echo "✓ Certificate exchange complete. APIM now trusts WSO2 IS over HTTPS."
echo ""
echo "Manual step remaining — configure IS as Key Manager in APIM Admin Portal:"
echo "  1. https://localhost:9443/admin → Key Managers → Add Key Manager"
echo "  2. Type: WSO2 Identity Server"
echo "  3. Issuer:              https://wso2is:9444/oauth2/token"
echo "  4. Client Reg Endpoint: https://wso2is:9444/api/identity/oauth2/dcr/v1.1/register"
echo "  5. Introspection:       https://wso2is:9444/oauth2/introspect"
echo "  6. Token Endpoint:      https://wso2is:9444/oauth2/token"
echo "  7. Revoke Endpoint:     https://wso2is:9444/oauth2/revoke"
echo "  8. UserInfo Endpoint:   https://wso2is:9444/oauth2/userinfo"
echo "  9. Authorize Endpoint:  https://wso2is:9444/oauth2/authorize"
echo " 10. Scope Mgmt:          https://wso2is:9444/api/identity/oauth2/v1.0/scopes"
echo "  → Save"
echo ""
echo "Then enable CORS on LabAPI:"
echo "  Publisher → LabAPI → Runtime → CORS → allow http://localhost:3000"
