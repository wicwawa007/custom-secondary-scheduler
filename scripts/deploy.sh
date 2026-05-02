#!/usr/bin/env bash
set -euo pipefail

NS="$1"
IMAGE="$2"

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
sed -e "s|__NAMESPACE__|${NS}|g" -e "s|__IMAGE__|${IMAGE}|g" manifests/install.yaml | kubectl apply -f -

echo "deployed secondary scheduler into namespace ${NS}"
