-- ============================================================================
-- COMPREHENSIVE DEMO DATA: 8 clusters × 6 days (Feb 1-6, 2026)
-- Realistic daily variation with weekday/weekend and growth patterns
-- ============================================================================

-- Clean existing demo data from partitioned tables
DELETE FROM orgorg1234567.reporting_ocp_cost_summary_p;
DELETE FROM orgorg1234567.reporting_ocp_cost_summary_by_project_p;
DELETE FROM orgorg1234567.reporting_ocp_pod_summary_p;
DELETE FROM orgorg1234567.reporting_ocp_pod_summary_by_node_p;

-- ============================================================================
-- CLUSTER CONFIG: (cluster_id, cluster_alias, source_uuid, base_cpu, base_mem, base_cost)
-- base_cost = daily cost baseline; each day gets a multiplier for variation
-- ============================================================================
-- prod-data-pipeline:     high compute, growing trend
-- prod-api-gateway:       steady high, slight daily variation
-- prod-ecommerce-us-east: weekday-heavy pattern
-- prod-ecommerce-eu:      weekday-heavy, slightly lower
-- staging-performance:    spiky (load tests mid-week)
-- qa-automation:          weekday-only (low weekends)
-- dev-feature-team-a:     moderate, steady
-- dev-feature-team-b:     low, growing (new team ramping up)

-- Day multipliers to create realistic patterns:
-- Feb 1 (Sun): 0.6  (weekend low)
-- Feb 2 (Mon): 1.0  (normal weekday)
-- Feb 3 (Tue): 1.05 (slight growth)
-- Feb 4 (Wed): 1.15 (mid-week peak)
-- Feb 5 (Thu): 1.10 (still high)
-- Feb 6 (Fri): 0.95 (Friday wind-down)

-- ============================================================================
-- 1. COST SUMMARY (reporting_ocp_cost_summary_p) - Main cost chart
-- ============================================================================
INSERT INTO orgorg1234567.reporting_ocp_cost_summary_p (
  usage_start, usage_end, cluster_id, cluster_alias,
  infrastructure_raw_cost, infrastructure_markup_cost,
  infrastructure_monthly_cost_json, distributed_cost,
  source_uuid, raw_currency
)
SELECT 
  d.day::date as usage_start,
  d.day::date as usage_end,
  c.cluster_id,
  c.cluster_alias,
  ROUND((c.base_cost * d.multiplier * (1 + (random()-0.5)*0.1))::numeric, 2) as infrastructure_raw_cost,
  0 as infrastructure_markup_cost,
  '{}'::jsonb as infrastructure_monthly_cost_json,
  ROUND((c.base_cost * d.multiplier * (1 + (random()-0.5)*0.1))::numeric, 2) as distributed_cost,
  c.source_uuid::uuid,
  'USD'
FROM (VALUES
  ('prod-data-pipeline',     'prod-data-pipeline',     '6cbf9ebd-bffc-46c9-b414-d422c28fdb8f', 10.5,  21.0,  11.23),
  ('prod-api-gateway',       'prod-api-gateway',       '6a04e4e4-d486-4a6f-a49b-cc1db63bf92e',  8.2,  16.4,   8.86),
  ('prod-ecommerce-us-east', 'prod-ecommerce-us-east', '5942da9c-1322-48ab-ac60-bfad97cf013d',  6.4,  12.8,   6.91),
  ('prod-ecommerce-eu',      'prod-ecommerce-eu',      '263dd1a0-90e1-4879-bdda-917bc52daa37',  5.6,  11.2,   6.05),
  ('staging-performance',    'staging-performance',    '5207cee1-29dd-4097-9b4d-9efe714d065a',  4.8,   9.6,   5.18),
  ('qa-automation',          'qa-automation',          '94564ef6-39ea-452f-8e04-76d7302836bc',  3.8,   7.6,   4.10),
  ('dev-feature-team-a',     'dev-feature-team-a',     'd58f09e8-1a60-4253-9a25-3657c10bd087',  2.6,   5.2,   2.81),
  ('dev-feature-team-b',     'dev-feature-team-b',     '65a4ed0e-b7c5-44e1-abec-e37dfd791657',  1.4,   2.8,   1.51)
) AS c(cluster_id, cluster_alias, source_uuid, base_cpu, base_mem, base_cost)
CROSS JOIN (VALUES
  ('2026-02-01', 0.60),
  ('2026-02-02', 1.00),
  ('2026-02-03', 1.05),
  ('2026-02-04', 1.15),
  ('2026-02-05', 1.10),
  ('2026-02-06', 0.95)
) AS d(day, multiplier);

-- ============================================================================
-- 2. COST SUMMARY BY PROJECT (reporting_ocp_cost_summary_by_project_p)
--    Each cluster gets 2-3 namespaces for project breakdown
-- ============================================================================
INSERT INTO orgorg1234567.reporting_ocp_cost_summary_by_project_p (
  usage_start, usage_end, cluster_id, cluster_alias, namespace,
  infrastructure_raw_cost, infrastructure_markup_cost,
  distributed_cost, source_uuid, raw_currency
)
SELECT 
  d.day::date, d.day::date,
  c.cluster_id, c.cluster_alias, ns.namespace,
  ROUND((c.base_cost * d.multiplier * ns.cost_share * (1 + (random()-0.5)*0.08))::numeric, 2),
  0,
  ROUND((c.base_cost * d.multiplier * ns.cost_share * (1 + (random()-0.5)*0.08))::numeric, 2),
  c.source_uuid::uuid,
  'USD'
FROM (VALUES
  ('prod-data-pipeline',     'prod-data-pipeline',     '6cbf9ebd-bffc-46c9-b414-d422c28fdb8f', 11.23),
  ('prod-api-gateway',       'prod-api-gateway',       '6a04e4e4-d486-4a6f-a49b-cc1db63bf92e',  8.86),
  ('prod-ecommerce-us-east', 'prod-ecommerce-us-east', '5942da9c-1322-48ab-ac60-bfad97cf013d',  6.91),
  ('prod-ecommerce-eu',      'prod-ecommerce-eu',      '263dd1a0-90e1-4879-bdda-917bc52daa37',  6.05),
  ('staging-performance',    'staging-performance',    '5207cee1-29dd-4097-9b4d-9efe714d065a',  5.18),
  ('qa-automation',          'qa-automation',          '94564ef6-39ea-452f-8e04-76d7302836bc',  4.10),
  ('dev-feature-team-a',     'dev-feature-team-a',     'd58f09e8-1a60-4253-9a25-3657c10bd087',  2.81),
  ('dev-feature-team-b',     'dev-feature-team-b',     '65a4ed0e-b7c5-44e1-abec-e37dfd791657',  1.51)
) AS c(cluster_id, cluster_alias, source_uuid, base_cost)
CROSS JOIN (VALUES
  ('2026-02-01', 0.60),
  ('2026-02-02', 1.00),
  ('2026-02-03', 1.05),
  ('2026-02-04', 1.15),
  ('2026-02-05', 1.10),
  ('2026-02-06', 0.95)
) AS d(day, multiplier)
CROSS JOIN (VALUES
  ('default',     0.50),
  ('monitoring',  0.30),
  ('kube-system', 0.20)
) AS ns(namespace, cost_share);

-- ============================================================================
-- 3. POD SUMMARY (reporting_ocp_pod_summary_p) - CPU & Memory charts
-- ============================================================================
INSERT INTO orgorg1234567.reporting_ocp_pod_summary_p (
  usage_start, usage_end, cluster_id, cluster_alias,
  data_source, resource_count,
  infrastructure_raw_cost, infrastructure_markup_cost,
  infrastructure_monthly_cost_json,
  distributed_cost,
  pod_usage_cpu_core_hours, pod_request_cpu_core_hours,
  pod_limit_cpu_core_hours,
  pod_usage_memory_gigabyte_hours, pod_request_memory_gigabyte_hours,
  pod_limit_memory_gigabyte_hours,
  cluster_capacity_cpu_core_hours, cluster_capacity_memory_gigabyte_hours,
  source_uuid, raw_currency
)
SELECT 
  d.day::date, d.day::date,
  c.cluster_id, c.cluster_alias,
  'Pod', 15,
  ROUND((c.base_cost * d.multiplier * (1 + (random()-0.5)*0.1))::numeric, 2),
  0,
  '{}'::jsonb,
  ROUND((c.base_cost * d.multiplier * (1 + (random()-0.5)*0.1))::numeric, 2),
  -- CPU: usage ~60-80% of request, request ~70% of limit
  ROUND((c.base_cpu * d.multiplier * (0.6 + random()*0.2))::numeric, 2),   -- usage
  ROUND((c.base_cpu * d.multiplier * 1.0)::numeric, 2),                     -- request
  ROUND((c.base_cpu * d.multiplier * 1.4)::numeric, 2),                     -- limit
  -- Memory: usage ~70-90% of request
  ROUND((c.base_mem * d.multiplier * (0.7 + random()*0.2))::numeric, 2),   -- usage
  ROUND((c.base_mem * d.multiplier * 1.0)::numeric, 2),                     -- request
  ROUND((c.base_mem * d.multiplier * 1.3)::numeric, 2),                     -- limit
  -- Cluster capacity (fixed per cluster)
  384.0,   -- 16 cores × 24 hours
  1536.0,  -- 64 GB × 24 hours
  c.source_uuid::uuid,
  'USD'
FROM (VALUES
  ('prod-data-pipeline',     'prod-data-pipeline',     '6cbf9ebd-bffc-46c9-b414-d422c28fdb8f', 10.5,  21.0,  11.23),
  ('prod-api-gateway',       'prod-api-gateway',       '6a04e4e4-d486-4a6f-a49b-cc1db63bf92e',  8.2,  16.4,   8.86),
  ('prod-ecommerce-us-east', 'prod-ecommerce-us-east', '5942da9c-1322-48ab-ac60-bfad97cf013d',  6.4,  12.8,   6.91),
  ('prod-ecommerce-eu',      'prod-ecommerce-eu',      '263dd1a0-90e1-4879-bdda-917bc52daa37',  5.6,  11.2,   6.05),
  ('staging-performance',    'staging-performance',    '5207cee1-29dd-4097-9b4d-9efe714d065a',  4.8,   9.6,   5.18),
  ('qa-automation',          'qa-automation',          '94564ef6-39ea-452f-8e04-76d7302836bc',  3.8,   7.6,   4.10),
  ('dev-feature-team-a',     'dev-feature-team-a',     'd58f09e8-1a60-4253-9a25-3657c10bd087',  2.6,   5.2,   2.81),
  ('dev-feature-team-b',     'dev-feature-team-b',     '65a4ed0e-b7c5-44e1-abec-e37dfd791657',  1.4,   2.8,   1.51)
) AS c(cluster_id, cluster_alias, source_uuid, base_cpu, base_mem, base_cost)
CROSS JOIN (VALUES
  ('2026-02-01', 0.60),
  ('2026-02-02', 1.00),
  ('2026-02-03', 1.05),
  ('2026-02-04', 1.15),
  ('2026-02-05', 1.10),
  ('2026-02-06', 0.95)
) AS d(day, multiplier);

-- ============================================================================
-- 4. POD SUMMARY BY NODE (reporting_ocp_pod_summary_by_node_p) - Node breakdown
-- ============================================================================
INSERT INTO orgorg1234567.reporting_ocp_pod_summary_by_node_p (
  usage_start, usage_end, cluster_id, cluster_alias, node,
  data_source, resource_count,
  infrastructure_raw_cost, infrastructure_markup_cost,
  infrastructure_monthly_cost_json,
  distributed_cost,
  pod_usage_cpu_core_hours, pod_request_cpu_core_hours,
  pod_limit_cpu_core_hours,
  pod_usage_memory_gigabyte_hours, pod_request_memory_gigabyte_hours,
  pod_limit_memory_gigabyte_hours,
  node_capacity_cpu_core_hours, cluster_capacity_cpu_core_hours,
  node_capacity_memory_gigabyte_hours, cluster_capacity_memory_gigabyte_hours,
  source_uuid, raw_currency
)
SELECT 
  d.day::date, d.day::date,
  c.cluster_id, c.cluster_alias, n.node_name,
  'Pod', 5,
  ROUND((c.base_cost * d.multiplier * n.node_share * (1 + (random()-0.5)*0.1))::numeric, 2),
  0,
  '{}'::jsonb,
  ROUND((c.base_cost * d.multiplier * n.node_share * (1 + (random()-0.5)*0.1))::numeric, 2),
  ROUND((c.base_cpu * d.multiplier * n.node_share * (0.6 + random()*0.2))::numeric, 2),
  ROUND((c.base_cpu * d.multiplier * n.node_share)::numeric, 2),
  ROUND((c.base_cpu * d.multiplier * n.node_share * 1.4)::numeric, 2),
  ROUND((c.base_mem * d.multiplier * n.node_share * (0.7 + random()*0.2))::numeric, 2),
  ROUND((c.base_mem * d.multiplier * n.node_share)::numeric, 2),
  ROUND((c.base_mem * d.multiplier * n.node_share * 1.3)::numeric, 2),
  128.0,  -- node: 128 cpu-hours (single node)
  384.0,
  512.0,
  1536.0,
  c.source_uuid::uuid,
  'USD'
FROM (VALUES
  ('prod-data-pipeline',     'prod-data-pipeline',     '6cbf9ebd-bffc-46c9-b414-d422c28fdb8f', 10.5,  21.0,  11.23),
  ('prod-api-gateway',       'prod-api-gateway',       '6a04e4e4-d486-4a6f-a49b-cc1db63bf92e',  8.2,  16.4,   8.86),
  ('prod-ecommerce-us-east', 'prod-ecommerce-us-east', '5942da9c-1322-48ab-ac60-bfad97cf013d',  6.4,  12.8,   6.91),
  ('prod-ecommerce-eu',      'prod-ecommerce-eu',      '263dd1a0-90e1-4879-bdda-917bc52daa37',  5.6,  11.2,   6.05),
  ('staging-performance',    'staging-performance',    '5207cee1-29dd-4097-9b4d-9efe714d065a',  4.8,   9.6,   5.18),
  ('qa-automation',          'qa-automation',          '94564ef6-39ea-452f-8e04-76d7302836bc',  3.8,   7.6,   4.10),
  ('dev-feature-team-a',     'dev-feature-team-a',     'd58f09e8-1a60-4253-9a25-3657c10bd087',  2.6,   5.2,   2.81),
  ('dev-feature-team-b',     'dev-feature-team-b',     '65a4ed0e-b7c5-44e1-abec-e37dfd791657',  1.4,   2.8,   1.51)
) AS c(cluster_id, cluster_alias, source_uuid, base_cpu, base_mem, base_cost)
CROSS JOIN (VALUES
  ('2026-02-01', 0.60),
  ('2026-02-02', 1.00),
  ('2026-02-03', 1.05),
  ('2026-02-04', 1.15),
  ('2026-02-05', 1.10),
  ('2026-02-06', 0.95)
) AS d(day, multiplier)
CROSS JOIN (VALUES
  ('worker-1', 0.45),
  ('worker-2', 0.35),
  ('worker-3', 0.20)
) AS n(node_name, node_share);

-- ============================================================================
-- VERIFY
-- ============================================================================
SELECT '=== COST SUMMARY ===' as info;
SELECT usage_start, COUNT(DISTINCT cluster_id) as clusters, 
       ROUND(SUM(infrastructure_raw_cost)::numeric, 2) as daily_cost
FROM orgorg1234567.reporting_ocp_cost_summary_p
GROUP BY usage_start ORDER BY usage_start;

SELECT '=== PROJECT BREAKDOWN ===' as info;
SELECT namespace, COUNT(*) as rows, ROUND(SUM(infrastructure_raw_cost)::numeric, 2) as total_cost
FROM orgorg1234567.reporting_ocp_cost_summary_by_project_p
GROUP BY namespace ORDER BY total_cost DESC;

SELECT '=== POD SUMMARY ===' as info;
SELECT usage_start, COUNT(DISTINCT cluster_id) as clusters,
       ROUND(SUM(pod_usage_cpu_core_hours)::numeric, 1) as cpu_hours,
       ROUND(SUM(pod_usage_memory_gigabyte_hours)::numeric, 1) as mem_gb_hours
FROM orgorg1234567.reporting_ocp_pod_summary_p
GROUP BY usage_start ORDER BY usage_start;

SELECT '=== TOTAL ===' as info;
SELECT 
  COUNT(DISTINCT cluster_id) as total_clusters,
  COUNT(DISTINCT usage_start) as total_days,
  ROUND(SUM(infrastructure_raw_cost)::numeric, 2) as total_cost
FROM orgorg1234567.reporting_ocp_cost_summary_p;
