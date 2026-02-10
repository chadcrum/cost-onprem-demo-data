#!/usr/bin/env python3
"""
Generate truly varied demo data with parallel NISE execution (one per day).
Uses multiprocessing to run up to 12 concurrent NISE processes.
Ensures no consecutive days have the same (cpu, mem) values.
"""
import os
import sys
import subprocess
import tempfile
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path
from multiprocessing import Pool, cpu_count
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value, run_oc_command
from helpers import create_upload_package_from_files
from helpers import wait_for_provider, wait_for_summary_tables
import requests

# Seed for reproducible variations
random.seed(42)

# Base patterns for each cluster with realistic variations
def get_daily_config(cluster_id: str, date: datetime.date):
    """Get unique CPU/memory config for a specific date ensuring no duplicates."""
    weekday = date.weekday()  # 0=Mon, 6=Sun
    day = date.day
    
    # Add small time-based variation to ensure uniqueness
    time_factor = (day * 7 + weekday) / 100.0  # Creates unique decimal component
    
    if cluster_id == "demo-prod-cluster":
        # E-commerce pattern
        if 22 <= day <= 23:  # Promo event (Jan 22-23)
            base_cpu = 3.5
            base_mem = 7.0
            variation = 0.3
        elif weekday >= 5:  # Weekend
            base_cpu = 2.4
            base_mem = 4.8
            variation = 0.25
        elif weekday == 4:  # Friday - ramping up
            base_cpu = 1.9
            base_mem = 3.8
            variation = 0.15
        elif weekday == 0:  # Monday - recovering
            base_cpu = 1.3
            base_mem = 2.6
            variation = 0.12
        else:  # Tue-Thu baseline
            base_cpu = 1.6
            base_mem = 3.2
            variation = 0.15
        
        # Add unique daily variation
        daily_var = random.uniform(-variation, variation)
        cpu = round(base_cpu + daily_var + time_factor * 0.01, 3)
        mem = round(base_mem + daily_var * 2 + time_factor * 0.02, 3)
        
        return {"cpu": cpu, "mem": mem, "pattern": "ecommerce"}
    
    elif cluster_id == "demo-dev-cluster":
        # Dev/CI-CD pattern
        if day in [6, 13, 20, 27]:  # Build/release days
            base_cpu = 3.0
            base_mem = 6.0
            variation = 0.4
        elif weekday >= 5:  # Weekend - minimal
            base_cpu = 0.2
            base_mem = 0.5
            variation = 0.08
        elif day == 3:  # Holiday
            base_cpu = 0.15
            base_mem = 0.4
            variation = 0.05
        else:  # Regular workday
            base_cpu = 1.1
            base_mem = 2.2
            variation = 0.2
        
        # Add unique daily variation
        daily_var = random.uniform(-variation, variation)
        cpu = round(base_cpu + daily_var + time_factor * 0.01, 3)
        mem = round(base_mem + daily_var * 2 + time_factor * 0.02, 3)
        
        # Ensure minimum values
        cpu = max(0.1, cpu)
        mem = max(0.3, mem)
        
        return {"cpu": cpu, "mem": mem, "pattern": "devops"}
    
    elif cluster_id == "demo-staging-cluster":
        # Staging/load test pattern
        if day in [6, 13, 20, 27] or (day == 3 and date.month == 2):  # Deploy + load test days
            base_cpu = 2.8
            base_mem = 5.6
            variation = 0.35
        else:  # Regular testing days
            base_cpu = 1.0
            base_mem = 2.0
            variation = 0.25  # Increased from 0.18 to prevent duplicates
        
        # Add unique daily variation (increase time_factor weight)
        daily_var = random.uniform(-variation, variation)
        cpu = round(base_cpu + daily_var + time_factor * 0.02, 3)  # Increased from 0.01
        mem = round(base_mem + daily_var * 2 + time_factor * 0.04, 3)  # Increased from 0.02
        
        return {"cpu": cpu, "mem": mem, "pattern": "staging"}
    
    return {"cpu": 1.0, "mem": 2.0, "pattern": "default"}


def create_nise_static_config(cluster_id: str, cpu: float, mem: float, date: str) -> str:
    """Create NISE static config for a single day."""
    return f"""---
generators:
  - OCPGenerator:
      start_date: {date}
      end_date: {date}
      nodes:
        - node:
          node_name: {cluster_id}-worker-1
          cpu_cores: 16
          memory_gig: 64
          resource_id: {cluster_id}-node-1
          labels: node-role.kubernetes.io/worker:true
          namespaces:
            default:
              pods:
                - pod:
                  pod_name: app-1
                  cpu_request: 2.0
                  mem_request_gig: 4.0
                  cpu_limit: 4.0
                  mem_limit_gig: 8.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {cpu}
                  mem_usage_gig:
                    full_period: {mem}
                  labels: app:demo|component:frontend
                - pod:
                  pod_name: app-2
                  cpu_request: 1.5
                  mem_request_gig: 3.0
                  cpu_limit: 3.0
                  mem_limit_gig: 6.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {round(cpu * 0.67, 3)}
                  mem_usage_gig:
                    full_period: {round(mem * 0.67, 3)}
                  labels: app:demo|component:api
                - pod:
                  pod_name: db-1
                  cpu_request: 3.0
                  mem_request_gig: 8.0
                  cpu_limit: 6.0
                  mem_limit_gig: 16.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {round(cpu * 1.67, 3)}
                  mem_usage_gig:
                    full_period: {round(mem * 2.0, 3)}
                  labels: app:database|tier:data
"""


def generate_nise_for_single_day(args):
    """Generate NISE data for a single day. Designed to run in parallel."""
    cluster_id, date_str, config, work_dir = args
    
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    day_config = get_daily_config(cluster_id, date_obj)
    
    # Create static config
    static_yaml = create_nise_static_config(cluster_id, day_config["cpu"], day_config["mem"], date_str)
    yaml_path = os.path.join(work_dir, f"static_{cluster_id}_{date_str}.yml")
    with open(yaml_path, 'w') as f:
        f.write(static_yaml)
    
    # Run NISE
    nise_output = os.path.join(work_dir, f"nise_{cluster_id}_{date_str}")
    os.makedirs(nise_output, exist_ok=True)
    
    cmd = ['nise', 'report', 'ocp', '--static-report-file', yaml_path,
           '--ocp-cluster-id', cluster_id, '--ros-ocp-info', '-w']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=nise_output)
        if result.returncode != 0:
            return {"date": date_str, "status": "failed", "error": result.stderr, "config": day_config}
        
        # Collect generated files
        files = {"pod": [], "ros": [], "node_label": [], "namespace_label": []}
        for root, _, filenames in os.walk(nise_output):
            for filename in filenames:
                if not filename.endswith('.csv'):
                    continue
                filepath = os.path.join(root, filename)
                if 'pod_usage' in filename:
                    files["pod"].append(filepath)
                elif 'ros_usage' in filename:
                    files["ros"].append(filepath)
                elif 'node_label' in filename:
                    files["node_label"].append(filepath)
                elif 'namespace_label' in filename:
                    files["namespace_label"].append(filepath)
        
        return {"date": date_str, "status": "success", "files": files, "config": day_config}
    
    except Exception as e:
        return {"date": date_str, "status": "failed", "error": str(e), "config": day_config}


def merge_csv_files(file_list: list, output_path: str):
    """Merge multiple CSV files with same schema."""
    if not file_list:
        return
    
    with open(file_list[0], 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
    
    with open(output_path, 'w', newline='') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)
        
        for filepath in sorted(file_list):  # Sort to ensure chronological order
            with open(filepath, 'r') as infile:
                reader = csv.reader(infile)
                next(reader)
                for row in reader:
                    writer.writerow(row)


def get_cluster_config():
    return ClusterConfig(
        namespace=os.environ.get("NAMESPACE", "cost-onprem"),
        helm_release_name=os.environ.get("HELM_RELEASE_NAME", "cost-onprem"),
        keycloak_namespace=os.environ.get("KEYCLOAK_NAMESPACE", "keycloak"),
    )


def get_jwt_token(cluster_config: ClusterConfig) -> str:
    keycloak_url = get_route_url(cluster_config.keycloak_namespace, "keycloak")
    if not keycloak_url:
        raise RuntimeError("Keycloak route not found")
    client_secret = get_secret_value(
        cluster_config.keycloak_namespace,
        "keycloak-client-secret-cost-management-operator",
        "CLIENT_SECRET",
    )
    if not client_secret:
        raise RuntimeError("Client secret not found")
    resp = requests.post(
        f"{keycloak_url}/realms/kubernetes/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "cost-management-operator",
            "client_secret": client_secret,
        },
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def register_source_via_gateway(cluster_config: ClusterConfig, jwt_token: str,
                                cluster_id: str, display_name: str) -> str:
    gateway_url = get_route_url(cluster_config.namespace, f"{cluster_config.helm_release_name}-api")
    api_base = f"{gateway_url}/api/cost-management/v1"
    
    resp = requests.get(f"{api_base}/source_types", headers={"Authorization": f"Bearer {jwt_token}"},
                        verify=False, timeout=30)
    resp.raise_for_status()
    source_type_id = next((st["id"] for st in resp.json().get("data", []) if st.get("name") == "openshift"), None)
    
    if not source_type_id:
        raise RuntimeError("OpenShift source type not found")
    
    resp = requests.post(
        f"{api_base}/sources",
        json={"name": display_name, "source_type_id": source_type_id, "source_ref": cluster_id},
        headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
        verify=False, timeout=120
    )
    resp.raise_for_status()
    source_id = resp.json().get("id")
    
    if not source_id:
        raise RuntimeError(f"No source ID in response")
    
    # Create application
    app_resp = requests.get(f"{api_base}/application_types", headers={"Authorization": f"Bearer {jwt_token}"},
                           verify=False, timeout=30)
    if app_resp.status_code == 200:
        app_type_id = next((at["id"] for at in app_resp.json().get("data", [])
                           if at.get("name") == "/insights/platform/cost-management"), None)
        if app_type_id:
            requests.post(
                f"{api_base}/applications",
                json={"source_id": source_id, "application_type_id": app_type_id,
                     "extra": {"bucket": "koku-bucket", "cluster_id": cluster_id}},
                headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
                verify=False, timeout=30
            )
    
    return source_id


def upload_data_via_ingress(cluster_config: ClusterConfig, tar_path: str, jwt_token: str) -> dict:
    gateway_url = get_route_url(cluster_config.namespace, f"{cluster_config.helm_release_name}-api")
    upload_url = f"{gateway_url}/api/ingress/v1/upload"
    with open(tar_path, "rb") as f:
        files = {"file": ("cost-mgmt.tar.gz", f, "application/vnd.redhat.hccm.filename+tgz")}
        response = requests.post(upload_url, files=files, headers={"Authorization": f"Bearer {jwt_token}"},
                                verify=False, timeout=120)
        response.raise_for_status()
        return response.json()


def main():
    print("=" * 70)
    print("PARALLEL VARIED DEMO DATA GENERATION")
    print("Generating unique data for each day in parallel (up to 12 concurrent)")
    print("=" * 70)
    
    cluster_config = get_cluster_config()
    
    # Generate date list (last 10 days for realistic demo - MASU processes recent data)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=9)
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    print(f"\nConfig:")
    print(f"  Namespace: {cluster_config.namespace}")
    print(f"  Date range: {start_date} to {end_date} ({len(dates)} days)")
    print(f"  Max parallel workers: {min(12, cpu_count())}")
    
    print("\n[1/2] Obtaining JWT token...")
    jwt_token = get_jwt_token(cluster_config)
    print("  ✅ JWT token obtained")
    
    # Cluster definitions
    clusters = {
        "demo-prod-cluster": {"name": "Production E-commerce", "desc": "E-commerce with weekend spikes and promo"},
        "demo-dev-cluster": {"name": "Development & CI/CD", "desc": "Dev with working hours and build spikes"},
        "demo-staging-cluster": {"name": "Staging & Load Testing", "desc": "Staging with deployment waves"},
    }
    
    results = []
    
    for cluster_id, cluster_info in clusters.items():
        print(f"\n{'=' * 70}")
        print(f"CLUSTER: {cluster_info['name']}")
        print(f"{'=' * 70}")
        print(f"  Cluster ID: {cluster_id}")
        print(f"  Description: {cluster_info['desc']}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Prepare arguments for parallel execution
                print(f"\n  [Step 1/5] Generating {len(dates)} days in parallel...")
                args_list = [(cluster_id, date_str, cluster_info, temp_dir) for date_str in dates]
                
                # Run parallel NISE generation
                with Pool(processes=min(12, cpu_count())) as pool:
                    day_results = pool.map(generate_nise_for_single_day, args_list)
                
                # Check results and show sample configs
                successful = [r for r in day_results if r["status"] == "success"]
                failed = [r for r in day_results if r["status"] == "failed"]
                
                print(f"    ✅ Generated {len(successful)}/{len(dates)} days successfully")
                if failed:
                    print(f"    ⚠️  {len(failed)} days failed")
                
                # Show sample of daily configs to verify variation
                print(f"\n    Sample daily configs (first 5 days):")
                for r in successful[:5]:
                    cfg = r["config"]
                    print(f"      {r['date']}: cpu={cfg['cpu']:.3f}, mem={cfg['mem']:.3f} ({cfg['pattern']})")
                
                # Verify no consecutive duplicates
                prev_config = None
                duplicates = []
                for r in sorted(successful, key=lambda x: x["date"]):
                    cfg = r["config"]
                    if prev_config and (cfg["cpu"], cfg["mem"]) == prev_config:
                        duplicates.append(r["date"])
                    prev_config = (cfg["cpu"], cfg["mem"])
                
                if duplicates:
                    print(f"    ⚠️  WARNING: {len(duplicates)} consecutive duplicates found!")
                else:
                    print(f"    ✅ No consecutive duplicate (cpu, mem) pairs")
                
                # Merge CSV files
                print(f"\n  [Step 2/5] Merging CSV files...")
                merged_dir = os.path.join(temp_dir, 'merged')
                os.makedirs(merged_dir, exist_ok=True)
                
                all_pod_files = []
                all_ros_files = []
                all_node_files = []
                all_ns_files = []
                
                for r in successful:
                    all_pod_files.extend(r["files"]["pod"])
                    all_ros_files.extend(r["files"]["ros"])
                    all_node_files.extend(r["files"]["node_label"])
                    all_ns_files.extend(r["files"]["namespace_label"])
                
                merged_pod = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_pod_usage.csv")
                merged_ros = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_ros_usage.csv")
                merged_node = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_node_label.csv")
                merged_ns = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_namespace_label.csv")
                
                merge_csv_files(all_pod_files, merged_pod)
                merge_csv_files(all_ros_files, merged_ros)
                merge_csv_files(all_node_files, merged_node)
                merge_csv_files(all_ns_files, merged_ns)
                
                print(f"    ✅ Merged {len(all_pod_files)} pod files")
                
                # Register source
                print(f"\n  [Step 3/5] Registering source...")
                source_id = register_source_via_gateway(cluster_config, jwt_token, cluster_id, cluster_info["name"])
                print(f"    ✅ Source registered: {source_id}")
                
                # Create upload package
                print(f"\n  [Step 4/5] Creating upload package...")
                package_path = create_upload_package_from_files(
                    pod_usage_files=[merged_pod],
                    ros_usage_files=[merged_ros],
                    cluster_id=cluster_id,
                    start_date=datetime.combine(start_date, datetime.min.time()),
                    end_date=datetime.combine(end_date, datetime.min.time()),
                    node_label_files=[merged_node],
                    namespace_label_files=[merged_ns],
                )
                print(f"    ✅ Package: {os.path.getsize(package_path) / 1024:.1f} KB")
                
                # Upload
                print(f"\n  [Step 5/5] Uploading data...")
                upload_response = upload_data_via_ingress(cluster_config, package_path, jwt_token)
                print(f"    ✅ Uploaded: {upload_response.get('request_id', 'N/A')}")
                
                results.append({"cluster_id": cluster_id, "source_id": source_id, "status": "uploaded"})
                
            except Exception as e:
                print(f"    ❌ Failed: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    # Wait for processing
    print(f"\n{'=' * 70}")
    print("WAITING FOR DATA PROCESSING")
    print(f"{'=' * 70}")
    
    db_pod = run_oc_command(
        ["get", "pods", "-n", cluster_config.namespace, "-l", "app.kubernetes.io/component=database",
         "-o", "jsonpath={.items[0].metadata.name}"],
        check=False,
    ).stdout.strip()
    
    for result in results:
        cluster_id = result["cluster_id"]
        print(f"\n  Processing {cluster_id}...")
        
        if wait_for_provider(cluster_config.namespace, db_pod, cluster_id, timeout=300):
            print(f"    ✅ Provider created")
        
        schema_name = wait_for_summary_tables(cluster_config.namespace, db_pod, cluster_id, timeout=600)
        if schema_name:
            print(f"    ✅ Summary tables populated")
    
    print(f"\n{'=' * 70}")
    print("✅ PARALLEL VARIED DATA GENERATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n✨ Generated {len(results)} clusters with unique daily values!")
    print("\n🎯 Realistic cost patterns with NO consecutive duplicates")


if __name__ == "__main__":
    main()
