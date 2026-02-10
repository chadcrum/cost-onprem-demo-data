# cost-onprem-demo-data

Synthetic demo data generator for **Red Hat Cost Management On-Premise**.

Populates the Cost Management UI with realistic cost, CPU/memory, volume, and
network data by inserting directly into the PostgreSQL summary tables that the
UI reads from.  Bypasses the normal Celery processing pipeline so you have full
control over the values shown in the demo.

## Directory Structure

```
cost-onprem-demo-data/
├── helpers/                 # Shared Python utilities (extracted from test infra)
│   ├── config.py            # ClusterConfig, KeycloakConfig, JWT helpers
│   ├── oc_utils.py          # oc/kubectl wrappers, DB queries, pod exec
│   ├── packaging.py         # Upload package (tar.gz) creation
│   ├── nise_utils.py        # NISE data generation
│   └── e2e_utils.py         # Source registration, wait functions
├── scripts/                 # Data generation scripts
│   ├── populate-demo-day.py # ★ Primary: daily CronJob data generator
│   ├── generate-demo-data.py
│   ├── generate-demo-data-3-clusters.py
│   ├── generate-demo-data-parodos.py
│   ├── generate-varied-demo-monthly.py
│   ├── generate-february-demo.py
│   ├── generate-multi-cluster-snapshot.py
│   ├── generate-realistic-demo-data.py
│   ├── generate-realistic-demo-data-v2.py
│   ├── generate-truly-varied-demo-data.py
│   ├── generate-varied-demo-data-parallel.py
│   ├── add-january-data.py
│   ├── delete-demo-sources.py
│   ├── insert-8-cluster-demo.py
│   └── quick-insert-8-clusters.sh
├── nise-configs/            # NISE static report YAML templates
│   ├── static-prod-ecommerce.yml
│   ├── static-dev-devops.yml
│   ├── static-staging-loadtest.yml
│   └── varied-workload-template.yml
├── sql/                     # Direct SQL insert scripts
│   ├── populate-demo-data.sql
│   └── populate-ros-demo-data.sql
├── k8s/                     # Kubernetes manifests for CronJob deployment
│   ├── cronjob.yaml
│   └── configmap.yaml
├── docs/                    # Guides and plans
│   ├── DEMO-ACCESS-GUIDE.md
│   ├── DEMO-DEPLOYMENT-PLAN.md
│   └── cronjob-README.md
├── deploy.sh                # One-command CronJob deployment
├── requirements.txt
├── .gitignore
└── README.md
```

## Quick Start

### Prerequisites

- OpenShift cluster with cost-onprem Helm chart deployed
- `oc` CLI logged in to the cluster
- Python 3.10+

### 1. Install dependencies

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Backfill historical data (one-time)

The primary script `scripts/populate-demo-day.py` inserts data directly into
the partitioned summary tables.  Use `--backfill-from` / `--backfill-to` to
seed historical data:

```bash
# Backfill the last 30 days
python3 scripts/populate-demo-day.py \
    --backfill-from 2026-01-06 \
    --backfill-to 2026-02-05 \
    --verbose
```

This populates **10 tables** per day per cluster:

| Table | Description |
|-------|-------------|
| `reporting_ocp_cost_summary_p` | Cluster-level cost roll-ups |
| `reporting_ocp_cost_summary_by_project_p` | Per-namespace cost breakdown |
| `reporting_ocp_pod_summary_p` | Cluster-level CPU/memory + storage |
| `reporting_ocp_pod_summary_by_project_p` | Per-namespace CPU/memory + storage |
| `reporting_ocp_pod_summary_by_node_p` | Per-node CPU/memory |
| `reporting_ocp_volume_summary_p` | Cluster-level PVC storage |
| `reporting_ocp_volume_summary_by_project_p` | Per-namespace PVC storage |
| `reporting_ocp_network_summary_p` | Cluster-level network I/O |
| `reporting_ocp_network_summary_by_project_p` | Per-namespace network I/O |
| `reporting_ocp_network_summary_by_node_p` | Per-node network I/O |

### 3. Deploy daily CronJob

Once the backfill is done, deploy a CronJob that runs at midnight UTC (1am CET)
to add each new day's data automatically:

```bash
./deploy.sh -n cost-onprem
```

**Manual trigger:**

```bash
kubectl create job demo-data-manual --from=cronjob/demo-data -n cost-onprem
```

## Data Model

The generator creates 3 demo clusters with realistic weekly traffic patterns:

| Cluster | Base Cost/Day | Namespaces | Nodes | PVCs |
|---------|--------------|------------|-------|------|
| Production Cluster | ~$85 | 4 (frontend, backend-api, database, monitoring) | 3 | 4 |
| Development Cluster | ~$42 | 4 (dev-workspace, ci-cd, code-review, testing) | 2 | 3 |
| Staging Cluster | ~$28 | 4 (staging-app, load-testing, qa-validation, redis-cache) | 2 | 3 |

### Weekly Pattern

Day-of-week multipliers create realistic usage curves:

| Day | Multiplier | Rationale |
|-----|-----------|-----------|
| Monday | 1.05 | Ramp-up |
| Tuesday | 1.12 | Peak building |
| Wednesday | 1.18 | Mid-week peak |
| Thursday | 1.10 | Slight decline |
| Friday | 0.92 | Wind-down |
| Saturday | 0.48 | Weekend low |
| Sunday | 0.52 | Weekend low |

A random variance of ±4% is applied on top, plus consideration of the
previous 2 days' actual values to create smooth, non-flat curves.

### Cost Breakdown

Costs are split into realistic components:

- **Infrastructure raw cost** (~55%): Base compute charges
- **Infrastructure markup** (~8.25%): Management overhead
- **Infrastructure usage (CPU)** (~10%): CPU-based metering
- **Infrastructure usage (Memory)** (~10%): Memory-based metering
- **Supplementary cost** (~16.75%): Network, support, etc.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `cost-onprem-database` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `costonprem_koku` | Database name |
| `DB_USER` | `koku_user` | Database user |
| `DB_PASSWORD` | *(none)* | Database password |
| `DB_SCHEMA` | `orgorg1234567` | Tenant schema |
| `VALKEY_HOST` | `cost-onprem-valkey` | Valkey/Redis host |
| `VALKEY_PORT` | `6379` | Valkey/Redis port |
| `NAMESPACE` | `cost-onprem` | K8s namespace (for NISE-based scripts) |
| `HELM_RELEASE_NAME` | `cost-onprem` | Helm release name |
| `KEYCLOAK_NAMESPACE` | `keycloak` | Keycloak namespace |

## Script Categories

### Direct DB Insert (recommended for demos)

These bypass the processing pipeline entirely:

- **`scripts/populate-demo-day.py`** - Primary daily generator with weekly patterns
- **`scripts/insert-8-cluster-demo.py`** - Quick 8-cluster seeding
- **`scripts/quick-insert-8-clusters.sh`** - Bash variant of above
- **`sql/populate-demo-data.sql`** - Raw SQL for Koku tables
- **`sql/populate-ros-demo-data.sql`** - Raw SQL for ROS tables

### NISE Pipeline (uses real processing)

These generate data via NISE and upload through the gateway API:

- **`scripts/generate-demo-data.py`** - Basic 3-cluster generator
- **`scripts/generate-demo-data-3-clusters.py`** - Enhanced 3-cluster with varied profiles
- **`scripts/generate-demo-data-parodos.py`** - Parodos-dev optimized variant
- **`scripts/generate-varied-demo-monthly.py`** - Monthly separated uploads
- **`scripts/generate-february-demo.py`** - February 2026 specific
- **`scripts/generate-multi-cluster-snapshot.py`** - 8-cluster snapshot
- **`scripts/generate-realistic-demo-data.py`** - Uses static YAML templates
- **`scripts/generate-realistic-demo-data-v2.py`** - Programmatic CSV variation
- **`scripts/generate-truly-varied-demo-data.py`** - Period-based variations
- **`scripts/generate-varied-demo-data-parallel.py`** - Parallel NISE execution

### Utility Scripts

- **`scripts/delete-demo-sources.py`** - Clean up demo sources via API
- **`scripts/add-january-data.py`** - Add data to existing sources

## License

Apache License 2.0
