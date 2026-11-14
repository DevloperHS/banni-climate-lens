#!/usr/bin/env bash
# Usage: ./deploy/deploy.sh v5
# Student account: ACR Tasks band hain, isliye local docker build + push.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:?Usage: ./deploy/deploy.sh <naya-tag>   e.g. v5}"
RG=banni-rg
APP=banni-app

ACR=$(az acr list -g "$RG" --query "[0].name" -o tsv)
[ -n "$ACR" ] || { echo "ACR nahi mila. az login karo."; exit 1; }
IMG="$ACR.azurecr.io/banni-climate-lens:$TAG"
FQDN=$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)

TAGS=$(az acr repository show-tags -n "$ACR" --repository banni-climate-lens -o tsv || true)
if grep -qx "$TAG" <<<"$TAGS"; then
  echo "Tag '$TAG' registry mein pehle se hai. Naya tag do. Maujood tags:"; echo "$TAGS"; exit 1
fi

echo "==> 1/4 Build $IMG"
docker build --provenance=false --sbom=false -t "$IMG" .

echo "==> 2/4 Registry login + push"
az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv \
  | docker login "$ACR.azurecr.io" -u "$ACR" --password-stdin >/dev/null
docker push "$IMG"

echo "==> 3/4 Container app update"
az containerapp update -g "$RG" -n "$APP" --image "$IMG" -o none

echo "==> 4/4 Health check (20s baad)"
sleep 20
curl -s "https://$FQDN/api/health"; echo
echo "Done: https://$FQDN  (browser mein Ctrl+Shift+R karo)"
