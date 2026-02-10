# Cost Management On-Premise - Demo Access Guide

**Deployment:** parodos-dev  
**Date:** 2026-02-05  
**Status:** ✅ Ready for Demo

---

## 🔑 Authentication & Access

### UI Access

**URL:** https://cost-onprem-ui-cost-onprem.apps.stress.parodos.dev

**Keycloak Admin Login:**
- Username: `admin`
- Password: `b978d84cb30147a1b39ec9899ccd535d`
- Keycloak Console: https://keycloak-keycloak.apps.stress.parodos.dev/admin

**Steps to access UI:**
1. Navigate to https://cost-onprem-ui-cost-onprem.apps.stress.parodos.dev
2. You'll be redirected to Keycloak for authentication
3. Login with admin credentials above
4. UI will load with cost management data

---

### API Access (JWT Token)

**Gateway URL:** https://cost-onprem-gateway-cost-onprem.apps.stress.parodos.dev

**Get JWT Token (valid for ~5 minutes):**
```bash
# From your terminal on the cluster
KEYCLOAK_URL="https://keycloak-keycloak.apps.stress.parodos.dev"
SECRET=$(oc get secret keycloak-client-secret-cost-management-operator -n keycloak -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)

TOKEN=$(curl -sk -X POST "$KEYCLOAK_URL/realms/kubernetes/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=cost-management-operator" \
  -d "client_secret=$SECRET" | jq -r '.access_token')

echo "JWT Token: $TOKEN"
```

**Save token for reuse:**
```bash
echo "$TOKEN" > /tmp/jwt-token.txt
# Later: TOKEN=$(cat /tmp/jwt-token.txt)
```

---

## 📊 Available Data (Demo Dataset)

### Clusters

| Cluster ID | Display Name | Data Period | Days | Summary Rows |
|------------|--------------|-------------|------|--------------|
| demo-prod-cluster | Production Cluster | 2026-01-06 to 2026-02-05 | 30 | 62 |
| demo-dev-cluster | Development Cluster | 2026-01-21 to 2026-02-05 | 15 | 32 |
| demo-staging-cluster | Staging Cluster | 2026-01-29 to 2026-02-05 | 7 | 16 |

**Total:** 3 clusters, 110 daily summary rows

### Namespaces (Sample)
- Production Cluster: `production`, `ai-ml`, `monitoring`
- Development Cluster: `development`, `ml-experimentation`, `staging`
- Staging Cluster: `staging`, `mlops-pipeline`, `qa`

---

## 🛠️ API Examples for Demo

### 1. Get API Status
```bash
TOKEN=$(cat /tmp/jwt-token.txt)
GATEWAY="https://cost-onprem-gateway-cost-onprem.apps.stress.parodos.dev"

curl -sk -H "Authorization: Bearer $TOKEN" \
  "$GATEWAY/api/cost-management/v1/status/" | jq -r '{api_version, commit}'
```

**Expected:** `{"api_version": 1, "commit": "undefined"}`

---

### 2. List Sources (Clusters)
```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "$GATEWAY/api/cost-management/v1/sources/" | jq '.data[] | {id, name, source_type}'
```

**Expected:** 3 sources (Production, Development, Staging)

---

### 3. Get Resource Types (Clusters)
```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "$GATEWAY/api/cost-management/v1/resource-types/openshift-clusters/" | jq '.data'
```

**Expected:**
```json
[
  {"cluster_alias": "Development Cluster", "value": "demo-dev-cluster"},
  {"cluster_alias": "Production Cluster", "value": "demo-prod-cluster"},
  {"cluster_alias": "Staging Cluster", "value": "demo-staging-cluster"}
]
```

---

### 4. Get Tags for OpenShift
```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "$GATEWAY/api/cost-management/v1/tags/openshift/" | jq 'keys'
```

---

### 5. Query Database Directly (for demo prep)

**Cost by Cluster and Namespace:**
```bash
oc exec -n cost-onprem cost-onprem-database-0 -- psql -U koku_user -d costonprem_koku -c "
SELECT 
  cluster_id,
  namespace,
  SUM(pod_request_cpu_core_hours)::numeric(10,2) as cpu_hours,
  SUM(pod_request_memory_gigabyte_hours)::numeric(10,2) as mem_gb_hours,
  COUNT(*) as days
FROM orgorg1234567.reporting_ocpusagelineitem_daily_summary
GROUP BY cluster_id, namespace
ORDER BY cluster_id, cpu_hours DESC;
"
```

**Total Summary:**
```bash
oc exec -n cost-onprem cost-onprem-database-0 -- psql -U koku_user -d costonprem_koku -c "
SELECT 
  COUNT(*) as total_rows,
  COUNT(DISTINCT cluster_id) as clusters,
  MIN(usage_start)::date as earliest,
  MAX(usage_start)::date as latest
FROM orgorg1234567.reporting_ocpusagelineitem_daily_summary;
"
```

---

## 🔍 Monitoring & Verification

### Check Processing Status

**Koku Listener (ingress processing):**
```bash
oc logs -n cost-onprem -l app.kubernetes.io/component=listener --tail=50
```

**MASU (cost processing):**
```bash
oc logs -n cost-onprem -l app.kubernetes.io/component=cost-processor --tail=50
```

**ROS Processor (recommendations):**
```bash
oc logs -n cost-onprem -l app.kubernetes.io/component=ros-processor --tail=50 --since=10m
```

---

### Check Kruize Experiments

```bash
cd /Users/jgil/go/src/github.com/insights-onprem/ros-helm-chart
NAMESPACE=cost-onprem ./scripts/query-kruize.sh --experiments
```

**Note:** Experiments may take 5-15 minutes to appear after data upload. ROS processor sends recommendation requests; Kruize creates experiments based on usage patterns.

---

## 🎯 Demo Scenarios

### Scenario 1: Multi-Cluster Cost Visibility
1. Login to UI
2. Navigate to OpenShift Cost dashboard
3. Show dropdown with 3 clusters
4. Select each cluster to show different cost profiles
5. Show aggregate view

### Scenario 2: Namespace-Level Cost Attribution
1. Select Production Cluster (30 days data)
2. View cost breakdown by namespace
3. Show top namespaces: `production`, `ai-ml`, `monitoring`
4. Drill into specific namespace

### Scenario 3: Cost Trends Over Time
1. Select 30-day time range
2. Show cost trend chart for Production cluster
3. Point out peaks/troughs in usage
4. Compare with Development cluster (15 days)

### Scenario 4: Resource Optimization (ROS)
1. Navigate to Recommendations/Optimization tab
2. Show recommendations for clusters (if available)
3. Explain CPU/Memory optimization suggestions
4. Show potential cost savings

**Note:** ROS recommendations depend on Kruize experiments. If not visible yet, check back in 5-10 minutes or show ROS processor logs demonstrating active processing.

### Scenario 5: API Integration
1. Show JWT token acquisition
2. Demonstrate API calls (sources, resource-types, tags)
3. Explain how customers can integrate with their tools
4. Show Keycloak for SSO/authentication

---

## 📝 Quick Reference Commands

### Get New JWT Token
```bash
cd /Users/jgil/go/src/github.com/insights-onprem/ros-helm-chart
TOKEN=$(./scripts/get-jwt-token.sh 2>/dev/null || \
  curl -sk -X POST "https://keycloak-keycloak.apps.stress.parodos.dev/realms/kubernetes/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=cost-management-operator" \
  -d "client_secret=$(oc get secret keycloak-client-secret-cost-management-operator -n keycloak -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)" \
  | jq -r '.access_token')
echo "$TOKEN" > /tmp/jwt-token.txt
```

### Check All Pods
```bash
oc get pods -n cost-onprem -l app.kubernetes.io/instance=cost-onprem
```

### Check Routes
```bash
oc get routes -n cost-onprem
```

### Run Smoke Tests
```bash
cd /Users/jgil/go/src/github.com/insights-onprem/ros-helm-chart/tests
export PATH="/Users/jgil/go/src/github.com/insights-onprem/ros-helm-chart/tests/venv/bin:$PATH"
NAMESPACE=cost-onprem ../tests/venv/bin/pytest -m smoke -v
```

---

## ⚠️ Known Issues / Notes

### ROS Processor Partition Errors
**Symptom:** Logs show `partition not found for resource workload_metrics with org_id org1234567`

**Status:** Known issue; doesn't block recommendation requests. ROS processor successfully sends requests to Kruize.

**Impact:** None for demo; experiments are created based on recommendation requests.

---

### Kruize Experiments Delay
**Expected:** 5-15 minutes after data upload for experiments to appear in Kruize DB.

**Verification:**
```bash
NAMESPACE=cost-onprem ./scripts/query-kruize.sh --experiments
```

If no experiments yet, show ROS processor logs demonstrating active processing and recommendation requests being sent.

---

## 🔄 Troubleshooting

### UI Not Loading
1. Check UI pod: `oc get pods -n cost-onprem -l app.kubernetes.io/component=ui`
2. Check logs: `oc logs -n cost-onprem -l app.kubernetes.io/component=ui`
3. Verify route: `oc get route cost-onprem-ui -n cost-onprem`

### API Returns 401
- Token expired (get new token, valid ~5 min)
- Check Keycloak: `oc get pods -n keycloak`

### No Data in UI
1. Verify DB has data (see "Query Database Directly" above)
2. Check MASU logs for processing completion
3. Verify sources registered: API call #2 above

---

## 📞 Support

For issues during demo:
- Check deployment status: `DEMO-DEPLOYMENT-PLAN.md` (updated with verification results)
- Re-run data generation: `scripts/generate-demo-data.py` (if needed)
- Delete and regenerate sources: `scripts/delete-demo-sources.py` then `generate-demo-data.py`

**Deployment complete:** 2026-02-05 21:48  
**Demo ready:** ✅ Yes (UI, API, 3 clusters with 110 rows of data)
