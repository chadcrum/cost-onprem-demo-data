#!/usr/bin/env bash
set -euo pipefail

# Deploy the demo data CronJob to an existing cost-onprem namespace.
#
# Usage:
#   ./deploy.sh                          # Deploy to cost-onprem namespace
#   ./deploy.sh -n my-namespace          # Deploy to custom namespace
#   NAMESPACE=my-ns ./deploy.sh          # Alternative

NAMESPACE="${NAMESPACE:-cost-onprem}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--namespace) NAMESPACE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "==> Deploying demo data CronJob to namespace: ${NAMESPACE}"

# Create ConfigMap from the Python script
echo "  Creating ConfigMap demo-data-script..."
kubectl create configmap demo-data-script \
    --from-file=populate-demo-day.py="${SCRIPT_DIR}/scripts/populate-demo-day.py" \
    -n "${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f - -n "${NAMESPACE}"

# Apply the CronJob
echo "  Applying CronJob..."
kubectl apply -f "${SCRIPT_DIR}/k8s/cronjob.yaml" -n "${NAMESPACE}"

echo ""
echo "==> Done. CronJob 'demo-data' deployed."
echo "    Schedule: midnight UTC (1am CET)"
echo ""
echo "  Manual trigger:"
echo "    kubectl create job demo-data-manual --from=cronjob/demo-data -n ${NAMESPACE}"
echo ""
echo "  Check status:"
echo "    kubectl get cronjob demo-data -n ${NAMESPACE}"
echo "    kubectl get jobs -l app.kubernetes.io/name=demo-data -n ${NAMESPACE}"
