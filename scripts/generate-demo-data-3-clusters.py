#!/usr/bin/env python3
"""
Generate demo data for 3 clusters with varied workload profiles.

This script generates realistic demo data for:
1. demo-prod-cluster - Production web application
2. demo-ml-cluster - ML/MLOps workloads  
3. demo-dev-cluster - Development environment

Uses existing test infrastructure from tests/e2e_helpers.py
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers import (
    generate_nise_data,
    register_source,
    wait_for_provider,
    wait_for_summary_tables,
    NISEConfig,
)
from helpers import (
    create_upload_package_from_files,
    execute_db_query,
    exec_in_pod,
    get_pod_by_label,
    get_route_url,
    get_secret_value,
    run_oc_command,
)
from helpers.config import (
    ClusterConfig,
    KeycloakConfig,
    obtain_jwt_token,
)
import requests
import base64
import json

# Configuration
NAMESPACE = os.environ.get("NAMESPACE", "cost-onprem")
HELM_RELEASE_NAME = os.environ.get("HELM_RELEASE_NAME", "cost-onprem")
KEYCLOAK_NAMESPACE = os.environ.get("KEYCLOAK_NAMESPACE", "keycloak")
ORG_ID = os.environ.get("ORG_ID", "org1234567")

# Cluster configurations
CLUSTER_CONFIGS = [
    {
        "cluster_id": "demo-prod-cluster",
        "display_name": "Production Cluster",
        "namespaces": ["prod-web", "prod-api", "prod-db"],
        "days": 7,
        "description": "Production web application with high utilization",
    },
    {
        "cluster_id": "demo-ml-cluster",
        "display_name": "ML/MLOps Cluster",
        "namespaces": ["ml-dev", "ml-training"],
        "days": 7,
        "description": "ML/MLOps workloads with bursty patterns",
    },
    {
        "cluster_id": "demo-dev-cluster",
        "display_name": "Development Cluster",
        "namespaces": ["dev-team-a", "dev-team-b", "ci-cd"],
        "days": 7,
        "description": "Development environment with low-medium utilization",
    },
]


def get_cluster_config() -> ClusterConfig:
    """Get cluster configuration."""
    return ClusterConfig(
        namespace=NAMESPACE,
        helm_release_name=HELM_RELEASE_NAME,
        keycloak_namespace=KEYCLOAK_NAMESPACE,
    )


def get_keycloak_config() -> KeycloakConfig:
    """Get Keycloak configuration."""
    keycloak_url = get_route_url(KEYCLOAK_NAMESPACE, "keycloak")
    if not keycloak_url:
        raise RuntimeError(f"Keycloak route not found in namespace {KEYCLOAK_NAMESPACE}")

    client_id = "cost-management-operator"
    secret_name = "keycloak-client-secret-cost-management-operator"
    client_secret = get_secret_value(KEYCLOAK_NAMESPACE, secret_name, "CLIENT_SECRET")

    if not client_secret:
        raise RuntimeError(f"Client secret not found: {secret_name}")

    return KeycloakConfig(
        url=keycloak_url,
        client_id=client_id,
        client_secret=client_secret,
    )


def create_rh_identity_header(org_id: str) -> str:
    """Create X-Rh-Identity header."""
    identity = {
        "identity": {
            "org_id": org_id,
            "account_number": "7890123",
            "user": {
                "username": "test",
                "email": "test@test.com",
            },
            "type": "User",
        }
    }
    return base64.b64encode(json.dumps(identity).encode()).decode()


def get_api_urls(cluster_config: ClusterConfig) -> tuple[str, str]:
    """Get Koku API reads and writes URLs."""
    reads_url = (
        f"http://{cluster_config.helm_release_name}-koku-api-reads."
        f"{cluster_config.namespace}.svc.cluster.local:8000/api/cost-management/v1"
    )
    writes_url = (
        f"http://{cluster_config.helm_release_name}-koku-api-writes."
        f"{cluster_config.namespace}.svc.cluster.local:8000/api/cost-management/v1"
    )
    return reads_url, writes_url


def get_ingress_url(cluster_config: ClusterConfig) -> str:
    """Get ingress upload URL."""
    gateway_url = get_route_url(cluster_config.namespace, f"{cluster_config.helm_release_name}-api")
    if not gateway_url:
        raise RuntimeError("Gateway route not found")
    
    # Gateway route includes /api prefix
    base = gateway_url.rstrip("/")
    if base.endswith("/api"):
        return f"{base}/ingress"
    return f"{base}/api/ingress"


def generate_cluster_data(
    cluster_config: ClusterConfig,
    keycloak_config: KeycloakConfig,
    cluster_info: dict,
    rh_identity: str,
    api_reads_url: str,
    api_writes_url: str,
    ingress_url: str,
    db_pod: str,
    temp_dir: str,
) -> dict:
    """Generate and process data for a single cluster."""
    cluster_id = cluster_info["cluster_id"]
    display_name = cluster_info["display_name"]
    days = cluster_info["days"]
    
    print(f"\n{'='*70}")
    print(f"Processing Cluster: {display_name} ({cluster_id})")
    print(f"{'='*70}")
    
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    print(f"Date range: {start_date.date()} to {end_date.date()} ({days} days)")
    
    # Step 1: Generate NISE data
    print(f"\n[1/5] Generating NISE data...")
    cluster_output_dir = os.path.join(temp_dir, cluster_id)
    os.makedirs(cluster_output_dir, exist_ok=True)
    
    # Create NISE config with realistic workload profiles
    nise_config = NISEConfig(
        node_name=f"{cluster_id}-node-1",
        namespace=cluster_info["namespaces"][0],
        pod_name=f"{cluster_id}-pod-1",
        resource_id=f"{cluster_id}-resource-1",
        cpu_cores=8,
        memory_gig=32,
        cpu_request=2.0,
        mem_request_gig=4.0,
        cpu_limit=4.0,
        mem_limit_gig=8.0,
        pod_seconds=3600,
        cpu_usage=0.5,
        mem_usage_gig=2.0,
        labels="environment:production|app:demo",
    )
    
    files = generate_nise_data(
        cluster_id=cluster_id,
        start_date=start_date,
        end_date=end_date,
        output_dir=cluster_output_dir,
        config=nise_config,
        include_ros=True,  # CRITICAL: Include ROS data
    )
    
    print(f"       Generated {len(files['all_files'])} CSV files")
    print(f"       - Pod usage files: {len(files['pod_usage_files'])}")
    print(f"       - ROS usage files: {len(files['ros_usage_files'])}")
    
    if not files["all_files"]:
        raise RuntimeError(f"NISE generated no CSV files for {cluster_id}")
    
    # Step 2: Register source
    print(f"\n[2/5] Registering source...")
    ingress_pod = get_pod_by_label(
        cluster_config.namespace,
        "app.kubernetes.io/component=ingress",
    )
    
    source_registration = register_source(
        namespace=cluster_config.namespace,
        pod=ingress_pod,
        api_reads_url=api_reads_url,
        api_writes_url=api_writes_url,
        rh_identity_header=rh_identity,
        cluster_id=cluster_id,
        org_id=ORG_ID,
        source_name=display_name,
        container="ingress",
    )
    
    print(f"       Source ID: {source_registration.source_id}")
    print(f"       Source Name: {source_registration.source_name}")
    
    # Step 3: Wait for provider
    print(f"\n[3/5] Waiting for provider in Koku...")
    if not wait_for_provider(cluster_config.namespace, db_pod, cluster_id, timeout=300):
        raise RuntimeError(f"Provider not created for cluster {cluster_id}")
    print("       Provider created")
    
    # Step 4: Upload data
    print(f"\n[4/5] Uploading data via ingress...")
    
    package_path = create_upload_package_from_files(
        pod_usage_files=files["pod_usage_files"],
        ros_usage_files=files["ros_usage_files"],
        cluster_id=cluster_id,
        start_date=start_date,
        end_date=end_date,
        node_label_files=files["node_label_files"] if files["node_label_files"] else None,
        namespace_label_files=files["namespace_label_files"] if files["namespace_label_files"] else None,
    )
    
    upload_url = f"{ingress_url}/v1/upload"
    print(f"       Ingress URL: {upload_url}")
    print(f"       Package size: {os.path.getsize(package_path)} bytes")
    
    # Get JWT token
    upload_token = obtain_jwt_token(keycloak_config)
    
    # Upload with retry
    session = requests.Session()
    session.verify = False
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open(package_path, "rb") as f:
                response = session.post(
                    upload_url,
                    files={"file": ("cost-mgmt.tar.gz", f, "application/vnd.redhat.hccm.filename+tgz")},
                    headers=upload_token.authorization_header,
                    timeout=60,
                )
            
            if response.status_code in [200, 201, 202]:
                print(f"       Upload successful: {response.status_code}")
                break
            elif attempt < max_retries - 1:
                print(f"       Upload attempt {attempt + 1} failed: {response.status_code}, retrying...")
                time.sleep(5)
            else:
                raise RuntimeError(f"Upload failed: {response.status_code} - {response.text[:200]}")
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"       Upload attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(5)
            else:
                raise
    
    # Step 5: Wait for processing
    print(f"\n[5/5] Waiting for Koku processing...")
    schema_name = wait_for_summary_tables(
        cluster_config.namespace,
        db_pod,
        cluster_id,
        timeout=600,
    )
    
    if not schema_name:
        raise RuntimeError(f"Timeout waiting for summary tables for cluster {cluster_id}")
    
    print(f"       Summary tables populated in schema: {schema_name}")
    
    # Get row count
    result = execute_db_query(
        cluster_config.namespace,
        db_pod,
        "costonprem_koku",
        "koku_user",
        f"""
        SELECT COUNT(*)
        FROM {schema_name}.reporting_ocpusagelineitem_daily_summary
        WHERE cluster_id = '{cluster_id}'
        """,
    )
    
    row_count = int(result[0][0]) if result and result[0][0] else 0
    print(f"       Rows in summary table: {row_count}")
    
    return {
        "cluster_id": cluster_id,
        "display_name": display_name,
        "source_id": source_registration.source_id,
        "schema_name": schema_name,
        "row_count": row_count,
        "status": "success",
    }


def main():
    """Main execution."""
    print("="*70)
    print("DEMO DATA GENERATION FOR 3 CLUSTERS")
    print("="*70)
    
    # Setup
    cluster_config = get_cluster_config()
    keycloak_config = get_keycloak_config()
    rh_identity = create_rh_identity_header(ORG_ID)
    api_reads_url, api_writes_url = get_api_urls(cluster_config)
    ingress_url = get_ingress_url(cluster_config)
    
    # Get database pod
    db_pod = get_pod_by_label(
        cluster_config.namespace,
        "app.kubernetes.io/component=database",
    )
    
    print(f"\nConfiguration:")
    print(f"  Namespace: {cluster_config.namespace}")
    print(f"  Keycloak: {keycloak_config.url}")
    print(f"  Database Pod: {db_pod}")
    print(f"  Org ID: {ORG_ID}")
    
    # Create temp directory
    temp_dir = os.path.join("/tmp", f"demo-data-{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)
    print(f"  Temp Directory: {temp_dir}")
    
    results = []
    
    try:
        # Process each cluster
        for cluster_info in CLUSTER_CONFIGS:
            try:
                result = generate_cluster_data(
                    cluster_config=cluster_config,
                    keycloak_config=keycloak_config,
                    cluster_info=cluster_info,
                    rh_identity=rh_identity,
                    api_reads_url=api_reads_url,
                    api_writes_url=api_writes_url,
                    ingress_url=ingress_url,
                    db_pod=db_pod,
                    temp_dir=temp_dir,
                )
                results.append(result)
            except Exception as e:
                print(f"\n❌ ERROR processing {cluster_info['cluster_id']}: {e}")
                results.append({
                    "cluster_id": cluster_info["cluster_id"],
                    "display_name": cluster_info["display_name"],
                    "status": "failed",
                    "error": str(e),
                })
        
        # Summary
        print(f"\n{'='*70}")
        print("GENERATION SUMMARY")
        print(f"{'='*70}")
        
        for result in results:
            if result["status"] == "success":
                print(f"✅ {result['display_name']}: {result['row_count']} rows")
            else:
                print(f"❌ {result['display_name']}: FAILED - {result.get('error', 'Unknown error')}")
        
        # Database verification
        print(f"\n{'='*70}")
        print("DATABASE VERIFICATION")
        print(f"{'='*70}")
        
        verification_query = """
        SELECT cluster_id, COUNT(*) as row_count
        FROM reporting_ocpusagelineitem_daily_summary
        WHERE cluster_id IN ('demo-prod-cluster', 'demo-ml-cluster', 'demo-dev-cluster')
        GROUP BY cluster_id
        ORDER BY cluster_id;
        """
        
        # Get schema name from first successful result
        schema_name = None
        for result in results:
            if result.get("schema_name"):
                schema_name = result["schema_name"]
                break
        
        if schema_name:
            result = execute_db_query(
                cluster_config.namespace,
                db_pod,
                "costonprem_koku",
                "koku_user",
                f"SELECT cluster_id, COUNT(*) FROM {schema_name}.reporting_ocpusagelineitem_daily_summary WHERE cluster_id IN ('demo-prod-cluster', 'demo-ml-cluster', 'demo-dev-cluster') GROUP BY cluster_id ORDER BY cluster_id;",
            )
            
            if result:
                print("\nCluster Summary Table Row Counts:")
                for row in result:
                    print(f"  {row[0]}: {row[1]} rows")
        
    finally:
        # Cleanup temp directory
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"\nCleaned up temp directory: {temp_dir}")


if __name__ == "__main__":
    main()
