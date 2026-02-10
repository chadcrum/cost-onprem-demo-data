#!/usr/bin/env python3
"""
Generate truly varied demo data by running NISE multiple times with different configs.
Creates realistic cost trends by varying resource values across time periods.
"""
import os
import sys
import subprocess
import tempfile
import csv
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value, run_oc_command
from helpers import create_upload_package_from_files
from helpers import wait_for_provider, wait_for_summary_tables
import requests

# Cluster configs with time period variations
CLUSTER_CONFIGS = {
    "demo-prod-cluster": {
        "display_name": "Production E-commerce",
        "description": "E-commerce with weekend spikes and promo event",
        "periods": [
            # Weekdays - baseline
            {"dates": ["2026-01-01", "2026-01-02", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
                       "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21",
                       "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30", "2026-02-02", "2026-02-03", "2026-02-04"],
             "cpu": 1.5, "mem": 3.0, "pattern": "weekday"},
            # Weekends - spike
            {"dates": ["2026-01-03", "2026-01-04", "2026-01-05", "2026-01-10", "2026-01-11", "2026-01-12",
                       "2026-01-17", "2026-01-18", "2026-01-19", "2026-01-24", "2026-01-25", "2026-01-26",
                       "2026-01-31", "2026-02-01", "2026-02-05"],
             "cpu": 2.7, "mem": 5.4, "pattern": "weekend"},
            # Promo event - major spike
            {"dates": ["2026-01-22", "2026-01-23"],
             "cpu": 3.75, "mem": 7.5, "pattern": "promo"},
        ],
    },
    "demo-dev-cluster": {
        "display_name": "Development & CI/CD",
        "description": "Dev with working hours and build spikes",
        "periods": [
            # Weekends - minimal
            {"dates": ["2026-01-03", "2026-01-04", "2026-01-05", "2026-01-10", "2026-01-11", "2026-01-12",
                       "2026-01-17", "2026-01-18", "2026-01-19", "2026-01-24", "2026-01-25", "2026-01-26",
                       "2026-01-31", "2026-02-01", "2026-02-02"],
             "cpu": 0.22, "mem": 0.6, "pattern": "weekend"},
            # Build days - spike
            {"dates": ["2026-01-06", "2026-01-13", "2026-01-20", "2026-01-27"],
             "cpu": 3.3, "mem": 6.0, "pattern": "build"},
            # Regular workdays - baseline
            {"dates": ["2026-01-01", "2026-01-02", "2026-01-07", "2026-01-08", "2026-01-09",
                       "2026-01-14", "2026-01-15", "2026-01-16", "2026-01-21", "2026-01-22", "2026-01-23",
                       "2026-01-28", "2026-01-29", "2026-01-30", "2026-02-03", "2026-02-04", "2026-02-05"],
             "cpu": 1.2, "mem": 2.4, "pattern": "workday"},
        ],
    },
    "demo-staging-cluster": {
        "display_name": "Staging & Load Testing",
        "description": "Staging with deployment waves and load tests",
        "periods": [
            # Deploy + load test days - spike
            {"dates": ["2026-01-06", "2026-01-13", "2026-01-20", "2026-01-27", "2026-02-03"],
             "cpu": 3.0, "mem": 6.0, "pattern": "loadtest"},
            # Regular testing days - baseline
            {"dates": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05",
                       "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10", "2026-01-11", "2026-01-12",
                       "2026-01-14", "2026-01-15", "2026-01-16", "2026-01-17", "2026-01-18", "2026-01-19",
                       "2026-01-21", "2026-01-22", "2026-01-23", "2026-01-24", "2026-01-25", "2026-01-26",
                       "2026-01-28", "2026-01-29", "2026-01-30", "2026-01-31",
                       "2026-02-01", "2026-02-02", "2026-02-04", "2026-02-05"],
             "cpu": 1.05, "mem": 2.1, "pattern": "normal"},
        ],
    },
}


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


def create_nise_static_config(cluster_id: str, cpu: float, mem: float, start_date: str, end_date: str) -> str:
    """Create NISE static config with specific resource values."""
    return f"""---
generators:
  - OCPGenerator:
      start_date: {start_date}
      end_date: {end_date}
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
                  labels: app:demo|env:prod
                - pod:
                  pod_name: app-2
                  cpu_request: 1.5
                  mem_request_gig: 3.0
                  cpu_limit: 3.0
                  mem_limit_gig: 6.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {cpu * 0.67}
                  mem_usage_gig:
                    full_period: {mem * 0.67}
                  labels: app:demo|env:prod
                - pod:
                  pod_name: db-1
                  cpu_request: 3.0
                  mem_request_gig: 8.0
                  cpu_limit: 6.0
                  mem_limit_gig: 16.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {cpu * 1.67}
                  mem_usage_gig:
                    full_period: {mem * 2.0}
                  labels: app:database|tier:data
"""


def generate_nise_data_for_period(cluster_id: str, period_config: dict, work_dir: str) -> dict:
    """Generate NISE data for a specific time period."""
    dates = period_config["dates"]
    cpu = period_config["cpu"]
    mem = period_config["mem"]
    pattern = period_config["pattern"]
    
    # Group consecutive dates
    date_ranges = []
    current_start = None
    prev_date = None
    
    for date_str in sorted(dates):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        if current_start is None:
            current_start = date_obj
            prev_date = date_obj
        elif (date_obj - prev_date).days == 1:
            # Consecutive day
            prev_date = date_obj
        else:
            # Gap - save current range and start new one
            date_ranges.append((current_start, prev_date))
            current_start = date_obj
            prev_date = date_obj
    
    # Don't forget the last range
    if current_start is not None:
        date_ranges.append((current_start, prev_date))
    
    all_files = {"pod": [], "ros": [], "node_label": [], "namespace_label": []}
    
    for start_date, end_date in date_ranges:
        # Create static config for this range
        static_yaml = create_nise_static_config(
            cluster_id, cpu, mem,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )
        
        yaml_path = os.path.join(work_dir, f"static_{pattern}_{start_date}_{end_date}.yml")
        with open(yaml_path, 'w') as f:
            f.write(static_yaml)
        
        # Run NISE
        nise_output = os.path.join(work_dir, f"nise_{pattern}_{start_date}_{end_date}")
        os.makedirs(nise_output, exist_ok=True)
        
        cmd = ['nise', 'report', 'ocp', '--static-report-file', yaml_path,
               '--ocp-cluster-id', cluster_id, '--ros-ocp-info', '-w']
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=nise_output)
        if result.returncode != 0:
            raise RuntimeError(f"NISE failed for {pattern} {start_date}-{end_date}: {result.stderr}")
        
        # Collect generated files
        for root, _, filenames in os.walk(nise_output):
            for filename in filenames:
                if not filename.endswith('.csv'):
                    continue
                
                filepath = os.path.join(root, filename)
                if 'pod_usage' in filename:
                    all_files["pod"].append(filepath)
                elif 'ros_usage' in filename:
                    all_files["ros"].append(filepath)
                elif 'node_label' in filename:
                    all_files["node_label"].append(filepath)
                elif 'namespace_label' in filename:
                    all_files["namespace_label"].append(filepath)
    
    return all_files


def merge_csv_files(file_list: list, output_path: str):
    """Merge multiple CSV files with same schema."""
    if not file_list:
        return
    
    # Read header from first file
    with open(file_list[0], 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
    
    # Write merged file
    with open(output_path, 'w', newline='') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)
        
        for filepath in file_list:
            with open(filepath, 'r') as infile:
                reader = csv.reader(infile)
                next(reader)  # Skip header
                for row in reader:
                    writer.writerow(row)


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
    print("TRULY VARIED DEMO DATA GENERATION")
    print("Multi-period NISE generation with different resource configs")
    print("=" * 70)
    
    cluster_config = get_cluster_config()
    
    print(f"\nCluster Config:")
    print(f"  Namespace: {cluster_config.namespace}")
    print(f"  Release: {cluster_config.helm_release_name}")
    
    print("\n[1/2] Obtaining JWT token...")
    jwt_token = get_jwt_token(cluster_config)
    print("  ✅ JWT token obtained")
    
    results = []
    
    for cluster_id, config in CLUSTER_CONFIGS.items():
        print(f"\n{'=' * 70}")
        print(f"CLUSTER: {config['display_name']}")
        print(f"{'=' * 70}")
        print(f"  Cluster ID: {cluster_id}")
        print(f"  Description: {config['description']}")
        print(f"  Periods: {len(config['periods'])}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Generate data for each period
                print(f"\n  [Step 1/5] Generating varied NISE data for {len(config['periods'])} periods...")
                
                combined_files = {"pod": [], "ros": [], "node_label": [], "namespace_label": []}
                
                for period in config['periods']:
                    pattern = period["pattern"]
                    num_dates = len(period["dates"])
                    print(f"    - {pattern}: {num_dates} dates (cpu={period['cpu']}, mem={period['mem']})")
                    
                    period_files = generate_nise_data_for_period(cluster_id, period, temp_dir)
                    
                    for file_type in combined_files:
                        combined_files[file_type].extend(period_files[file_type])
                
                print(f"    ✅ Generated data for all periods")
                
                # Merge CSV files
                print(f"\n  [Step 2/5] Merging CSV files...")
                merged_dir = os.path.join(temp_dir, 'merged')
                os.makedirs(merged_dir, exist_ok=True)
                
                merged_pod = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_pod_usage.csv")
                merged_ros = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_ros_usage.csv")
                merged_node = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_node_label.csv")
                merged_ns = os.path.join(merged_dir, f"January-2026-{cluster_id}-ocp_namespace_label.csv")
                
                merge_csv_files(combined_files["pod"], merged_pod)
                merge_csv_files(combined_files["ros"], merged_ros)
                merge_csv_files(combined_files["node_label"], merged_node)
                merge_csv_files(combined_files["namespace_label"], merged_ns)
                
                print(f"    ✅ Merged {len(combined_files['pod'])} pod files into 1")
                
                # Register source
                print(f"\n  [Step 3/5] Registering source...")
                source_id = register_source_via_gateway(cluster_config, jwt_token, cluster_id, config["display_name"])
                print(f"    ✅ Source registered: {source_id}")
                
                # Create upload package
                print(f"\n  [Step 4/5] Creating upload package...")
                package_path = create_upload_package_from_files(
                    pod_usage_files=[merged_pod],
                    ros_usage_files=[merged_ros],
                    cluster_id=cluster_id,
                    start_date=datetime(2026, 1, 1),
                    end_date=datetime(2026, 2, 5),
                    node_label_files=[merged_node],
                    namespace_label_files=[merged_ns],
                )
                print(f"    ✅ Package created: {os.path.getsize(package_path)} bytes")
                
                # Upload
                print(f"\n  [Step 5/5] Uploading data...")
                upload_response = upload_data_via_ingress(cluster_config, package_path, jwt_token)
                print(f"    ✅ Data uploaded: {upload_response.get('request_id', 'N/A')}")
                
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
            print(f"    ✅ Summary tables populated (schema: {schema_name})")
    
    print(f"\n{'=' * 70}")
    print("✅ TRULY VARIED DEMO DATA GENERATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"\nProcessed {len(results)} clusters with realistic cost variations!")
    print("\n🎯 Cost patterns created:")
    print("  • Production: Weekday baseline → Weekend 1.8x → Promo 2.5x")
    print("  • Development: Weekend minimal → Workday 1.0x → Build 2.75x")
    print("  • Staging: Normal baseline → Load test 2.85x")


if __name__ == "__main__":
    main()
