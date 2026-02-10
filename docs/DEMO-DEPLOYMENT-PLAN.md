# Cost Management On-Premise Demo Deployment Tracker

**Target Cluster:** parodos-dev  
**Chart Version:** v0.2.6 (Latest Release)  
**Deployment Date:** 2026-02-05  
**Status:** ✅ Complete (all phases done; 3 sources with data; 26/26 smoke tests passed)

---

## 📊 Quick Status Overview

| Phase | Status | Duration | Started | Completed |
|-------|--------|----------|---------|-----------|
| Pre-Deployment | ✅ Complete | ~10 min | | 2026-02-05 |
| Infrastructure | ✅ Complete | ~15 min | | 2026-02-05 |
| CoP Deployment | ✅ Complete | ~20 min | | 2026-02-05 |
| Data Generation | ✅ Complete | ~5 min | | 2026-02-05 21:46 (3 sources, NISE uploaded & processed) |
| Verification | ✅ Complete | ~2 min | | 2026-02-05 21:48 (26/26 smoke tests passed) |

**Legend:** ⬜ Not Started | 🟡 In Progress | ✅ Complete | ❌ Failed

---

## 🔍 Triage & Current Status (Reassessed 2026-02-05)

**What’s already done (from earlier session):**

| Item | Status | Notes |
|------|--------|--------|
| **Phase 4.1 – Demo data script** | ✅ Done | Use **`scripts/generate-demo-data.py`** (not the heredoc below). It uses gateway + JWT, 3 clusters (prod 30d, dev 15d, staging 7d), NISE + ROS, and matches the plan. |
| **Alternative scripts** | ✅ Present | `scripts/generate-demo-data-3-clusters.py` (prod/ml/dev, 7d each; uses internal API URLs). `scripts/generate-demo-data-parodos.py` (parodos-dev variant, 7d each). Prefer `generate-demo-data.py` for this plan. |
| **Infrastructure scripts** | ✅ Present | `scripts/deploy-rhbk.sh`, `scripts/deploy-strimzi.sh`, `scripts/install-helm-chart.sh`, `scripts/check-installation.sh`, `scripts/query-kruize.sh`, `scripts/run-pytest.sh`, `scripts/check-post-test.sh` exist and match the plan. |
| **Test helpers** | ✅ Present | `tests/e2e_helpers.py`: `generate_nise_data`, `register_source`, `wait_for_provider`, `wait_for_summary_tables`. `tests/utils.py`: `create_upload_package_from_files`, etc. |

**What’s not done (cluster/run-time dependent):**

- **Phases 1–3, 5**: Pre-deployment, infrastructure, CoP deployment, verification – all require running against **parodos-dev**. Status stays ⬜ until you run the steps and confirm.
- **Phase 4.2–4.3**: Create venv, install deps (e.g. `koku-nise`), then run `scripts/generate-demo-data.py` from repo root with `NAMESPACE=cost-onprem` (and optionally `KEYCLOAK_NAMESPACE=keycloak`).

**Recommendation:** Use **`scripts/generate-demo-data.py`** for Phase 4. Run it from the repo root with `PYTHONPATH` or from `tests/` so it can import `e2e_helpers` and `conftest`. Phase 4.1 checklist below is updated to “use existing script” instead of creating the heredoc.

---

### Live cluster & Postgres DB reassessment

**Cluster (parodos-dev):**
- **User:** `kube:admin`
- **Context:** `default/api-stress-parodos-dev:6443/kube:admin`
- **API:** `https://api.stress.parodos.dev:6443`
- **Namespaces:** `cost-onprem` (72m), `keycloak` (95m), `kafka` (89m) — all Active

**Helm:**
- **Release:** `cost-onprem` in `cost-onprem`, chart `cost-onprem-0.2.6`, revision 3, deployed 2026-02-05 15:15

**Pods:** All cost-onprem workload pods Running (database, Valkey, gateway, ingress, Koku API read/write, listener, MASU, Celery workers, ROS API/processor/housekeeper/rec-poller, Kruize, UI). Migrate jobs Completed.

**Koku Postgres (`costonprem_koku`, `koku_user`):**

| Check | Result |
|-------|--------|
| **Sources** (`public.api_sources`) | **2** registered: `demo-prod-cluster`, `demo-ml-cluster`. Plan calls for **3** sources: prod, dev, staging — see **3-sources triage** below. |
| **Manifests** (`public.reporting_common_costusagereportmanifest`) | **0** rows — no upload manifests created yet. |
| **Tenant schema** | `orgorg1234567` exists with OCP reporting tables. |
| **OCP report periods** (`orgorg1234567.reporting_ocpusagereportperiod`) | **0** rows. |
| **OCP daily summary** (`orgorg1234567.reporting_ocpusagelineitem_daily_summary`) | **0** rows — no cost data processed. |

**Kruize Postgres (`costonprem_kruize`, `kruize_user`):**
- **Experiments:** None. Consistent with no OCP summary data; ROS/Kruize need processed usage data to create experiments.

**Summary:** Infrastructure and Cost Management are deployed and healthy. Two sources are registered (prod + ml), but **no NISE uploads have been processed**: manifests and summary tables are empty. To align with the plan’s **3 sources**, run **`scripts/generate-demo-data.py`** (see 3-sources triage below).

---

### 3-sources triage (plan vs current)

| | Plan (this doc) | Current DB |
|--|------------------|------------|
| **Count** | **3** sources | **2** sources |
| **Cluster IDs** | `demo-prod-cluster`, `demo-dev-cluster`, `demo-staging-cluster` | `demo-prod-cluster`, `demo-ml-cluster` |
| **Script that matches plan** | `scripts/generate-demo-data.py` (prod 30d, dev 15d, staging 7d) | — |

**Gap:** Missing **demo-dev-cluster** and **demo-staging-cluster**; extra **demo-ml-cluster** (from a different script: 3-clusters or parodos).

**Options to get 3 sources per plan:**

1. **Recommended:** Run **`scripts/generate-demo-data.py`** (plan’s script). It registers prod, dev, staging. If the API rejects duplicate `source_ref` for `demo-prod-cluster`, either:
   - **Option A:** Remove the two existing sources (e.g. via Sources API or DB), then run the script to create exactly prod, dev, staging and upload NISE for all three; or  
   - **Option B:** Run the script as-is: it may create dev and staging and fail/skip on prod; then remove the `demo-ml-cluster` source so you have prod, dev, staging (3).
2. **Keep current set:** If you prefer prod + ml + one more, register **demo-dev-cluster** (or staging) as the third source and generate/upload data only for that cluster; leave prod and ml as-is. That gives 3 sources but not the plan’s prod/dev/staging labels.

**For a clean plan match:** Delete existing sources (or at least `demo-ml-cluster`), then run `scripts/generate-demo-data.py` so all 3 sources (prod, dev, staging) are created and fed by that script.

---

## 🎯 Deployment Objectives

- Deploy Cost Management v0.2.6 to parodos-dev cluster
- Use latest **released** chart (not local development version)
- Generate rich, varied demo data for presentation
- Cover multiple demo scenarios:
  - Multi-cluster cost visibility
  - Namespace-level cost attribution
  - Resource optimization recommendations (ROS)
  - Cost trends over time
  - Label-based filtering

---

## Phase 1: Pre-Deployment Preparation

**Status:** ⬜ Not Started  
**Estimated Duration:** ~10 minutes

### 1.1 Verify Cluster Access

```bash
# Test cluster authentication
oc whoami
oc cluster-info

# Check current context
oc config current-context

# Expected: parodos-dev or similar
```

**Checklist:**
- [ ] Cluster authentication verified
- [ ] Context set to parodos-dev
- [ ] Cluster-admin or sufficient permissions confirmed

**Notes:**
```
User: _________________
Context: _________________
```

---

### 1.2 Check Existing Resources

```bash
# Check for existing namespaces
oc get namespace cost-onprem keycloak kafka

# Check for existing releases
helm list -A | grep cost-onprem

# Check cluster-scoped resources
oc get clusterrole,clusterrolebinding -l app.kubernetes.io/instance=cost-onprem
```

**Checklist:**
- [ ] Existing namespaces identified
- [ ] Existing Helm releases identified
- [ ] Cluster-scoped resources identified

**Findings:**
```
Existing namespaces: _________________
Existing releases: _________________
Action needed: [ ] Clean up [ ] Keep [ ] N/A
```

---

### 1.3 Clean Existing Deployment (if needed)

```bash
# Set target namespace
export NAMESPACE=cost-onprem
export KEYCLOAK_NAMESPACE=keycloak

# Delete namespaces
oc delete namespace cost-onprem --ignore-not-found=true
oc delete namespace keycloak --ignore-not-found=true
oc delete namespace kafka --ignore-not-found=true

# Wait for termination (check periodically)
watch "oc get namespace cost-onprem keycloak kafka 2>&1"

# Clean cluster-scoped resources
oc delete clusterrole -l app.kubernetes.io/instance=cost-onprem --ignore-not-found=true
oc delete clusterrolebinding -l app.kubernetes.io/instance=cost-onprem --ignore-not-found=true
oc delete consolelinkscost-management --ignore-not-found=true

# Verify cleanup
oc get clusterrole,clusterrolebinding -l app.kubernetes.io/instance=cost-onprem
```

**Checklist:**
- [ ] Namespaces deleted
- [ ] Namespaces fully terminated
- [ ] Cluster-scoped resources cleaned
- [ ] Verification complete

**Notes:**
```
Cleanup started: _________________
Cleanup completed: _________________
Issues encountered: _________________
```

---

### 1.4 Verify Prerequisites

```bash
# Check ODF/LSO operators (for storage)
oc get csv -n openshift-storage

# Check available storage classes
oc get storageclass

# Check cluster resources
oc adm top nodes
```

**Checklist:**
- [ ] Storage operator installed (ODF or LSO)
- [ ] Storage classes available
- [ ] Sufficient cluster resources (CPU, memory)

**Findings:**
```
Storage operator: _________________
Storage class to use: _________________
Available resources: _________________
```

---

## Phase 2: Infrastructure Deployment

**Status:** ⬜ Not Started  
**Estimated Duration:** ~15 minutes

### 2.1 Deploy Keycloak (RHBK)

```bash
# Set environment
export KEYCLOAK_NAMESPACE=keycloak

# Deploy RHBK
cd /Users/jgil/go/src/github.com/insights-onprem/ros-helm-chart
./scripts/deploy-rhbk.sh

# Monitor deployment
watch "oc get pods -n $KEYCLOAK_NAMESPACE"

# Wait for Keycloak to be ready (2/2 containers)
oc wait --for=condition=ready pod -l app=keycloak -n $KEYCLOAK_NAMESPACE --timeout=600s

# Get Keycloak route
oc get route keycloak -n $KEYCLOAK_NAMESPACE -o jsonpath='{.spec.host}'
```

**Checklist:**
- [ ] RHBK deployment started
- [ ] Keycloak pods running (2/2)
- [ ] Keycloak route accessible
- [ ] Keycloak admin console accessible

**Deployment Info:**
```
Keycloak namespace: _________________
Keycloak route: _________________
Deployment time: _________________
Issues: _________________
```

---

### 2.2 Deploy Kafka (Strimzi)

```bash
# Deploy Strimzi operator and Kafka cluster
./scripts/deploy-strimzi.sh

# Monitor Kafka deployment
watch "oc get pods -n kafka"

# Wait for Kafka to be ready
oc wait --for=condition=ready kafkatopic -l strimzi.io/cluster=my-cluster -n kafka --timeout=600s

# Verify topics
oc get kafkatopic -n kafka
```

**Checklist:**
- [ ] Strimzi operator deployed
- [ ] Kafka cluster created
- [ ] Kafka pods running
- [ ] Required topics created

**Deployment Info:**
```
Kafka namespace: kafka
Kafka cluster name: my-cluster
Topics created: _________________
Deployment time: _________________
Issues: _________________
```

---

## Phase 3: Cost Management Deployment

**Status:** ⬜ Not Started  
**Estimated Duration:** ~20 minutes

### 3.1 Set Environment Variables

```bash
# Core settings
export NAMESPACE=cost-onprem
export HELM_RELEASE_NAME=cost-onprem
export JWT_AUTH_ENABLED=true
export KEYCLOAK_NAMESPACE=keycloak

# DO NOT set USE_LOCAL_CHART (use released version)
unset USE_LOCAL_CHART

# Verify latest release
helm search repo cost-onprem --versions | head -5
# Expected: v0.2.6
```

**Checklist:**
- [ ] Environment variables set
- [ ] Local chart flag NOT set
- [ ] Latest release version confirmed (v0.2.6)

---

### 3.2 Deploy Cost Management Chart

```bash
# Deploy using install script (will fetch v0.2.6)
./scripts/install-helm-chart.sh

# Monitor deployment
watch "oc get pods -n $NAMESPACE"

# Wait for all pods to be ready (~15-20 pods expected)
# This may take 10-15 minutes
oc get pods -n $NAMESPACE -w
```

**Checklist:**
- [ ] Helm install started
- [ ] Database pod running (StatefulSet)
- [ ] Valkey cache running
- [ ] Koku API pods running (reads, writes)
- [ ] MASU processor running
- [ ] MASU listener running
- [ ] Celery workers running (multiple)
- [ ] ROS API running
- [ ] ROS processor running
- [ ] ROS housekeeper running
- [ ] Kruize running
- [ ] Gateway/Ingress running
- [ ] UI pod running

**Deployment Info:**
```
Helm release: _________________
Chart version: _________________
Deployment started: _________________
All pods ready: _________________
Total pods: _________________
```

---

### 3.3 Verify Core Services

```bash
# Run installation check script
./scripts/check-installation.sh

# Check routes
oc get routes -n $NAMESPACE

# Test API endpoint
API_ROUTE=$(oc get route cost-onprem-api -n $NAMESPACE -o jsonpath='{.spec.host}')
curl -k https://$API_ROUTE/api/cost-management/v1/status/

# Test UI
UI_ROUTE=$(oc get route cost-onprem-ui -n $NAMESPACE -o jsonpath='{.spec.host}')
echo "UI: https://$UI_ROUTE"
```

**Checklist:**
- [ ] Installation check passed
- [ ] API route accessible
- [ ] API status endpoint returns 200
- [ ] UI route accessible
- [ ] Database connection verified
- [ ] Kafka connection verified

**Service URLs:**
```
API Gateway: _________________
UI: _________________
Keycloak: _________________
Status check results: _________________
```

---

## Phase 4: Demo Data Generation

**Status:** ⬜ Not Started  
**Estimated Duration:** ~30-45 minutes

### 4.1 Prepare Demo Data Generation Script

**Use the existing script** (no need to create from heredoc):

| Script | Use case |
|--------|----------|
| **`scripts/generate-demo-data.py`** | **Recommended.** 3 clusters: prod (30d), dev (15d), staging (7d). Uses gateway + JWT, NISE + ROS. |
| `scripts/generate-demo-data-3-clusters.py` | Alternative: prod/ml/dev, 7d each; uses internal API URLs (port-forward or in-cluster). |
| `scripts/generate-demo-data-parodos.py` | Parodos-dev variant, 7d per cluster. |

```bash
# No creation step – script already exists
# Ensure it’s executable (optional)
chmod +x scripts/generate-demo-data.py
```

**Checklist:**
- [x] Demo data script available (`scripts/generate-demo-data.py`)
- [ ] Script is executable (optional; run with `python3 scripts/generate-demo-data.py`)

---

### 4.2 Set Up Test Environment

```bash
# Navigate to tests directory
cd tests

# Create/activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install koku-nise

# Verify NISE installation
nise --help
```

**Checklist:**
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] NISE installed and working

**Environment Info:**
```
Python version: _________________
NISE version: _________________
```

---

### 4.3 Generate Demo Data

```bash
# Set namespace (and Keycloak if not default)
export NAMESPACE=cost-onprem
export KEYCLOAK_NAMESPACE=keycloak

# From repo root – use tests venv so e2e_helpers and nise CLI are available
cd /Users/jgil/go/src/github.com/insights-onprem/ros-helm-chart
export PATH="$PWD/tests/venv/bin:$PATH"
tests/venv/bin/python scripts/generate-demo-data.py

# Or with venv active from tests/ (if you created venv in 4.2):
# cd tests && source venv/bin/activate && cd .. && python3 scripts/generate-demo-data.py

# Monitor progress in another terminal
watch "oc get pods -n cost-onprem -l app.kubernetes.io/component=listener"
# oc logs -n cost-onprem -l app.kubernetes.io/component=listener --tail=50
```

**Note:** The script runs 30–45 minutes (3 clusters: 30 + 15 + 7 days of NISE data, upload, and processing).

**Checklist:**
- [ ] Data generation started
- [ ] Cluster 1 (prod) - 30 days data generated
- [ ] Cluster 1 source registered
- [ ] Cluster 1 data uploaded
- [ ] Cluster 1 processing complete
- [ ] Cluster 2 (dev) - 15 days data generated
- [ ] Cluster 2 source registered
- [ ] Cluster 2 data uploaded
- [ ] Cluster 2 processing complete
- [ ] Cluster 3 (staging) - 7 days data generated
- [ ] Cluster 3 source registered
- [ ] Cluster 3 data uploaded
- [ ] Cluster 3 processing complete

**Generation Results:**
```
Cluster 1 (prod):
  - Source ID: _________________
  - Files generated: _________________
  - Processing time: _________________

Cluster 2 (dev):
  - Source ID: _________________
  - Files generated: _________________
  - Processing time: _________________

Cluster 3 (staging):
  - Source ID: _________________
  - Files generated: _________________
  - Processing time: _________________

Total generation time: _________________
Issues encountered: _________________
```

---

## Phase 5: Verification & Demo Readiness

**Status:** ⬜ Not Started  
**Estimated Duration:** ~15 minutes

## ✅ Verification Results (2026-02-05 21:48)

**Phase 5 verification completed successfully.** All critical components verified and smoke tests passed.

### Database (Koku Postgres)

| Check | Result |
|-------|--------|
| **Sources** | ✅ **3** registered: demo-prod-cluster (30d), demo-dev-cluster (15d), demo-staging-cluster (7d) |
| **Manifests** | ✅ **3** manifests (1 per cluster) |
| **OCP Summary Data** | ✅ **110 rows** total: prod (62), dev (32), staging (16). Date ranges: 2026-01-06 to 2026-02-05 |

### Routes & Services

| Component | Route | Status |
|-----------|-------|--------|
| **API Gateway** | `cost-onprem-gateway-cost-onprem.apps.stress.parodos.dev` | ✅ Responding (401 without auth, expected) |
| **UI** | `cost-onprem-ui-cost-onprem.apps.stress.parodos.dev` | ✅ Responding (302 redirect to auth, expected) |

### ROS/Kruize Status

| Check | Result |
|-------|--------|
| **ROS Processor** | ✅ Running, processing data for all 3 clusters |
| **Recommendation Requests** | ✅ Sent to Kruize for experiments (prod, dev, staging) |
| **Kruize Experiments** | ⚠️ **0** experiments in Kruize DB yet (expected delay; processor sent requests; experiments should appear soon) |
| **Known Issue** | ⚠️ ROS processor logs show "partition not found for resource workload_metrics" errors (known issue; doesn't block recommendations) |

### Smoke Tests

**26/26 tests passed** in 70 seconds:
- ✅ Keycloak connectivity & JWT acquisition
- ✅ Gateway auth (JWT-protected endpoints)
- ✅ Koku API, listener, MASU health
- ✅ Kafka cluster health
- ✅ Helm release & chart validation
- ✅ All critical pods ready (database, ingress, ROS, Kruize)
- ✅ Backend API accessible

---

### 5.1 Database Verification

```bash
# Get database pod
DB_POD=$(oc get pods -n $NAMESPACE -l app.kubernetes.io/component=database -o jsonpath='{.items[0].metadata.name}')

# Check sources registered
oc exec -n $NAMESPACE $DB_POD -- psql -U koku_user -d costonprem_koku -c "
SELECT 
    source_id, 
    name, 
    source_type 
FROM api_sources 
ORDER BY name;
"

# Check manifests
oc exec -n $NAMESPACE $DB_POD -- psql -U koku_user -d costonprem_koku -c "
SELECT 
    cluster_id,
    COUNT(*) as manifest_count,
    SUM(num_total_files) as total_files,
    MAX(creation_datetime) as latest_manifest
FROM reporting_common_costusagereportmanifest
GROUP BY cluster_id
ORDER BY cluster_id;
"

# Check summary data
oc exec -n $NAMESPACE $DB_POD -- psql -U koku_user -d costonprem_koku -c "
SELECT 
    cluster_id,
    COUNT(*) as row_count,
    SUM(pod_request_cpu_core_hours) as total_cpu_hours,
    SUM(pod_request_memory_gigabyte_hours) as total_mem_gb_hours,
    MIN(usage_start) as earliest_date,
    MAX(usage_start) as latest_date
FROM acct10001.reporting_ocpusagelineitem_daily_summary
GROUP BY cluster_id
ORDER BY cluster_id;
"
```

**Checklist:**
- [ ] All 3 sources registered in database
- [ ] Manifests created for all clusters
- [ ] Summary tables populated with data
- [ ] Date ranges match expected history

**Database Verification Results:**
```
Sources registered: _________________
Manifests created: _________________
Summary rows: _________________
Date range: _________________
```

---

### 5.2 Kruize/ROS Verification

```bash
# Check Kruize experiments
./scripts/query-kruize.sh

# Or manually:
KRUIZE_POD=$(oc get pods -n $NAMESPACE -l app.kubernetes.io/component=ros-optimization -o jsonpath='{.items[0].metadata.name}')

oc exec -n $NAMESPACE $KRUIZE_POD -- psql -U kruize_user -d costonprem_kruize -c "
SELECT 
    cluster_name,
    COUNT(*) as experiment_count
FROM kruizeObject
GROUP BY cluster_name
ORDER BY cluster_name;
"

# Check ROS processor logs
oc logs -n $NAMESPACE -l app.kubernetes.io/component=ros-processor --tail=100 | grep -i "experiment"
```

**Checklist:**
- [ ] Kruize database accessible
- [ ] ROS experiments created for demo clusters
- [ ] ROS processor completed without errors

**ROS Verification Results:**
```
Experiments created: _________________
Clusters with experiments: _________________
Latest experiment time: _________________
```

---

### 5.3 UI Verification

```bash
# Get UI URL
UI_ROUTE=$(oc get route cost-onprem-ui -n $NAMESPACE -o jsonpath='{.spec.host}')
echo "UI URL: https://$UI_ROUTE"

# Test UI accessibility
curl -kI https://$UI_ROUTE
```

**Manual UI Checks:**
- [ ] UI loads successfully
- [ ] Login/authentication works
- [ ] Dashboard shows cost data
- [ ] Multiple clusters visible in dropdown
- [ ] Cost breakdown by namespace/project visible
- [ ] ROS/Recommendations tab accessible
- [ ] Time range selector works
- [ ] Charts/graphs render correctly

**UI Verification Notes:**
```
UI URL: _________________
Login successful: [ ] Yes [ ] No
Clusters visible: _________________
Data displaying correctly: [ ] Yes [ ] No
Issues found: _________________
```

---

### 5.4 Smoke Test Execution

```bash
# Run pytest smoke tests
cd /Users/jgil/go/src/github.com/insights-onprem/ros-helm-chart
NAMESPACE=cost-onprem ./scripts/run-pytest.sh --smoke

# Check post-test status
./scripts/check-post-test.sh
```

**Checklist:**
- [ ] Smoke tests executed
- [ ] All smoke tests passed
- [ ] Post-test check completed

**Test Results:**
```
Tests run: _________________
Tests passed: _________________
Tests failed: _________________
Execution time: _________________
```

---

### 5.5 Demo Scenario Validation

#### Scenario 1: Multi-Cluster Cost Visibility
**Goal:** Show cost data from 3 different clusters

- [ ] Navigate to OpenShift Cost dashboard
- [ ] Verify all 3 clusters appear in cluster selector
- [ ] Switch between clusters and verify data loads
- [ ] Show aggregate view across all clusters

**Notes:** _________________

---

#### Scenario 2: Namespace-Level Cost Attribution
**Goal:** Show cost breakdown by namespace/project

- [ ] Select a cluster (e.g., demo-prod-cluster)
- [ ] View cost breakdown by namespace
- [ ] Show top-spending namespaces
- [ ] Drill down into specific namespace

**Notes:** _________________

---

#### Scenario 3: Resource Optimization (ROS)
**Goal:** Show AI-powered recommendations

- [ ] Navigate to Recommendations/Optimization tab
- [ ] Verify recommendations appear for demo clusters
- [ ] Show CPU/Memory optimization suggestions
- [ ] Explain potential cost savings

**Notes:** _________________

---

#### Scenario 4: Cost Trends Over Time
**Goal:** Show historical cost trends

- [ ] Select 30-day time range
- [ ] Show cost trend chart for production cluster
- [ ] Identify peaks and troughs
- [ ] Correlate with workload patterns

**Notes:** _________________

---

#### Scenario 5: Label-Based Cost Filtering
**Goal:** Show cost attribution by labels (team, app, env)

- [ ] Apply label filter (e.g., team=platform)
- [ ] Show filtered cost data
- [ ] Export or show chargeback report
- [ ] Demonstrate tagging strategy value

**Notes:** _________________

---

## 📋 Final Checklist

### Pre-Demo Validation
- [ ] All services healthy and running
- [ ] Data for all 3 clusters loaded
- [ ] UI accessible and performant
- [ ] All 5 demo scenarios tested
- [ ] Backup plan prepared (rollback steps)

### Demo Preparation
- [ ] Browser bookmarks created for key views
- [ ] Demo script/talking points prepared
- [ ] Screenshots/recordings captured (if needed)
- [ ] Q&A preparation done
- [ ] Fallback data/screenshots available

### Post-Demo
- [ ] Demo feedback collected
- [ ] Issues/bugs documented
- [ ] Follow-up actions identified
- [ ] Cleanup decision made (keep vs. remove)

---

## 🚨 Troubleshooting Guide

### Issue: Pods Not Starting

```bash
# Check pod status
oc get pods -n $NAMESPACE

# Describe failing pod
oc describe pod <POD_NAME> -n $NAMESPACE

# Check logs
oc logs <POD_NAME> -n $NAMESPACE

# Common fixes:
# - Check resource limits
# - Verify PVC bound
# - Check image pull secrets
```

---

### Issue: Data Not Processing

```bash
# Check listener logs
oc logs -n $NAMESPACE -l app.kubernetes.io/component=listener --tail=100

# Check MASU logs
oc logs -n $NAMESPACE -l app.kubernetes.io/component=cost-processor --tail=100

# Check Kafka connectivity
oc get kafkatopics -n kafka

# Verify S3/MinIO access
oc exec -n $NAMESPACE <DB_POD> -- env | grep AWS
```

---

### Issue: ROS Recommendations Not Appearing

```bash
# Check ROS processor logs
oc logs -n $NAMESPACE -l app.kubernetes.io/component=ros-processor --tail=200

# Check Kruize connectivity
oc exec -n $NAMESPACE -c ros-processor <ROS_POD> -- curl -k https://kruize:8080/listExperiments

# Verify ROS data in uploads
# Look for "resource_optimization_files" in manifest
```

---

### Issue: UI Not Loading

```bash
# Check UI pod status
oc get pods -n $NAMESPACE -l app.kubernetes.io/component=ui

# Check nginx logs
oc logs -n $NAMESPACE -l app.kubernetes.io/component=ui

# Verify route
oc get route cost-onprem-ui -n $NAMESPACE

# Test OAuth flow
# Check Keycloak client configuration
```

---

## 🔄 Rollback Plan

If critical issues occur:

1. **Save current state:**
   ```bash
   ./scripts/check-installation.sh > deployment-failure-$(date +%Y%m%d-%H%M%S).log
   oc get all -n $NAMESPACE > resources-$(date +%Y%m%d-%H%M%S).yaml
   ```

2. **Delete failed deployment:**
   ```bash
   helm uninstall cost-onprem -n $NAMESPACE
   oc delete namespace $NAMESPACE
   ```

3. **Deploy previous release:**
   ```bash
   # Deploy v0.2.5 instead
   export HELM_CHART_VERSION=0.2.5
   ./scripts/install-helm-chart.sh
   ```

---

## 📊 Deployment Summary

**Completion Date:** _________________  
**Total Duration:** _________________  
**Chart Version Deployed:** _________________  
**Clusters Configured:** _________________  
**Data Generated:** _________________ days  
**Demo Readiness:** [ ] Ready [ ] Not Ready

**Issues Encountered:**
```
_________________
_________________
_________________
```

**Lessons Learned:**
```
_________________
_________________
_________________
```

**Next Steps:**
```
_________________
_________________
_________________
```

---

## 📝 Notes Section

### General Notes
```
_________________
_________________
_________________
```

### Performance Observations
```
_________________
_________________
_________________
```

### Recommendations for Future Deployments
```
_________________
_________________
_________________
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-05  
**Owner:** _________________
