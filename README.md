# cost-onprem-demo-data

Synthetic demo data generator for **Red Hat Cost Management On-Premise**.

Populates the Cost Management UI with realistic cost, CPU/memory, volume, and
network data by inserting directly into the PostgreSQL summary tables that the
UI reads from. Bypasses the normal Celery processing pipeline so you have full
control over the values shown in the demo.

## Directory Structure

```
cost-onprem-demo-data/
├── scripts/
│   └── populate-demo-day.py  # Daily CronJob data generator
├── sql/                      # Reference SQL scripts (manual use)
│   ├── populate-demo-data.sql
│   └── populate-ros-demo-data.sql
├── k8s/
│   └── cronjob.yaml          # CronJob manifest
├── docs/
│   ├── cronjob-README.md     # Detailed CronJob documentation
│   └── data-generation-logic.md  # How data values are computed
├── deploy.sh                 # One-command CronJob deployment
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

The script `scripts/populate-demo-day.py` inserts data directly into the
partitioned summary tables. Use `--backfill-from` / `--backfill-to` to seed
historical data:

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

> For a detailed breakdown of every layer of the generation logic (multipliers,
> variance, cost splits, utilization bands, etc.), see
> [docs/data-generation-logic.md](docs/data-generation-logic.md).

The generator creates 3 demo clusters with realistic weekly traffic patterns:

| Cluster | Base Cost/Day | Namespaces | Nodes | PVCs |
|---------|--------------|------------|-------|------|
| Production Cluster | $42.50 | frontend, backend-api, database, monitoring, redis-cache | 3 | 4 |
| Development Cluster | $18.20 | dev-workspace, ci-cd, code-review, testing | 3 | 3 |
| Staging Cluster | $12.80 | staging-app, load-testing, qa-validation | 3 | 3 |

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

A random variance of +/-4% is applied on top, plus consideration of the
previous 2 days' actual values to create smooth, non-flat curves.

### Cost Breakdown

Costs are split into realistic components:

- **Infrastructure raw cost** (~55%): Base compute charges
- **Infrastructure markup** (~8.25%): Management overhead
- **Infrastructure usage (CPU)** (~10%): CPU-based metering
- **Infrastructure usage (Memory)** (~5%): Memory-based metering
- **Supplementary cost** (~26%): CPU, memory, and volume supplementary charges
- **Cost model** (~41%): CPU, memory, and volume cost model rates

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `cost-onprem-database.cost-onprem.svc.cluster.local` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `costonprem_koku` | Database name |
| `DB_USER` | `koku_user` | Database user |
| `DB_PASSWORD` | *(required)* | Database password |
| `DB_SCHEMA` | `orgorg1234567` | Tenant schema |
| `VALKEY_HOST` | `cost-onprem-valkey.cost-onprem.svc.cluster.local` | Valkey/Redis host |
| `VALKEY_PORT` | `6379` | Valkey/Redis port |

## SQL Reference Scripts

The `sql/` directory contains standalone SQL scripts for manual use:

- **`populate-demo-data.sql`** -- Inserts cost + pod + node data for 8 clusters x 6 days directly into Koku summary tables.
- **`populate-ros-demo-data.sql`** -- Inserts ROS workloads and Kruize-compatible recommendation sets.

These are not invoked by the CronJob or any Python script. They serve as
reference material or for one-off manual seeding via `psql` or `oc exec`.

## License

Apache License 2.0
