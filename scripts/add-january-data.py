#!/usr/bin/env python3
"""
Add January 2026 data to existing demo sources.
Generates NISE data for Jan 1-31 and uploads to existing clusters.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers import (
    generate_nise_data,
)
from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value, run_oc_command
from helpers import create_upload_package_from_files, exec_in_pod
import requests
import base64
import json

# Demo clusters (matching existing sources)
DEMO_CLUSTERS = [
    {
        "cluster_id": "demo-prod-cluster",
        "display_name": "Production Cluster",
        "source_id": "1",
        "namespaces": ["production", "ai-ml", "monitoring"],
    },
    {
        "cluster_id": "demo-dev-cluster",
        "display_name": "Development Cluster",
        "source_id": "2",
        "namespaces": ["development", "ml-experimentation", "staging"],
    },
    {
        "cluster_id": "demo-staging-cluster",
        "display_name": "Staging Cluster",
        "source_id": "3",
        "namespaces": ["staging", "mlops-pipeline", "qa"],
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


def main():
    print("=" * 70)
    print("ADDING JANUARY 2026 DATA TO EXISTING SOURCES")
    print("=" * 70)
    
    cluster_config = get_cluster_config()
    print(f"\nCluster Config:")
    print(f"  Namespace: {cluster_config.namespace}")
    print(f"  Release: {cluster_config.helm_release_name}")
    
    # Get JWT token
    print("\n[1/2] Obtaining JWT token...")
    jwt_token = get_jwt_token(cluster_config)
    print("  ✅ JWT token obtained")
    
    # Date range: January 1-31, 2026
    start_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 1, 31)
    
    print(f"\n[2/2] Generating and uploading January data")
    print(f"  Date range: {start_date.date()} to {end_date.date()} (31 days)")
    
    results = []
    
    for idx, cluster in enumerate(DEMO_CLUSTERS, 1):
        print(f"\n{'=' * 70}")
        print(f"CLUSTER {idx}/3: {cluster['display_name']}")
        print(f"{'=' * 70}")
        print(f"  Cluster ID: {cluster['cluster_id']}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Generate NISE data for January
            print(f"\n  [Step 1/3] Generating NISE data for January...")
            try:
                files = generate_nise_data(
                    cluster_id=cluster["cluster_id"],
                    start_date=start_date,
                    end_date=end_date,
                    output_dir=temp_dir,
                    include_ros=True,
                )
                print(f"    ✅ Generated {len(files['all_files'])} CSV files")
                print(f"      - Pod usage: {len(files['pod_usage_files'])}")
                print(f"      - ROS usage: {len(files['ros_usage_files'])}")
            except Exception as e:
                print(f"    ❌ NISE generation failed: {e}")
                continue
            
            # Create upload package
            print(f"\n  [Step 2/3] Creating upload package...")
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
            print(f"\n  [Step 3/3] Uploading data via ingress...")
            try:
                upload_response = upload_data_via_ingress(
                    cluster_config, package_path, jwt_token
                )
                print(f"    ✅ Data uploaded: {upload_response.get('request_id', 'N/A')}")
                results.append({
                    "cluster_id": cluster["cluster_id"],
                    "status": "uploaded",
                })
            except Exception as e:
                print(f"    ❌ Upload failed: {e}")
                continue
    
    print(f"\n{'=' * 70}")
    print("JANUARY DATA UPLOAD COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n✅ Uploaded January data for {len(results)} cluster(s):")
    for result in results:
        print(f"  - {result['cluster_id']}: {result['status']}")
    
    print("\nProcessing will take 5-10 minutes.")
    print("Monitor with: oc logs -n cost-onprem -l app.kubernetes.io/component=listener --tail=50 -f")


if __name__ == "__main__":
    main()
