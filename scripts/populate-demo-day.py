#!/usr/bin/env python3
"""
Populate daily demo cost/usage data into the Cost Management on-premise DB.

Inserts one day's worth of realistic cost, CPU/memory, volume, and network
data into all partitioned summary tables. Designed to run as a daily CronJob
or manually with --backfill for bulk seeding.

Usage:
  # Single day (today)
  python populate-demo-day.py

  # Specific date
  python populate-demo-day.py --date 2026-02-15

  # Backfill a range
  python populate-demo-day.py --backfill-from 2026-02-01 --backfill-to 2026-02-10

  # Dry run (print SQL, don't execute)
  python populate-demo-day.py --dry-run --date 2026-02-05

Environment variables (set by CronJob or manually):
  DB_HOST       PostgreSQL host      (default: cost-onprem-database.cost-onprem.svc.cluster.local)
  DB_PORT       PostgreSQL port      (default: 5432)
  DB_NAME       Koku database name   (default: costonprem_koku)
  DB_USER       Database user        (default: koku_user)
  DB_PASSWORD   Database password    (required)
  DB_SCHEMA     Tenant schema        (default: orgorg1234567)
  VALKEY_HOST   Valkey/Redis host    (default: cost-onprem-valkey.cost-onprem.svc.cluster.local)
  VALKEY_PORT   Valkey/Redis port    (default: 6379)
"""

import argparse
import logging
import os
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")

logger = logging.getLogger("populate-demo-day")

# =============================================================================
# CONFIGURATION — Tune these for your demo
# =============================================================================

# Weekly traffic pattern multipliers (Monday=0 .. Sunday=6)
WEEKLY_PATTERN = {
    0: 1.05,  # Monday — ramp-up after weekend
    1: 1.12,  # Tuesday — building to peak
    2: 1.18,  # Wednesday — mid-week peak
    3: 1.10,  # Thursday — sustain
    4: 0.92,  # Friday — wind-down
    5: 0.48,  # Saturday — weekend low
    6: 0.52,  # Sunday — weekend low
}

# Random variance range applied on top of the pattern
VARIANCE_MIN = -0.04  # -4%
VARIANCE_MAX = 0.04   # +4%

# Cluster definitions
CLUSTERS = [
    {
        "cluster_id": "demo-prod-cluster",
        "cluster_alias": "Production Cluster",
        "source_uuid": None,  # resolved at runtime from api_provider
        "base_cost": 42.50,       # Base daily cost in USD
        "base_cpu": 28.0,         # Base CPU core-hours
        "base_mem": 56.0,         # Base memory GiB-hours
        "pod_count": 24,
        "capacity_cpu": 384.0,    # Cluster CPU capacity core-hours
        "capacity_mem": 1536.0,   # Cluster memory capacity GiB-hours
        "base_net_in": 12.0,      # Base network data-in GB
        "base_net_out": 3.5,      # Base network data-out GB
        "namespaces": {
            "frontend":    {"cost_share": 0.30, "cpu_share": 0.30, "mem_share": 0.25, "net_share": 0.35},
            "backend-api": {"cost_share": 0.25, "cpu_share": 0.25, "mem_share": 0.25, "net_share": 0.30},
            "database":    {"cost_share": 0.22, "cpu_share": 0.20, "mem_share": 0.28, "net_share": 0.10},
            "monitoring":  {"cost_share": 0.13, "cpu_share": 0.15, "mem_share": 0.12, "net_share": 0.15},
            "redis-cache": {"cost_share": 0.10, "cpu_share": 0.10, "mem_share": 0.10, "net_share": 0.10},
        },
        "pvcs": [
            {"name": "postgresql-data", "namespace": "database",    "storageclass": "gp3-csi", "capacity_gib": 100, "count": 1},
            {"name": "redis-data",      "namespace": "redis-cache", "storageclass": "gp3-csi", "capacity_gib": 20,  "count": 3},
            {"name": "prometheus-data",  "namespace": "monitoring",  "storageclass": "gp3-csi", "capacity_gib": 50,  "count": 1},
            {"name": "app-logs",         "namespace": "backend-api", "storageclass": "gp3-csi", "capacity_gib": 30,  "count": 1},
        ],
        "nodes": [
            {"name": "worker-1", "share": 0.45},
            {"name": "worker-2", "share": 0.35},
            {"name": "worker-3", "share": 0.20},
        ],
    },
    {
        "cluster_id": "demo-dev-cluster",
        "cluster_alias": "Development Cluster",
        "source_uuid": None,  # resolved at runtime from api_provider
        "base_cost": 18.20,
        "base_cpu": 12.0,
        "base_mem": 24.0,
        "pod_count": 18,
        "capacity_cpu": 192.0,
        "capacity_mem": 768.0,
        "base_net_in": 5.0,
        "base_net_out": 1.5,
        "namespaces": {
            "dev-workspace": {"cost_share": 0.35, "cpu_share": 0.35, "mem_share": 0.30, "net_share": 0.25},
            "ci-cd":         {"cost_share": 0.30, "cpu_share": 0.30, "mem_share": 0.30, "net_share": 0.35},
            "code-review":   {"cost_share": 0.20, "cpu_share": 0.20, "mem_share": 0.25, "net_share": 0.25},
            "testing":       {"cost_share": 0.15, "cpu_share": 0.15, "mem_share": 0.15, "net_share": 0.15},
        },
        "pvcs": [
            {"name": "workspace-data", "namespace": "dev-workspace", "storageclass": "gp3-csi", "capacity_gib": 40, "count": 2},
            {"name": "jenkins-home",   "namespace": "ci-cd",         "storageclass": "gp3-csi", "capacity_gib": 60, "count": 1},
            {"name": "gitea-repos",    "namespace": "code-review",   "storageclass": "gp3-csi", "capacity_gib": 80, "count": 1},
        ],
        "nodes": [
            {"name": "worker-1", "share": 0.45},
            {"name": "worker-2", "share": 0.35},
            {"name": "worker-3", "share": 0.20},
        ],
    },
    {
        "cluster_id": "demo-staging-cluster",
        "cluster_alias": "Staging Cluster",
        "source_uuid": None,  # resolved at runtime from api_provider
        "base_cost": 12.80,
        "base_cpu": 8.5,
        "base_mem": 17.0,
        "pod_count": 10,
        "capacity_cpu": 192.0,
        "capacity_mem": 768.0,
        "base_net_in": 3.0,
        "base_net_out": 0.8,
        "namespaces": {
            "staging-app":    {"cost_share": 0.45, "cpu_share": 0.45, "mem_share": 0.45, "net_share": 0.40},
            "load-testing":   {"cost_share": 0.35, "cpu_share": 0.35, "mem_share": 0.35, "net_share": 0.40},
            "qa-validation":  {"cost_share": 0.20, "cpu_share": 0.20, "mem_share": 0.20, "net_share": 0.20},
        },
        "pvcs": [
            {"name": "staging-db",     "namespace": "staging-app",   "storageclass": "gp3-csi", "capacity_gib": 30, "count": 1},
            {"name": "test-artifacts", "namespace": "qa-validation", "storageclass": "gp3-csi", "capacity_gib": 25, "count": 1},
            {"name": "load-test-data", "namespace": "load-testing",  "storageclass": "gp3-csi", "capacity_gib": 15, "count": 1},
        ],
        "nodes": [
            {"name": "worker-1", "share": 0.45},
            {"name": "worker-2", "share": 0.35},
            {"name": "worker-3", "share": 0.20},
        ],
    },
]

# Cost split ratios (must roughly sum to ~1.0 with markup)
RAW_COST_RATIO = 0.55        # Infrastructure raw cost
MARKUP_RATIO = 0.55 * 0.15   # Markup = 15% of raw
INFRA_USAGE_CPU_RATIO = 0.10  # Infrastructure usage cost (CPU)
INFRA_USAGE_MEM_RATIO = 0.05  # Infrastructure usage cost (memory)
SUPPL_CPU_RATIO = 0.14        # Supplementary usage cost (CPU)
SUPPL_MEM_RATIO = 0.10        # Supplementary usage cost (memory)
SUPPL_VOL_RATIO = 0.02        # Supplementary usage cost (volume)
CM_CPU_RATIO = 0.24           # Cost model CPU
CM_MEM_RATIO = 0.15           # Cost model memory
CM_VOL_RATIO = 0.02           # Cost model volume

# Volume pricing ($/GiB/month)
VOLUME_PRICE_PER_GIB_MONTH = 0.10


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def v(base: float, variance_pct: float = 0.03) -> float:
    """Apply small random variance to a base value."""
    return round(base * (1 + random.uniform(-variance_pct, variance_pct)), 4)


def get_day_multiplier(target_date: date, prev_days_data: dict) -> float:
    """
    Calculate the day's multiplier from weekly pattern + random variance.
    If we have previous days' data, derive extra variance from the trend.
    """
    dow = target_date.weekday()
    base_mult = WEEKLY_PATTERN[dow]

    # Add random variance
    variance = random.uniform(VARIANCE_MIN, VARIANCE_MAX)

    # If we have 2 previous days, add trend-based variance
    if prev_days_data:
        avg_cost = sum(prev_days_data.values()) / len(prev_days_data)
        if avg_cost > 0:
            # Add a small trend nudge based on how the last 2 days differed
            costs = list(prev_days_data.values())
            if len(costs) >= 2:
                trend = (costs[-1] - costs[-2]) / avg_cost
                variance += trend * 0.1  # 10% of the trend

    return base_mult * (1 + variance)


def resolve_provider_uuids(conn):
    """Query actual provider UUIDs from the DB and assign them to CLUSTERS.

    The cost summary tables have a FK to reporting_tenant_api_provider, so we
    must use UUIDs that actually exist in that table rather than hardcoded ones.
    Providers are matched to clusters by name similarity against cluster_alias.
    """
    sql = "SELECT uuid::text, name FROM public.api_provider ORDER BY name"
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            providers = cur.fetchall()
    except psycopg2.Error as e:
        sys.exit(f"ERROR: Failed to query api_provider table: {e}")

    if not providers:
        sys.exit(
            "ERROR: No providers found in api_provider table. "
            "Deploy cost-onprem and register sources first."
        )

    logger.info(f"Found {len(providers)} provider(s) in database:")
    for uuid_val, name in providers:
        logger.info(f"  {name}: {uuid_val}")

    # Try name-based matching first (case-insensitive substring)
    active = []
    used_providers = set()
    for cluster in CLUSTERS:
        alias = cluster["cluster_alias"].lower()
        match = next(
            (p for p in providers
             if p[0] not in used_providers
             and (p[1].lower() in alias or alias in p[1].lower())),
            None,
        )
        if match:
            cluster["source_uuid"] = match[0]
            used_providers.add(match[0])
            logger.info(f"  Mapped provider '{match[1]}' -> cluster '{cluster['cluster_alias']}'")
            active.append(cluster)

    if active:
        CLUSTERS[:] = active
        return

    # Fallback: single provider → assign it to all clusters
    if len(providers) == 1:
        uuid_val, name = providers[0]
        logger.info(f"  Single provider '{name}' — assigning to all {len(CLUSTERS)} cluster(s)")
        for cluster in CLUSTERS:
            cluster["source_uuid"] = uuid_val
            logger.info(f"    '{name}' -> '{cluster['cluster_alias']}'")
        return

    # Fallback: multiple providers, no name matches — assign by position
    logger.info("  No name matches found, assigning providers to clusters by position")
    active = []
    for i, cluster in enumerate(CLUSTERS):
        if i < len(providers):
            cluster["source_uuid"] = providers[i][0]
            logger.info(f"    '{providers[i][1]}' -> '{cluster['cluster_alias']}'")
            active.append(cluster)
        else:
            logger.warning(f"    No provider left for cluster '{cluster['cluster_alias']}', skipping")
    CLUSTERS[:] = active


def get_previous_costs(conn, schema: str, target_date: date) -> dict:
    """Query the last 2 days' total cost from the cost summary table."""
    sql = f"""
        SELECT usage_start, SUM(infrastructure_raw_cost)::float as total_raw
        FROM {schema}.reporting_ocp_cost_summary_p
        WHERE usage_start >= %s AND usage_start < %s
        GROUP BY usage_start
        ORDER BY usage_start
    """
    d2 = target_date - timedelta(days=2)
    with conn.cursor() as cur:
        cur.execute(sql, (d2, target_date))
        return {row[0]: row[1] for row in cur.fetchall()}


def get_last_data_date(conn, schema: str) -> date | None:
    """Find the most recent date that has data in cost_summary_p.

    Returns None if the table is empty (no data at all).
    """
    sql = f"""
        SELECT MAX(usage_start)
        FROM {schema}.reporting_ocp_cost_summary_p
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        if row and row[0]:
            return row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
    return None


def delete_day(conn, schema: str, target_date: date):
    """Delete existing data for the target date from all tables."""
    tables = [
        "reporting_ocp_cost_summary_p",
        "reporting_ocp_cost_summary_by_project_p",
        "reporting_ocp_pod_summary_p",
        "reporting_ocp_pod_summary_by_project_p",
        "reporting_ocp_pod_summary_by_node_p",
        "reporting_ocp_volume_summary_p",
        "reporting_ocp_volume_summary_by_project_p",
        "reporting_ocp_network_summary_p",
        "reporting_ocp_network_summary_by_project_p",
        "reporting_ocp_network_summary_by_node_p",
    ]
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"DELETE FROM {schema}.{table} WHERE usage_start = %s", (target_date,))
            logger.debug(f"  Deleted {cur.rowcount} rows from {table}")


def insert_cost_summary(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_cost_summary_p."""
    cost = cluster["base_cost"] * mult
    cur.execute(f"""
        INSERT INTO {schema}.reporting_ocp_cost_summary_p (
            id, usage_start, usage_end, cluster_id, cluster_alias,
            infrastructure_raw_cost, infrastructure_markup_cost,
            infrastructure_usage_cost, infrastructure_monthly_cost_json,
            supplementary_usage_cost, supplementary_monthly_cost_json,
            cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
            cost_model_rate_type, distributed_cost, source_uuid, raw_currency
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
            %s, %s, %s, 'Infrastructure', %s, %s, 'USD'
        )
    """, (
        str(uuid4()), target_date, target_date,
        cluster["cluster_id"], cluster["cluster_alias"],
        v(cost * RAW_COST_RATIO),
        v(cost * MARKUP_RATIO),
        psycopg2.extras.Json({"cpu": v(cost * INFRA_USAGE_CPU_RATIO), "memory": v(cost * INFRA_USAGE_MEM_RATIO)}),
        psycopg2.extras.Json({"cpu": v(cost * SUPPL_CPU_RATIO), "memory": v(cost * SUPPL_MEM_RATIO), "volume": v(cost * SUPPL_VOL_RATIO)}),
        v(cost * CM_CPU_RATIO), v(cost * CM_MEM_RATIO), v(cost * CM_VOL_RATIO),
        v(cost), cluster["source_uuid"],
    ))


def insert_cost_by_project(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_cost_summary_by_project_p."""
    for ns_name, ns in cluster["namespaces"].items():
        cost = cluster["base_cost"] * mult * ns["cost_share"]
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_cost_summary_by_project_p (
                id, usage_start, usage_end, cluster_id, cluster_alias, namespace,
                infrastructure_raw_cost, infrastructure_markup_cost,
                infrastructure_usage_cost, infrastructure_project_monthly_cost,
                supplementary_usage_cost, supplementary_project_monthly_cost,
                cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
                cost_model_rate_type, distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
                %s, %s, %s, 'Infrastructure', %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"], ns_name,
            v(cost * RAW_COST_RATIO), v(cost * MARKUP_RATIO),
            psycopg2.extras.Json({"cpu": v(cost * INFRA_USAGE_CPU_RATIO), "memory": v(cost * INFRA_USAGE_MEM_RATIO)}),
            psycopg2.extras.Json({"cpu": v(cost * SUPPL_CPU_RATIO), "memory": v(cost * SUPPL_MEM_RATIO), "volume": v(cost * SUPPL_VOL_RATIO)}),
            v(cost * CM_CPU_RATIO), v(cost * CM_MEM_RATIO), v(cost * CM_VOL_RATIO),
            v(cost), cluster["source_uuid"],
        ))


def insert_pod_summary(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_pod_summary_p (Pod data_source)."""
    cost = cluster["base_cost"] * mult
    cpu_usage = cluster["base_cpu"] * mult * random.uniform(0.60, 0.80)
    mem_usage = cluster["base_mem"] * mult * random.uniform(0.70, 0.90)
    cur.execute(f"""
        INSERT INTO {schema}.reporting_ocp_pod_summary_p (
            id, usage_start, usage_end, cluster_id, cluster_alias,
            data_source, resource_count,
            infrastructure_raw_cost, infrastructure_markup_cost,
            infrastructure_usage_cost, infrastructure_monthly_cost_json,
            supplementary_usage_cost, supplementary_monthly_cost_json,
            cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
            cost_model_rate_type,
            pod_usage_cpu_core_hours, pod_request_cpu_core_hours, pod_limit_cpu_core_hours,
            pod_usage_memory_gigabyte_hours, pod_request_memory_gigabyte_hours,
            pod_limit_memory_gigabyte_hours,
            cluster_capacity_cpu_core_hours, cluster_capacity_memory_gigabyte_hours,
            distributed_cost, source_uuid, raw_currency
        ) VALUES (
            %s, %s, %s, %s, %s,
            'Pod', %s,
            %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
            %s, %s, %s, 'Infrastructure',
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, 'USD'
        )
    """, (
        str(uuid4()), target_date, target_date,
        cluster["cluster_id"], cluster["cluster_alias"],
        cluster["pod_count"],
        v(cost * RAW_COST_RATIO), v(cost * MARKUP_RATIO),
        psycopg2.extras.Json({"cpu": v(cost * INFRA_USAGE_CPU_RATIO), "memory": v(cost * INFRA_USAGE_MEM_RATIO)}),
        psycopg2.extras.Json({"cpu": v(cost * SUPPL_CPU_RATIO), "memory": v(cost * SUPPL_MEM_RATIO), "volume": v(cost * SUPPL_VOL_RATIO)}),
        v(cost * CM_CPU_RATIO), v(cost * CM_MEM_RATIO), v(cost * CM_VOL_RATIO),
        round(cpu_usage, 2),
        round(cluster["base_cpu"] * mult, 2),
        round(cluster["base_cpu"] * mult * 1.4, 2),
        round(mem_usage, 2),
        round(cluster["base_mem"] * mult, 2),
        round(cluster["base_mem"] * mult * 1.3, 2),
        cluster["capacity_cpu"], cluster["capacity_mem"],
        v(cost), cluster["source_uuid"],
    ))


def insert_pod_by_project(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_pod_summary_by_project_p (Pod data_source)."""
    for ns_name, ns in cluster["namespaces"].items():
        cost = cluster["base_cost"] * mult * ns["cost_share"]
        cpu_share = ns.get("cpu_share", ns["cost_share"])
        mem_share = ns.get("mem_share", ns["cost_share"])
        cpu_usage = cluster["base_cpu"] * mult * cpu_share * random.uniform(0.60, 0.80)
        mem_usage = cluster["base_mem"] * mult * mem_share * random.uniform(0.70, 0.90)
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_pod_summary_by_project_p (
                id, usage_start, usage_end, cluster_id, cluster_alias, namespace,
                data_source, resource_count,
                infrastructure_raw_cost, infrastructure_markup_cost,
                infrastructure_usage_cost, infrastructure_monthly_cost_json,
                supplementary_usage_cost, supplementary_monthly_cost_json,
                cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
                cost_model_rate_type,
                pod_usage_cpu_core_hours, pod_request_cpu_core_hours, pod_limit_cpu_core_hours,
                pod_usage_memory_gigabyte_hours, pod_request_memory_gigabyte_hours,
                pod_limit_memory_gigabyte_hours,
                cluster_capacity_cpu_core_hours, cluster_capacity_memory_gigabyte_hours,
                distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'Pod', %s,
                %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
                %s, %s, %s, 'Infrastructure',
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"], ns_name,
            max(1, int(cluster["pod_count"] * ns["cost_share"])),
            v(cost * RAW_COST_RATIO), v(cost * MARKUP_RATIO),
            psycopg2.extras.Json({"cpu": v(cost * INFRA_USAGE_CPU_RATIO), "memory": v(cost * INFRA_USAGE_MEM_RATIO)}),
            psycopg2.extras.Json({"cpu": v(cost * SUPPL_CPU_RATIO), "memory": v(cost * SUPPL_MEM_RATIO), "volume": v(cost * SUPPL_VOL_RATIO)}),
            v(cost * CM_CPU_RATIO), v(cost * CM_MEM_RATIO), v(cost * CM_VOL_RATIO),
            round(cpu_usage, 2),
            round(cluster["base_cpu"] * mult * cpu_share, 2),
            round(cluster["base_cpu"] * mult * cpu_share * 1.4, 2),
            round(mem_usage, 2),
            round(cluster["base_mem"] * mult * mem_share, 2),
            round(cluster["base_mem"] * mult * mem_share * 1.3, 2),
            cluster["capacity_cpu"], cluster["capacity_mem"],
            v(cost), cluster["source_uuid"],
        ))


def insert_pod_by_node(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_pod_summary_by_node_p."""
    for node in cluster["nodes"]:
        ns = node["share"]
        cost = cluster["base_cost"] * mult * ns
        cpu_usage = cluster["base_cpu"] * mult * ns * random.uniform(0.60, 0.80)
        mem_usage = cluster["base_mem"] * mult * ns * random.uniform(0.70, 0.90)
        num_nodes = len(cluster["nodes"])
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_pod_summary_by_node_p (
                id, usage_start, usage_end, cluster_id, cluster_alias, node,
                data_source, resource_count,
                infrastructure_raw_cost, infrastructure_markup_cost,
                infrastructure_usage_cost, infrastructure_monthly_cost_json,
                supplementary_usage_cost, supplementary_monthly_cost_json,
                cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
                cost_model_rate_type,
                pod_usage_cpu_core_hours, pod_request_cpu_core_hours, pod_limit_cpu_core_hours,
                pod_usage_memory_gigabyte_hours, pod_request_memory_gigabyte_hours,
                pod_limit_memory_gigabyte_hours,
                node_capacity_cpu_core_hours, cluster_capacity_cpu_core_hours,
                node_capacity_memory_gigabyte_hours, cluster_capacity_memory_gigabyte_hours,
                distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'Pod', %s,
                %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
                %s, %s, %s, 'Infrastructure',
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"], node["name"],
            max(1, int(cluster["pod_count"] * ns)),
            v(cost * RAW_COST_RATIO), v(cost * MARKUP_RATIO),
            psycopg2.extras.Json({"cpu": v(cost * INFRA_USAGE_CPU_RATIO), "memory": v(cost * INFRA_USAGE_MEM_RATIO)}),
            psycopg2.extras.Json({"cpu": v(cost * SUPPL_CPU_RATIO), "memory": v(cost * SUPPL_MEM_RATIO), "volume": v(cost * SUPPL_VOL_RATIO)}),
            v(cost * CM_CPU_RATIO), v(cost * CM_MEM_RATIO), v(cost * CM_VOL_RATIO),
            round(cpu_usage, 2),
            round(cluster["base_cpu"] * mult * ns, 2),
            round(cluster["base_cpu"] * mult * ns * 1.4, 2),
            round(mem_usage, 2),
            round(cluster["base_mem"] * mult * ns, 2),
            round(cluster["base_mem"] * mult * ns * 1.3, 2),
            round(cluster["capacity_cpu"] / num_nodes, 1), cluster["capacity_cpu"],
            round(cluster["capacity_mem"] / num_nodes, 1), cluster["capacity_mem"],
            v(cost), cluster["source_uuid"],
        ))


def insert_pod_storage_summary(cur, schema, cluster, target_date):
    """Insert Storage data_source rows into pod_summary_p."""
    total_cap = sum(p["capacity_gib"] for p in cluster["pvcs"])
    total_count = sum(p["count"] for p in cluster["pvcs"])
    daily_cost = total_cap * VOLUME_PRICE_PER_GIB_MONTH / 30.0
    cur.execute(f"""
        INSERT INTO {schema}.reporting_ocp_pod_summary_p (
            id, usage_start, usage_end, cluster_id, cluster_alias,
            data_source, resource_count,
            infrastructure_raw_cost, infrastructure_markup_cost,
            infrastructure_usage_cost, infrastructure_monthly_cost_json,
            supplementary_usage_cost, supplementary_monthly_cost_json,
            cost_model_volume_cost, cost_model_rate_type,
            distributed_cost, source_uuid, raw_currency
        ) VALUES (
            %s, %s, %s, %s, %s,
            'Storage', %s,
            %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
            %s, 'Infrastructure', %s, %s, 'USD'
        )
    """, (
        str(uuid4()), target_date, target_date,
        cluster["cluster_id"], cluster["cluster_alias"],
        total_count,
        v(daily_cost), v(daily_cost * 0.15),
        psycopg2.extras.Json({"volume": v(daily_cost * 0.30)}),
        psycopg2.extras.Json({"volume": v(daily_cost * 0.20)}),
        v(daily_cost * 0.50),
        v(daily_cost * 1.50), cluster["source_uuid"],
    ))


def insert_pod_storage_by_project(cur, schema, cluster, target_date):
    """Insert Storage data_source rows into pod_summary_by_project_p."""
    for pvc in cluster["pvcs"]:
        daily_cost = pvc["capacity_gib"] * VOLUME_PRICE_PER_GIB_MONTH / 30.0
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_pod_summary_by_project_p (
                id, usage_start, usage_end, cluster_id, cluster_alias, namespace,
                data_source, resource_count,
                infrastructure_raw_cost, infrastructure_markup_cost,
                infrastructure_usage_cost, infrastructure_monthly_cost_json,
                supplementary_usage_cost, supplementary_monthly_cost_json,
                cost_model_volume_cost, cost_model_rate_type,
                distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'Storage', %s,
                %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
                %s, 'Infrastructure', %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"], pvc["namespace"],
            pvc["count"],
            v(daily_cost), v(daily_cost * 0.15),
            psycopg2.extras.Json({"volume": v(daily_cost * 0.30)}),
            psycopg2.extras.Json({"volume": v(daily_cost * 0.20)}),
            v(daily_cost * 0.50),
            v(daily_cost * 1.50), cluster["source_uuid"],
        ))


def insert_volume_summary(cur, schema, cluster, target_date):
    """Insert into reporting_ocp_volume_summary_p."""
    for pvc in cluster["pvcs"]:
        cap = pvc["capacity_gib"]
        daily_cost = cap * VOLUME_PRICE_PER_GIB_MONTH / 30.0
        usage_frac = random.uniform(0.40, 0.75)
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_volume_summary_p (
                id, usage_start, usage_end, cluster_id, cluster_alias,
                data_source, resource_count,
                infrastructure_raw_cost, infrastructure_markup_cost,
                infrastructure_usage_cost, infrastructure_monthly_cost_json,
                supplementary_usage_cost, supplementary_monthly_cost_json,
                cost_model_volume_cost, cost_model_rate_type,
                persistentvolumeclaim, storageclass,
                volume_request_storage_gigabyte_months,
                persistentvolumeclaim_usage_gigabyte_months,
                persistentvolumeclaim_capacity_gigabyte_months,
                distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s,
                'Storage', %s,
                %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
                %s, 'Infrastructure',
                %s, %s, %s, %s, %s,
                %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"],
            pvc["count"],
            v(daily_cost), v(daily_cost * 0.15),
            psycopg2.extras.Json({"volume": v(daily_cost * 0.30)}),
            psycopg2.extras.Json({"volume": v(daily_cost * 0.20)}),
            v(daily_cost * 0.50),
            pvc["name"], pvc["storageclass"],
            round(cap * 0.90 / 30.0, 4),
            round(cap * usage_frac / 30.0, 4),
            round(cap / 30.0, 4),
            v(daily_cost * 1.50), cluster["source_uuid"],
        ))


def insert_volume_by_project(cur, schema, cluster, target_date):
    """Insert into reporting_ocp_volume_summary_by_project_p."""
    for pvc in cluster["pvcs"]:
        cap = pvc["capacity_gib"]
        daily_cost = cap * VOLUME_PRICE_PER_GIB_MONTH / 30.0
        usage_frac = random.uniform(0.40, 0.75)
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_volume_summary_by_project_p (
                id, usage_start, usage_end, cluster_id, cluster_alias, namespace,
                data_source, resource_count,
                infrastructure_raw_cost, infrastructure_markup_cost,
                infrastructure_usage_cost, infrastructure_monthly_cost_json,
                supplementary_usage_cost, supplementary_monthly_cost_json,
                cost_model_volume_cost, cost_model_rate_type,
                persistentvolumeclaim, storageclass,
                volume_request_storage_gigabyte_months,
                persistentvolumeclaim_usage_gigabyte_months,
                persistentvolumeclaim_capacity_gigabyte_months,
                distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'Storage', %s,
                %s, %s, %s, '{{}}'::jsonb, %s, '{{}}'::jsonb,
                %s, 'Infrastructure',
                %s, %s, %s, %s, %s,
                %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"], pvc["namespace"],
            pvc["count"],
            v(daily_cost), v(daily_cost * 0.15),
            psycopg2.extras.Json({"volume": v(daily_cost * 0.30)}),
            psycopg2.extras.Json({"volume": v(daily_cost * 0.20)}),
            v(daily_cost * 0.50),
            pvc["name"], pvc["storageclass"],
            round(cap * 0.90 / 30.0, 4),
            round(cap * usage_frac / 30.0, 4),
            round(cap / 30.0, 4),
            v(daily_cost * 1.50), cluster["source_uuid"],
        ))


def insert_network_summary(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_network_summary_p."""
    data_in = cluster["base_net_in"] * mult
    data_out = cluster["base_net_out"] * mult
    cur.execute(f"""
        INSERT INTO {schema}.reporting_ocp_network_summary_p (
            id, usage_start, usage_end, cluster_id, cluster_alias,
            data_source, resource_count,
            infrastructure_data_in_gigabytes, infrastructure_data_out_gigabytes,
            infrastructure_raw_cost, infrastructure_markup_cost,
            distributed_cost, source_uuid, raw_currency
        ) VALUES (
            %s, %s, %s, %s, %s,
            'Network', %s,
            %s, %s, %s, %s,
            %s, %s, 'USD'
        )
    """, (
        str(uuid4()), target_date, target_date,
        cluster["cluster_id"], cluster["cluster_alias"],
        cluster["pod_count"],
        v(data_in), v(data_out),
        v((data_in + data_out) * 0.05),  # ~$0.05/GB
        v((data_in + data_out) * 0.05 * 0.15),
        v((data_in + data_out) * 0.05 * 1.15),
        cluster["source_uuid"],
    ))


def insert_network_by_project(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_network_summary_by_project_p."""
    for ns_name, ns in cluster["namespaces"].items():
        net_share = ns.get("net_share", ns["cost_share"])
        data_in = cluster["base_net_in"] * mult * net_share
        data_out = cluster["base_net_out"] * mult * net_share
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_network_summary_by_project_p (
                id, usage_start, usage_end, cluster_id, cluster_alias, namespace,
                data_source, resource_count,
                infrastructure_data_in_gigabytes, infrastructure_data_out_gigabytes,
                infrastructure_raw_cost, infrastructure_markup_cost,
                distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'Network', %s,
                %s, %s, %s, %s,
                %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"], ns_name,
            max(1, int(cluster["pod_count"] * ns["cost_share"])),
            v(data_in), v(data_out),
            v((data_in + data_out) * 0.05),
            v((data_in + data_out) * 0.05 * 0.15),
            v((data_in + data_out) * 0.05 * 1.15),
            cluster["source_uuid"],
        ))


def insert_network_by_node(cur, schema, cluster, target_date, mult):
    """Insert into reporting_ocp_network_summary_by_node_p."""
    for node in cluster["nodes"]:
        ns = node["share"]
        data_in = cluster["base_net_in"] * mult * ns
        data_out = cluster["base_net_out"] * mult * ns
        cur.execute(f"""
            INSERT INTO {schema}.reporting_ocp_network_summary_by_node_p (
                id, usage_start, usage_end, cluster_id, cluster_alias, node,
                data_source, resource_count,
                infrastructure_data_in_gigabytes, infrastructure_data_out_gigabytes,
                infrastructure_raw_cost, infrastructure_markup_cost,
                distributed_cost, source_uuid, raw_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'Network', %s,
                %s, %s, %s, %s,
                %s, %s, 'USD'
            )
        """, (
            str(uuid4()), target_date, target_date,
            cluster["cluster_id"], cluster["cluster_alias"], node["name"],
            max(1, int(cluster["pod_count"] * ns)),
            v(data_in), v(data_out),
            v((data_in + data_out) * 0.05),
            v((data_in + data_out) * 0.05 * 0.15),
            v((data_in + data_out) * 0.05 * 1.15),
            cluster["source_uuid"],
        ))


# =============================================================================
# MAIN LOGIC
# =============================================================================

def populate_day(conn, schema: str, target_date: date):
    """Insert one full day of demo data for all clusters."""
    logger.info(f"Populating {target_date} ({target_date.strftime('%A')}) ...")

    # Get previous days' data for variance
    prev_data = get_previous_costs(conn, schema, target_date)
    mult = get_day_multiplier(target_date, prev_data)
    logger.info(f"  Day multiplier: {mult:.4f} (base pattern: {WEEKLY_PATTERN[target_date.weekday()]:.2f})")

    # Delete existing data for idempotency
    delete_day(conn, schema, target_date)

    with conn.cursor() as cur:
        for cluster in CLUSTERS:
            logger.info(f"  Cluster: {cluster['cluster_alias']}")

            # Cost tables
            insert_cost_summary(cur, schema, cluster, target_date, mult)
            insert_cost_by_project(cur, schema, cluster, target_date, mult)

            # Pod tables (Pod data_source)
            insert_pod_summary(cur, schema, cluster, target_date, mult)
            insert_pod_by_project(cur, schema, cluster, target_date, mult)
            insert_pod_by_node(cur, schema, cluster, target_date, mult)

            # Pod tables (Storage data_source)
            insert_pod_storage_summary(cur, schema, cluster, target_date)
            insert_pod_storage_by_project(cur, schema, cluster, target_date)

            # Volume tables
            insert_volume_summary(cur, schema, cluster, target_date)
            insert_volume_by_project(cur, schema, cluster, target_date)

            # Network tables
            insert_network_summary(cur, schema, cluster, target_date, mult)
            insert_network_by_project(cur, schema, cluster, target_date, mult)
            insert_network_by_node(cur, schema, cluster, target_date, mult)

    conn.commit()
    logger.info(f"  Committed.")


def flush_valkey():
    """Flush the Valkey cache so the UI picks up new data."""
    host = os.environ.get("VALKEY_HOST", "cost-onprem-valkey.cost-onprem.svc.cluster.local")
    port = int(os.environ.get("VALKEY_PORT", "6379"))
    try:
        import redis
        r = redis.Redis(host=host, port=port, socket_timeout=5)
        r.flushall()
        logger.info("Valkey cache flushed.")
    except ImportError:
        # Fallback: raw socket FLUSHALL
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((host, port))
            s.sendall(b"*1\r\n$8\r\nFLUSHALL\r\n")
            resp = s.recv(64)
            s.close()
            logger.info(f"Valkey cache flushed (raw socket): {resp.decode().strip()}")
        except Exception as e:
            logger.warning(f"Could not flush Valkey at {host}:{port}: {e}")


def _print_dry_run(dates: list, schema: str):
    """Print dry-run summary and exit."""
    logger.info(f"DRY RUN — would populate {len(dates)} day(s): {dates[0]} to {dates[-1]}")
    logger.info(f"Schema: {schema}")
    logger.info(f"Clusters: {len(CLUSTERS)}")
    for c in CLUSTERS:
        ns_count = len(c['namespaces'])
        pvc_count = len(c['pvcs'])
        node_count = len(c['nodes'])
        logger.info(f"  {c['cluster_alias']}: {ns_count} namespaces, {pvc_count} PVCs, {node_count} nodes, base=${c['base_cost']}/day")
    for d in dates:
        mult = WEEKLY_PATTERN[d.weekday()]
        total = sum(c["base_cost"] for c in CLUSTERS) * mult
        logger.info(f"  {d} ({d.strftime('%A')}): multiplier={mult:.2f}, est. total=${total:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Populate daily demo cost data")
    parser.add_argument("--date", type=str, help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-from", type=str, help="Backfill start date YYYY-MM-DD")
    parser.add_argument("--backfill-to", type=str, help="Backfill end date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Print config, don't execute")
    parser.add_argument("--no-flush", action="store_true", help="Skip Valkey flush")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Connect to database (needed before date resolution for gap detection)
    schema = os.environ.get("DB_SCHEMA", "orgorg1234567")
    db_host = os.environ.get("DB_HOST", "cost-onprem-database.cost-onprem.svc.cluster.local")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME", "costonprem_koku")
    db_user = os.environ.get("DB_USER", "koku_user")
    db_pass = os.environ.get("DB_PASSWORD")

    # Determine dates
    dates = None  # resolved below; set early for --dry-run w/ explicit ranges

    if args.backfill_from and args.backfill_to:
        start = date.fromisoformat(args.backfill_from)
        end = date.fromisoformat(args.backfill_to)
        dates = []
        d = start
        while d <= end:
            dates.append(d)
            d += timedelta(days=1)
    elif args.date:
        dates = [date.fromisoformat(args.date)]
    # else: default — resolved after DB connect (gap detection)

    if args.dry_run and dates is not None:
        _print_dry_run(dates, schema)
        return

    if not db_pass:
        sys.exit("ERROR: DB_PASSWORD environment variable is required")

    logger.info(f"Connecting to {db_host}:{db_port}/{db_name} as {db_user} ...")
    conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)

    try:
        resolve_provider_uuids(conn)

        # Default mode: auto-detect gaps and fill from last data date+1 to today,
        # capped to the 1st of the current month.
        if dates is None:
            today = date.today()
            first_of_month = today.replace(day=1)
            last_data = get_last_data_date(conn, schema)

            if last_data and last_data >= first_of_month:
                gap_start = last_data + timedelta(days=1)
            else:
                # No data this month (or no data at all) — start from 1st of month
                gap_start = first_of_month

            if gap_start > today:
                logger.info(f"Data is up to date (last: {last_data}, today: {today}). Nothing to do.")
                return

            dates = []
            d = gap_start
            while d <= today:
                dates.append(d)
                d += timedelta(days=1)

            logger.info(
                f"Gap detected: last data={last_data}, filling {len(dates)} day(s) "
                f"from {dates[0]} to {dates[-1]}"
            )

        if args.dry_run:
            _print_dry_run(dates, schema)
            conn.close()
            return

        for target_date in dates:
            populate_day(conn, schema, target_date)
    finally:
        conn.close()

    if not args.no_flush:
        flush_valkey()

    logger.info(f"Done. Populated {len(dates)} day(s).")


if __name__ == "__main__":
    main()
