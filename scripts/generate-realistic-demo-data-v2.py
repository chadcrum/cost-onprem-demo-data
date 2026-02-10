#!/usr/bin/env python3
"""
Generate realistic demo data with varied daily patterns using Python.
Creates 3 clusters with distinct workload profiles and realistic cost trends.
"""
import os
import sys
import subprocess
import tempfile
import csv
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value, run_oc_command
from helpers import create_upload_package_from_files
from helpers import wait_for_provider, wait_for_summary_tables
import requests

# Demo clusters with realistic scenarios
DEMO_CLUSTERS = [
    {
        "cluster_id": "demo-prod-cluster",
        "display_name": "Production E-commerce",
        "description": "E-commerce platform with weekend spikes and promo events",
        "pattern": "ecommerce",
    },
    {
        "cluster_id": "demo-dev-cluster",
        "display_name": "Development & CI/CD",
        "description": "Dev environment with working hours and build spikes",
        "pattern": "devops",
    },
    {
        "cluster_id": "demo-staging-cluster",
        "display_name": "Staging & Load Testing",
        "description": "Staging with deployment waves and load test spikes",
        "pattern": "staging",
    },
]

ORG_ID = "org1234567"
BUCKET = "koku-bucket"


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


def get_usage_multiplier(pattern: str, date: datetime) -> float:
    """Get CPU/memory usage multiplier for a given pattern and date."""
    day = date.day
    weekday = date.weekday()  # 0=Mon, 6=Sun
    
    if pattern == "ecommerce":
        # Weekend spikes + major promo Jan 22-24
        if 22 <= day <= 24:  # Promo event
            return 2.5 + random.uniform(-0.2, 0.3)
        elif weekday >= 5:  # Weekend
            return 1.8 + random.uniform(-0.15, 0.25)
        elif weekday == 4:  # Friday buildup
            return 1.4 + random.uniform(-0.1, 0.1)
        elif weekday == 0:  # Monday recovery
            return 0.9 + random.uniform(-0.05, 0.1)
        else:  # Regular weekday
            return 1.0 + random.uniform(-0.1, 0.15)
    
    elif pattern == "devops":
        # Working hours + build spikes
        if weekday >= 5:  # Weekend - minimal
            return 0.15 + random.uniform(-0.05, 0.05)
        elif day in [6, 13, 20, 27]:  # Build/release days
            return 2.2 + random.uniform(-0.2, 0.4)
        elif day == 3:  # Holiday (Jan 3rd)
            return 0.1
        else:  # Regular workday
            return 0.8 + random.uniform(-0.15, 0.25)
    
    elif pattern == "staging":
        # Weekly deploy + load test cycle
        if day in [6, 13, 20, 27]:  # Deploy + load test days
            return 2.0 + random.uniform(-0.15, 0.3)
        elif 1 <= day <= 5:  # Early month low
            return 0.4 + random.uniform(-0.1, 0.1)
        else:  # Testing days
            return 0.7 + random.uniform(-0.1, 0.2)
    
    return 1.0


def generate_varied_nise_data_programmatically(
    cluster_id: str,
    pattern: str,
    start_date: datetime,
    end_date: datetime,
    output_dir: str,
) -> Dict[str, List[str]]:
    """Generate NISE data and then vary it programmatically for realism."""
    
    # First, generate baseline NISE data using default config
    print(f"    Generating baseline NISE data...")
    
    base_static_yaml = f"""---
generators:
  - OCPGenerator:
      start_date: {start_date.strftime('%Y-%m-%d')}
      end_date: {end_date.strftime('%Y-%m-%d')}
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
                    full_period: 1.5
                  mem_usage_gig:
                    full_period: 3.0
                  labels: app:demo|env:prod
                - pod:
                  pod_name: app-2
                  cpu_request: 1.5
                  mem_request_gig: 3.0
                  cpu_limit: 3.0
                  mem_limit_gig: 6.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: 1.0
                  mem_usage_gig:
                    full_period: 2.0
                  labels: app:demo|env:prod
                - pod:
                  pod_name: db-1
                  cpu_request: 3.0
                  mem_request_gig: 8.0
                  cpu_limit: 6.0
                  mem_limit_gig: 16.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: 2.5
                  mem_usage_gig:
                    full_period: 6.0
                  labels: app:database|tier:data
"""
    
    # Write static YAML
    yaml_path = os.path.join(output_dir, 'static_report.yml')
    with open(yaml_path, 'w') as f:
        f.write(base_static_yaml)
    
    # Generate with NISE
    nise_output = os.path.join(output_dir, 'nise_output')
    os.makedirs(nise_output, exist_ok=True)
    
    cmd = [
        'nise', 'report', 'ocp',
        '--static-report-file', yaml_path,
        '--ocp-cluster-id', cluster_id,
        '--ros-ocp-info',
        '-w',
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=nise_output)
    if result.returncode != 0:
        raise RuntimeError(f"NISE failed: {result.stderr}")
    
    print(f"    Applying {pattern} usage patterns...")
    
    # Find generated CSV files and vary them
    varied_output = os.path.join(output_dir, 'varied_output')
    os.makedirs(varied_output, exist_ok=True)
    
    pod_files = []
    ros_files = []
    node_label_files = []
    namespace_label_files = []
    
    for root, _, filenames in os.walk(nise_output):
        for filename in filenames:
            if not filename.endswith('.csv'):
                continue
            
            input_path = os.path.join(root, filename)
            output_path = os.path.join(varied_output, filename)
            
            # Vary usage data for pod_usage and ros_usage files
            if 'pod_usage' in filename or 'ros_usage' in filename:
                vary_usage_csv(input_path, output_path, pattern, start_date, end_date)
                
                if 'pod_usage' in filename:
                    pod_files.append(output_path)
                elif 'ros_usage' in filename:
                    ros_files.append(output_path)
            else:
                # Copy label files as-is
                import shutil
                shutil.copy(input_path, output_path)
                
                if 'node_label' in filename:
                    node_label_files.append(output_path)
                elif 'namespace_label' in filename:
                    namespace_label_files.append(output_path)
    
    return {
        "pod_usage_files": pod_files,
        "ros_usage_files": ros_files if ros_files else pod_files,
        "node_label_files": node_label_files,
        "namespace_label_files": namespace_label_files,
        "all_files": pod_files + ros_files + node_label_files + namespace_label_files,
    }


def vary_usage_csv(input_path: str, output_path: str, pattern: str, start_date: datetime, end_date: datetime):
    """Vary CPU and memory usage in CSV based on pattern and date."""
    
    with open(input_path, 'r') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        
        rows = []
        for row in reader:
            # Parse interval start
            interval_start_str = row.get('interval_start', '')
            try:
                interval_start = datetime.fromisoformat(interval_start_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                rows.append(row)  # Keep row as-is if can't parse
                continue
            
            # Get multiplier for this date
            multiplier = get_usage_multiplier(pattern, interval_start)
            
            # Apply multiplier to usage fields
            for field in ['pod_usage_cpu_core_seconds', 'pod_request_cpu_core_seconds', 
                          'pod_limit_cpu_core_seconds', 'pod_usage_memory_byte_seconds',
                          'pod_request_memory_byte_seconds', 'pod_limit_memory_byte_seconds',
                          'node_capacity_cpu_core_seconds', 'node_capacity_memory_byte_seconds']:
                if field in row and row[field]:
                    try:
                        original_value = float(row[field])
                        row[field] = str(original_value * multiplier)
                    except (ValueError, TypeError):
                        pass  # Skip if not a valid number
            
            rows.append(row)
    
    # Write varied data
    with open(output_path, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def register_source_via_gateway(
    cluster_config: ClusterConfig,
    jwt_token: str,
    cluster_id: str,
    display_name: str,
) -> str:
    """Register source via gateway API."""
    gateway_url = get_route_url(cluster_config.namespace, f"{cluster_config.helm_release_name}-api")
    api_base = f"{gateway_url}/api/cost-management/v1"
    
    # Get source type ID
    resp = requests.get(
        f"{api_base}/source_types",
        headers={"Authorization": f"Bearer {jwt_token}"},
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    source_types = resp.json().get("data", [])
    source_type_id = next((st["id"] for st in source_types if st.get("name") == "openshift"), None)
    
    if not source_type_id:
        raise RuntimeError("OpenShift source type not found")
    
    # Create source
    source_payload = {
        "name": display_name,
        "source_type_id": source_type_id,
        "source_ref": cluster_id,
    }
    
    resp = requests.post(
        f"{api_base}/sources",
        json=source_payload,
        headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
        verify=False,
        timeout=120,
    )
    resp.raise_for_status()
    source_data = resp.json()
    source_id = source_data.get("id")
    
    if not source_id:
        raise RuntimeError(f"No source ID in response: {source_data}")
    
    # Create application
    app_resp = requests.get(
        f"{api_base}/application_types",
        headers={"Authorization": f"Bearer {jwt_token}"},
        verify=False,
        timeout=30,
    )
    
    if app_resp.status_code == 200:
        app_types = app_resp.json().get("data", [])
        app_type_id = next(
            (at["id"] for at in app_types if at.get("name") == "/insights/platform/cost-management"),
            None
        )
        
        if app_type_id:
            app_payload = {
                "source_id": source_id,
                "application_type_id": app_type_id,
                "extra": {"bucket": BUCKET, "cluster_id": cluster_id},
            }
            requests.post(
                f"{api_base}/applications",
                json=app_payload,
                headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
                verify=False,
                timeout=30,
            )
    
    return source_id


def upload_data_via_ingress(
    cluster_config: ClusterConfig, tar_path: str, jwt_token: str
) -> dict:
    gateway_url = get_route_url(cluster_config.namespace, f"{cluster_config.helm_release_name}-api")
    if not gateway_url:
        raise RuntimeError("Gateway route not found")
    upload_url = f"{gateway_url}/api/ingress/v1/upload"
    with open(tar_path, "rb") as f:
        files = {"file": ("cost-mgmt.tar.gz", f, "application/vnd.redhat.hccm.filename+tgz")}
        headers = {"Authorization": f"Bearer {jwt_token}"}
        response = requests.post(upload_url, files=files, headers=headers, verify=False, timeout=120)
        response.raise_for_status()
        return response.json()


def main():
    print("=" * 70)
    print("REALISTIC DEMO DATA GENERATION (Programmatic Variation)")
    print("=" * 70)
    print("\n✨ Creating varied workload patterns:")
    print("  • Production: E-commerce with weekend spikes + promo event")
    print("  • Development: Working hours + CI/CD build spikes")
    print("  • Staging: Deployment waves + load testing spikes")
    print("=" * 70)
    
    cluster_config = get_cluster_config()
    
    print(f"\nCluster Config:")
    print(f"  Namespace: {cluster_config.namespace}")
    print(f"  Release: {cluster_config.helm_release_name}")
    
    # Get JWT token
    print("\n[1/2] Obtaining JWT token...")
    jwt_token = get_jwt_token(cluster_config)
    print("  ✅ JWT token obtained")
    
    # Date range: January 1 - February 5, 2026
    start_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 2, 5)
    
    print(f"\n[2/2] Generating realistic data")
    print(f"  Date range: {start_date.date()} to {end_date.date()} (36 days)")
    
    results = []
    
    for idx, cluster in enumerate(DEMO_CLUSTERS, 1):
        print(f"\n{'=' * 70}")
        print(f"CLUSTER {idx}/3: {cluster['display_name']}")
        print(f"{'=' * 70}")
        print(f"  Cluster ID: {cluster['cluster_id']}")
        print(f"  Description: {cluster['description']}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                files = generate_varied_nise_data_programmatically(
                    cluster_id=cluster["cluster_id"],
                    pattern=cluster["pattern"],
                    start_date=start_date,
                    end_date=end_date,
                    output_dir=temp_dir,
                )
                
                print(f"    ✅ Generated {len(files['all_files'])} CSV files")
                
            except Exception as e:
                print(f"    ❌ Data generation failed: {e}")
                import traceback
                traceback.print_exc()
                continue
            
            # Register source
            print(f"\n  [Step 2/4] Registering source...")
            try:
                source_id = register_source_via_gateway(
                    cluster_config,
                    jwt_token,
                    cluster["cluster_id"],
                    cluster["display_name"],
                )
                print(f"    ✅ Source registered: {source_id}")
            except Exception as e:
                print(f"    ❌ Source registration failed: {e}")
                continue
            
            # Create upload package
            print(f"\n  [Step 3/4] Creating upload package...")
            try:
                package_path = create_upload_package_from_files(
                    pod_usage_files=files["pod_usage_files"],
                    ros_usage_files=files["ros_usage_files"],
                    cluster_id=cluster["cluster_id"],
                    start_date=start_date,
                    end_date=end_date,
                    node_label_files=files["node_label_files"] if files["node_label_files"] else None,
                    namespace_label_files=files["namespace_label_files"] if files["namespace_label_files"] else None,
                )
                print(f"    ✅ Package created: {os.path.getsize(package_path)} bytes")
            except Exception as e:
                print(f"    ❌ Package creation failed: {e}")
                import traceback
                traceback.print_exc()
                continue
            
            # Upload
            print(f"\n  [Step 4/4] Uploading data...")
            try:
                upload_response = upload_data_via_ingress(
                    cluster_config, package_path, jwt_token
                )
                print(f"    ✅ Data uploaded: {upload_response.get('request_id', 'N/A')}")
                results.append({
                    "cluster_id": cluster["cluster_id"],
                    "source_id": source_id,
                    "status": "uploaded",
                })
            except Exception as e:
                print(f"    ❌ Upload failed: {e}")
                continue
    
    # Wait for processing
    print(f"\n{'=' * 70}")
    print("WAITING FOR DATA PROCESSING")
    print(f"{'=' * 70}")
    
    db_pod = run_oc_command(
        [
            "get", "pods", "-n", cluster_config.namespace,
            "-l", "app.kubernetes.io/component=database",
            "-o", "jsonpath={.items[0].metadata.name}",
        ],
        check=False,
    ).stdout.strip()
    
    for result in results:
        cluster_id = result["cluster_id"]
        print(f"\n  Processing {cluster_id}...")
        
        # Wait for provider
        print(f"    Waiting for provider...")
        if wait_for_provider(cluster_config.namespace, db_pod, cluster_id, timeout=300):
            print(f"    ✅ Provider created")
        else:
            print(f"    ⚠️  Provider not created (may take longer)")
        
        # Wait for summary tables
        print(f"    Waiting for summary tables...")
        schema_name = wait_for_summary_tables(
            cluster_config.namespace, db_pod, cluster_id, timeout=600
        )
        if schema_name:
            print(f"    ✅ Summary tables populated (schema: {schema_name})")
        else:
            print(f"    ⚠️  Summary tables not populated (may take longer)")
    
    print(f"\n{'=' * 70}")
    print("✅ REALISTIC DEMO DATA GENERATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"\nProcessed {len(results)} clusters with varied patterns:")
    for result in results:
        print(f"  - {result['cluster_id']}: {result['status']}")
    
    print("\n🎯 Realistic cost patterns created!")
    print("\nCosts will restart MASU to recalculate...")


if __name__ == "__main__":
    main()
