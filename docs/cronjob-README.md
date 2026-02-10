# Demo Data Generator for Cost Management On-Premise

Populates synthetic cost, CPU/memory, volume, and network data into the
Cost Management on-premise database. Designed to keep a demo environment
alive with realistic daily data.

## What it does

Inserts one day's worth of data into **10 partitioned summary tables**:

| Table | Data Type |
|-------|-----------|
| `reporting_ocp_cost_summary_p` | Cluster-level cost (raw, markup, usage) |
| `reporting_ocp_cost_summary_by_project_p` | Namespace-level cost breakdown |
| `reporting_ocp_pod_summary_p` | Cluster CPU/memory + storage |
| `reporting_ocp_pod_summary_by_project_p` | Namespace CPU/memory + storage |
| `reporting_ocp_pod_summary_by_node_p` | Node-level CPU/memory |
| `reporting_ocp_volume_summary_p` | PVC capacity/usage |
| `reporting_ocp_volume_summary_by_project_p` | PVC by namespace |
| `reporting_ocp_network_summary_p` | Cluster network data in/out |
| `reporting_ocp_network_summary_by_project_p` | Namespace network |
| `reporting_ocp_network_summary_by_node_p` | Node network |

### Demo clusters

| Cluster | Namespaces | Base Cost/day |
|---------|------------|---------------|
| Production Cluster | frontend, backend-api, database, monitoring, redis-cache | $42.50 |
| Development Cluster | dev-workspace, ci-cd, code-review, testing | $18.20 |
| Staging Cluster | staging-app, load-testing, qa-validation | $12.80 |

### Weekly pattern

Daily costs follow a realistic weekly traffic pattern:

| Day | Multiplier | Character |
|-----|-----------|-----------|
| Monday | 1.05x | Ramp-up |
| Tuesday | 1.12x | Building to peak |
| Wednesday | 1.18x | Mid-week peak |
| Thursday | 1.10x | Sustain |
| Friday | 0.92x | Wind-down |
| Saturday | 0.48x | Weekend low |
| Sunday | 0.52x | Weekend low |

A +/- 4% random variance is applied on top, plus trend-based nudges from the
previous 2 days so curves never look flat.

## Quick start

### Local (with port-forward)

```bash
# Port-forward to the database and Valkey
oc port-forward -n cost-onprem svc/cost-onprem-database 15432:5432 &
oc port-forward -n cost-onprem svc/cost-onprem-valkey 16379:6379 &

# Install dependencies
pip install -r requirements.txt

# Backfill a month of data
DB_HOST=127.0.0.1 DB_PORT=15432 DB_PASSWORD=<password> \
VALKEY_HOST=127.0.0.1 VALKEY_PORT=16379 \
python populate-demo-day.py --backfill-from 2026-02-01 --backfill-to 2026-02-28

# Or just today
DB_HOST=127.0.0.1 DB_PORT=15432 DB_PASSWORD=<password> \
VALKEY_HOST=127.0.0.1 VALKEY_PORT=16379 \
python populate-demo-day.py
```

### Deploy as CronJob

```bash
# Deploy CronJob + ConfigMap
./deploy.sh -n cost-onprem

# Trigger manually
kubectl create job demo-data-manual --from=cronjob/demo-data -n cost-onprem

# Check status
kubectl get cronjob demo-data -n cost-onprem
kubectl logs -l app.kubernetes.io/name=demo-data -n cost-onprem --tail=50
```

### Dry run

```bash
python populate-demo-day.py --dry-run --backfill-from 2026-02-01 --backfill-to 2026-02-28
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `cost-onprem-database.cost-onprem.svc.cluster.local` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `costonprem_koku` | Database name |
| `DB_USER` | `koku_user` | Database user |
| `DB_PASSWORD` | *(required)* | Database password |
| `DB_SCHEMA` | `orgorg1234567` | Tenant schema |
| `VALKEY_HOST` | `cost-onprem-valkey.cost-onprem.svc.cluster.local` | Valkey host |
| `VALKEY_PORT` | `6379` | Valkey port |

## File structure

```
scripts/demo-data/
├── populate-demo-day.py    # Main script
├── deploy.sh               # Deploy CronJob to cluster
├── requirements.txt        # Python dependencies
├── README.md               # This file
└── k8s/
    ├── configmap.yaml      # ConfigMap template
    └── cronjob.yaml        # CronJob manifest
```
