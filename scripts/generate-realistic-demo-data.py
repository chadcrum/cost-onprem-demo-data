#!/usr/bin/env python3
"""
Generate realistic demo data with varied workload patterns.
Creates e-commerce, dev/CI-CD, and staging scenarios with realistic cost trends.
"""
import os
import sys
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value, run_oc_command
from helpers import create_upload_package_from_files, exec_in_pod
from helpers import wait_for_provider, wait_for_summary_tables
import requests
import base64
import json

# Demo clusters with realistic workload configs
DEMO_CLUSTERS = [
    {
        "cluster_id": "demo-prod-cluster",
        "display_name": "Production E-commerce",
        "static_file": "static-prod-ecommerce.yml",
        "namespaces": {
            "NAMESPACE_1": "production-web",
            "NAMESPACE_2": "production-api",
            "NAMESPACE_3": "production-data",
        },
        "description": "E-commerce platform with weekend spikes and promo events",
    },
    {
        "cluster_id": "demo-dev-cluster",
        "display_name": "Development & CI/CD",
        "static_file": "static-dev-devops.yml",
        "namespaces": {
            "NAMESPACE_1": "development",
            "NAMESPACE_2": "ci-cd",
        },
        "description": "Dev environment with working hours and build spikes",
    },
    {
        "cluster_id": "demo-staging-cluster",
        "display_name": "Staging & Load Testing",
        "static_file": "static-staging-loadtest.yml",
        "namespaces": {
            "NAMESPACE_1": "staging-app",
        },
        "description": "Staging with deployment waves and load test spikes",
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


def generate_realistic_nise_data(
    cluster_id: str,
    start_date: datetime,
    end_date: datetime,
    static_file_path: str,
    namespaces: dict,
    output_dir: str,
) -> dict:
    """Generate NISE data using custom static report file with varied patterns."""
    
    # Read and customize static file
    with open(static_file_path, 'r') as f:
        yaml_content = f.read()
    
    # Replace placeholders
    yaml_content = yaml_content.replace('START_DATE', start_date.strftime('%Y-%m-%d'))
    yaml_content = yaml_content.replace('END_DATE', end_date.strftime('%Y-%m-%d'))
    yaml_content = yaml_content.replace('CLUSTER_ID', cluster_id)
    
    for placeholder, namespace in namespaces.items():
        yaml_content = yaml_content.replace(placeholder, namespace)
    
    # Write customized YAML
    yaml_path = os.path.join(output_dir, 'static_report.yml')
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)
    
    # Create output directory
    nise_output = os.path.join(output_dir, 'nise_output')
    os.makedirs(nise_output, exist_ok=True)
    
    # Run NISE
    cmd = [
        'nise', 'report', 'ocp',
        '--static-report-file', yaml_path,
        '--ocp-cluster-id', cluster_id,
        '--ros-ocp-info',  # Include ROS data
        '-w',  # Write monthly files
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=nise_output,
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"NISE failed: {result.stderr}")
    
    # Categorize files
    files = {
        "pod_usage_files": [],
        "ros_usage_files": [],
        "node_label_files": [],
        "namespace_label_files": [],
        "all_files": [],
    }
    
    for root, _, filenames in os.walk(nise_output):
        for f in filenames:
            if f.endswith('.csv'):
                full_path = os.path.join(root, f)
                files["all_files"].append(full_path)
                
                if 'pod_usage' in f:
                    files["pod_usage_files"].append(full_path)
                elif 'ros_usage' in f:
                    files["ros_usage_files"].append(full_path)
                elif 'node_label' in f:
                    files["node_label_files"].append(full_path)
                elif 'namespace_label' in f:
                    files["namespace_label_files"].append(full_path)
    
    if not files["ros_usage_files"]:
        files["ros_usage_files"] = files["pod_usage_files"]
    
    return files


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


def main():
    print("=" * 70)
    print("REALISTIC DEMO DATA GENERATION")
    print("=" * 70)
    print("\n✨ Creating varied workload patterns:")
    print("  • Production: E-commerce with weekend spikes + promo event")
    print("  • Development: Working hours + CI/CD build spikes")
    print("  • Staging: Deployment waves + load testing spikes")
    print("=" * 70)
    
    cluster_config = get_cluster_config()
    script_dir = Path(__file__).parent
    
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
                # Generate NISE data with custom static file
                print(f"\n  [Step 1/4] Generating NISE data with varied patterns...")
                static_file = script_dir / cluster["static_file"]
                
                files = generate_realistic_nise_data(
                    cluster_id=cluster["cluster_id"],
                    start_date=start_date,
                    end_date=end_date,
                    static_file_path=str(static_file),
                    namespaces=cluster["namespaces"],
                    output_dir=temp_dir,
                )
                
                print(f"    ✅ Generated {len(files['all_files'])} CSV files")
                print(f"      - Pod usage: {len(files['pod_usage_files'])}")
                print(f"      - ROS usage: {len(files['ros_usage_files'])}")
                
            except Exception as e:
                print(f"    ❌ NISE generation failed: {e}")
                import traceback
                traceback.print_exc()
                continue
            
            # Register source
            print(f"\n  [Step 2/4] Registering source via gateway...")
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
                    pod_usage_files=[str(f) for f in files["pod_usage_files"]],
                    ros_usage_files=[str(f) for f in files["ros_usage_files"]],
                    cluster_id=cluster["cluster_id"],
                    start_date=start_date,
                    end_date=end_date,
                    node_label_files=[str(f) for f in files["node_label_files"]] if files["node_label_files"] else None,
                    namespace_label_files=[str(f) for f in files["namespace_label_files"]] if files["namespace_label_files"] else None,
                )
                print(f"    ✅ Package created: {os.path.getsize(package_path)} bytes")
            except Exception as e:
                print(f"    ❌ Package creation failed: {e}")
                continue
            
            # Upload
            print(f"\n  [Step 4/4] Uploading data via ingress...")
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
    
    print("\n🎯 Data patterns created:")
    print("  • Production: Weekend traffic spikes, Jan 22-24 promo event")
    print("  • Development: Working hours, CI/CD build spikes")
    print("  • Staging: Weekly deployment + load test cycles")
    print("\nRefresh the UI to see realistic cost trends!")


if __name__ == "__main__":
    main()
