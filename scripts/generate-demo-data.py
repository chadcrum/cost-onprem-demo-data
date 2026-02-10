#!/usr/bin/env python3
"""
Generate demo data for 3 clusters with ML/MLOps workloads.

This script generates NISE data, registers sources, and uploads data
for demo-prod-cluster, demo-dev-cluster, and demo-staging-cluster.
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers import (
    generate_nise_data,
    register_source,
    wait_for_provider,
    wait_for_summary_tables,
)
from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value, run_oc_command
from helpers import create_upload_package_from_files, exec_in_pod
import requests
import base64
import json

# Demo cluster configurations
DEMO_CLUSTERS = [
    {
        "cluster_id": "demo-prod-cluster",
        "display_name": "Production Cluster",
        "days_history": 30,
        "namespaces": ["production", "ai-ml", "monitoring"],
    },
    {
        "cluster_id": "demo-dev-cluster",
        "display_name": "Development Cluster",
        "days_history": 15,
        "namespaces": ["development", "ml-experimentation", "staging"],
    },
    {
        "cluster_id": "demo-staging-cluster",
        "display_name": "Staging Cluster",
        "days_history": 7,
        "namespaces": ["staging", "mlops-pipeline", "qa"],
    },
]

# Default org_id (from Keycloak test user)
ORG_ID = "org1234567"
BUCKET = "koku-bucket"


def get_cluster_config():
    """Get cluster configuration from environment."""
    return ClusterConfig(
        namespace=os.environ.get("NAMESPACE", "cost-onprem"),
        helm_release_name=os.environ.get("HELM_RELEASE_NAME", "cost-onprem"),
        keycloak_namespace=os.environ.get("KEYCLOAK_NAMESPACE", "keycloak"),
    )


def get_rh_identity_header(org_id: str) -> str:
    """Generate X-Rh-Identity header."""
    identity = {
        "identity": {
            "org_id": org_id,
            "account_number": "7890123",
            "user": {"username": "test", "email": "test@test.com"},
            "type": "User",
        }
    }
    return base64.b64encode(json.dumps(identity).encode()).decode()


def get_api_urls(cluster_config: ClusterConfig):
    """Get Koku API URLs via gateway."""
    gateway_url = get_route_url(cluster_config.namespace, f"{cluster_config.helm_release_name}-api")
    if not gateway_url:
        raise RuntimeError("Gateway route not found")
    
    # Sources API is accessible via gateway at /api/cost-management/v1/sources/
    api_base = f"{gateway_url}/api/cost-management/v1"
    return api_base, api_base  # Same URL for reads and writes via gateway


def get_ingress_pod(cluster_config: ClusterConfig) -> str:
    """Get ingress pod name."""
    result = run_oc_command(
        [
            "get",
            "pods",
            "-n",
            cluster_config.namespace,
            "-l",
            "app.kubernetes.io/component=ingress",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ],
        check=False,
    )
    return result.stdout.strip()


def get_jwt_token(cluster_config: ClusterConfig) -> str:
    """Get JWT token from Keycloak."""
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

    response = requests.post(
        f"{keycloak_url}/realms/kubernetes/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "cost-management-operator",
            "client_secret": client_secret,
        },
        verify=False,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def upload_data_via_ingress(
    cluster_config: ClusterConfig, tar_path: str, jwt_token: str
) -> dict:
    """Upload data via ingress API."""
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
    """Generate demo data for all clusters."""
    print("=" * 70)
    print("DEMO DATA GENERATION")
    print("=" * 70)
    
    cluster_config = get_cluster_config()
    print(f"\nCluster Config:")
    print(f"  Namespace: {cluster_config.namespace}")
    print(f"  Release: {cluster_config.helm_release_name}")
    
    # Get JWT token once
    print("\n[1/4] Obtaining JWT token...")
    jwt_token = get_jwt_token(cluster_config)
    print("  ✅ JWT token obtained")
    
    # Get ingress pod
    ingress_pod = get_ingress_pod(cluster_config)
    print(f"  ✅ Ingress pod: {ingress_pod}")
    
    # Get API URLs
    api_reads_url, api_writes_url = get_api_urls(cluster_config)
    rh_identity = get_rh_identity_header(ORG_ID)
    
    # Process each cluster
    today = datetime.now()
    results = []
    
    for idx, cluster in enumerate(DEMO_CLUSTERS, 1):
        print(f"\n{'=' * 70}")
        print(f"CLUSTER {idx}/3: {cluster['display_name']}")
        print(f"{'=' * 70}")
        print(f"  Cluster ID: {cluster['cluster_id']}")
        print(f"  Days History: {cluster['days_history']}")
        print(f"  Namespaces: {', '.join(cluster['namespaces'])}")
        
        # Calculate dates
        end_date = today
        start_date = today - timedelta(days=cluster["days_history"])
        
        print(f"\n  [Step 1/4] Generating NISE data...")
        print(f"    Date range: {start_date.date()} to {end_date.date()}")
        
        # Create temp directory for this cluster
        with tempfile.TemporaryDirectory() as temp_dir:
            # Generate NISE data
            try:
                files = generate_nise_data(
                    cluster_id=cluster["cluster_id"],
                    start_date=start_date,
                    end_date=end_date,
                    output_dir=temp_dir,
                    include_ros=True,  # Critical: --ros-ocp-info flag
                )
                print(f"    ✅ Generated {len(files['all_files'])} CSV files")
                print(f"      - Pod usage: {len(files['pod_usage_files'])}")
                print(f"      - ROS usage: {len(files['ros_usage_files'])}")
            except Exception as e:
                print(f"    ❌ NISE generation failed: {e}")
                continue
            
            # Register source via gateway with JWT
            print(f"\n  [Step 2/4] Registering source via gateway...")
            try:
                # Get source type ID
                response = requests.get(
                    f"{api_reads_url}/source_types",
                    headers={"Authorization": f"Bearer {jwt_token}"},
                    verify=False,
                    timeout=30,
                )
                response.raise_for_status()
                source_types = response.json().get("data", [])
                source_type_id = None
                for st in source_types:
                    if st.get("name") == "openshift":
                        source_type_id = st.get("id")
                        break
                
                if not source_type_id:
                    raise RuntimeError("OpenShift source type not found")
                
                # Create source
                source_payload = {
                    "name": cluster["display_name"],
                    "source_type_id": source_type_id,
                    "source_ref": cluster["cluster_id"],
                }
                
                response = requests.post(
                    f"{api_writes_url}/sources",
                    json=source_payload,
                    headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
                    verify=False,
                    timeout=120,
                )
                response.raise_for_status()
                source_data = response.json()
                source_id = source_data.get("id")
                
                if not source_id:
                    raise RuntimeError(f"No source ID in response: {source_data}")
                
                print(f"    ✅ Source registered: {source_id}")
                
                # Create application (optional but recommended)
                app_type_response = requests.get(
                    f"{api_reads_url}/application_types",
                    headers={"Authorization": f"Bearer {jwt_token}"},
                    verify=False,
                    timeout=30,
                )
                if app_type_response.status_code == 200:
                    app_types = app_type_response.json().get("data", [])
                    app_type_id = None
                    for at in app_types:
                        if at.get("name") == "/insights/platform/cost-management":
                            app_type_id = at.get("id")
                            break
                    
                    if app_type_id:
                        app_payload = {
                            "source_id": source_id,
                            "application_type_id": app_type_id,
                            "extra": {"bucket": BUCKET, "cluster_id": cluster["cluster_id"]},
                        }
                        requests.post(
                            f"{api_writes_url}/applications",
                            json=app_payload,
                            headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
                            verify=False,
                            timeout=30,
                        )
                
                source_reg = type('obj', (object,), {
                    'source_id': source_id,
                    'source_name': cluster["display_name"],
                    'cluster_id': cluster["cluster_id"],
                    'org_id': ORG_ID,
                })()
                
            except Exception as e:
                print(f"    ❌ Source registration failed: {e}")
                import traceback
                traceback.print_exc()
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
            
            # Upload data
            print(f"\n  [Step 4/4] Uploading data via ingress...")
            try:
                upload_response = upload_data_via_ingress(
                    cluster_config, package_path, jwt_token
                )
                print(f"    ✅ Data uploaded: {upload_response.get('request_id', 'N/A')}")
            except Exception as e:
                print(f"    ❌ Upload failed: {e}")
                continue
            
            results.append({
                "cluster_id": cluster["cluster_id"],
                "source_id": source_reg.source_id,
                "status": "uploaded",
            })
    
    # Wait for processing
    print(f"\n{'=' * 70}")
    print("WAITING FOR DATA PROCESSING")
    print(f"{'=' * 70}")
    
    db_pod = run_oc_command(
        [
            "get",
            "pods",
            "-n",
            cluster_config.namespace,
            "-l",
            "app.kubernetes.io/component=database",
            "-o",
            "jsonpath={.items[0].metadata.name}",
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
        schema = wait_for_summary_tables(
            cluster_config.namespace, db_pod, cluster_id, timeout=600
        )
        if schema:
            print(f"    ✅ Summary tables populated (schema: {schema})")
        else:
            print(f"    ⚠️  Summary tables not populated (may take longer)")
    
    print(f"\n{'=' * 70}")
    print("DEMO DATA GENERATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n✅ Processed {len(results)} clusters:")
    for result in results:
        print(f"  - {result['cluster_id']}: {result['status']}")


if __name__ == "__main__":
    main()
