#!/bin/bash
# Quick batch insert for 8 diverse clusters (Feb 5, 2026)

set -e

echo "======================================================================="
echo "BATCH INSERT: 8 DIVERSE CLUSTERS (Feb 5, 2026)"
echo "======================================================================="

# Cluster definitions: id, cpu_hours (24h total), mem_gb_hours (24h total), description
declare -a CLUSTERS=(
  "prod-data-pipeline|124.8|249.6|Production Data Pipeline"
  "prod-api-gateway|98.4|196.8|Production API Gateway"  
  "prod-ecommerce-us-east|76.8|153.6|Production E-commerce US-East"
  "prod-ecommerce-eu|67.2|134.4|Production E-commerce EU"
  "staging-performance|57.6|115.2|Staging Performance Testing"
  "qa-automation|45.6|91.2|QA Automation"
  "dev-feature-team-a|31.2|62.4|Development Team A"
  "dev-feature-team-b|16.8|33.6|Development Team B"
)

echo ""
echo "Inserting 8 clusters with varied usage:"
echo ""

for cluster_def in "${CLUSTERS[@]}"; do
  IFS='|' read -r cluster_id cpu_hrs mem_hrs desc <<< "$cluster_def"
  
  # Calculate costs (simplified: $0.05/CPU-hour + $0.02/GB-hour)
  cost=$(echo "$cpu_hrs * 0.05 + $mem_hrs * 0.02" | bc -l | xargs printf "%.2f")
  
  echo "  • $desc: ${cpu_hrs} CPU-hours, ${mem_hrs} GB-hours = \$$cost"
  
  # Insert 3 rows per cluster (simulating 3 pods)
  oc exec -n cost-onprem cost-onprem-database-0 -- psql -U koku_user -d costonprem_koku -c "
INSERT INTO orgorg1234567.reporting_ocpusagelineitem_daily_summary (
    uuid, cluster_id, cluster_alias, data_source, namespace, node, resource_id,
    usage_start, usage_end,
    pod_labels,
    pod_usage_cpu_core_hours, pod_request_cpu_core_hours, pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours, pod_request_memory_gigabyte_hours, pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_core_hours, cluster_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours, cluster_capacity_memory_gigabyte_hours,
    infrastructure_raw_cost, infrastructure_project_raw_cost,
    source_uuid
) VALUES 
(gen_random_uuid(), '${cluster_id}', '${cluster_id}', 'Pod', 'default', 'worker-1', 'app-primary',
 '2026-02-05', '2026-02-05', '{\"app\":\"primary\"}',
 $(echo "$cpu_hrs * 0.5" | bc -l), $(echo "$cpu_hrs * 0.4" | bc -l), $(echo "$cpu_hrs * 0.6" | bc -l),
 $(echo "$mem_hrs * 0.5" | bc -l), $(echo "$mem_hrs * 0.4" | bc -l), $(echo "$mem_hrs * 0.6" | bc -l),
 384, 384, 1536, 1536,
 $(echo "$cost * 0.5" | bc -l), $(echo "$cost * 0.5" | bc -l),
 '00000000-0000-0000-0000-000000000001'),
(gen_random_uuid(), '${cluster_id}', '${cluster_id}', 'Pod', 'default', 'worker-1', 'app-secondary',
 '2026-02-05', '2026-02-05', '{\"app\":\"secondary\"}',
 $(echo "$cpu_hrs * 0.3" | bc -l), $(echo "$cpu_hrs * 0.25" | bc -l), $(echo "$cpu_hrs * 0.35" | bc -l),
 $(echo "$mem_hrs * 0.3" | bc -l), $(echo "$mem_hrs * 0.25" | bc -l), $(echo "$mem_hrs * 0.35" | bc -l),
 384, 384, 1536, 1536,
 $(echo "$cost * 0.3" | bc -l), $(echo "$cost * 0.3" | bc -l),
 '00000000-0000-0000-0000-000000000001'),
(gen_random_uuid(), '${cluster_id}', '${cluster_id}', 'Pod', 'default', 'worker-1', 'database',
 '2026-02-05', '2026-02-05', '{\"app\":\"database\"}',
 $(echo "$cpu_hrs * 0.2" | bc -l), $(echo "$cpu_hrs * 0.15" | bc -l), $(echo "$cpu_hrs * 0.25" | bc -l),
 $(echo "$mem_hrs * 0.2" | bc -l), $(echo "$mem_hrs * 0.15" | bc -l), $(echo "$mem_hrs * 0.25" | bc -l),
 384, 384, 1536, 1536,
 $(echo "$cost * 0.2" | bc -l), $(echo "$cost * 0.2" | bc -l),
 '00000000-0000-0000-0000-000000000001')
ON CONFLICT DO NOTHING;
" >/dev/null 2>&1

done

echo ""
echo "======================================================================="
echo "✅ COMPLETE - 8 diverse clusters inserted!"
echo "======================================================================="
echo ""
echo "Verifying data..."
oc exec -n cost-onprem cost-onprem-database-0 -- psql -U koku_user -d costonprem_koku -c "
SELECT 
  cluster_id,
  ROUND(SUM(pod_usage_cpu_core_hours)::numeric, 1) as cpu_hours,
  ROUND(SUM(pod_usage_memory_gigabyte_hours)::numeric, 1) as mem_gb_hours,
  ROUND(SUM(infrastructure_raw_cost)::numeric, 2) as cost_usd
FROM orgorg1234567.reporting_ocpusagelineitem_daily_summary
WHERE usage_start = '2026-02-05'
GROUP BY cluster_id
ORDER BY SUM(pod_usage_cpu_core_hours) DESC;
"

echo ""
echo "🎯 Demo ready with 7.4x cost variation!"
echo "💡 Data visible immediately in UI (no MASU processing needed)"
