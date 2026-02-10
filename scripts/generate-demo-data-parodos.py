#!/usr/bin/env python3
"""
Generate demo data for 3 clusters on parodos-dev for customer demonstration.

This script generates realistic demo data for:
- demo-prod-cluster: Production web application workloads
- demo-ml-cluster: ML/MLOps workloads  
- demo-dev-cluster: Development environment workloads

Each cluster gets 7 days of data with varied workload profiles.
"""

import os
import sys
import time
import tempfile
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers import (
    generate_nise_data,
    register_source,
    wait_for_provider,
    wait_for_summary_tables,
    get_koku_api_reads_url,
    get_koku_api_writes_url,
)
from helpers import (
    create_upload_package_from_files,
    exec_in_pod,
    get_pod_by_label,
    execute_db_query,
    get_secret_value,
    get_route_url,
)
from helpers.config import (
    ClusterConfig,
    KeycloakConfig,
)
import requests
import base64
import json
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        "duration_days": 7,
        "description": "Production web application with high utilization",
    },
    {
        "cluster_id": "demo-ml-cluster",
        "display_name": "ML/MLOps Cluster",
        "namespaces": ["ml-dev", "ml-training"],
        "duration_days": 7,
        "description": "ML/MLOps workloads with bursty patterns",
    },
    {
        "cluster_id": "demo-dev-cluster",
        "display_name": "Development Cluster",
        "namespaces": ["dev-team-a", "dev-team-b", "ci-cd"],
        "duration_days": 7,
        "description": "Development environment with low-medium utilization",
    },
]


def create_rh_identity_header(org_id: str, account_number: str = "7890123") -> str:
    """Create X-Rh-Identity header for API calls."""
    identity = {
        "identity": {
            "org_id": org_id,
            "account_number": account_number,
            "type": "User",
            "user": {
                "username": "demo-user",
                "email": "demo@example.com",
            },
        }
    }
    encoded = base64.b64encode(json.dumps(identity).encode()).decode()
    return encoded


def obtain_jwt_token(keycloak_config: KeycloakConfig):
    """Obtain a fresh JWT token from Keycloak using client credentials flow."""
    response = requests.post(
        keycloak_config.token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": keycloak_config.client_id,
            "client_secret": keycloak_config.client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=False,
        timeout=30,
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"Failed to obtain JWT token: {response.status_code} - {response.text}")
    
    token_data = response.json()
    expires_in = token_data.get("expires_in", 300)
    
    class JWTToken:
        def __init__(self, access_token, expires_at):
            self.access_token = access_token
            self.expires_at = expires_at
        
        @property
        def authorization_header(self):
            return {"Authorization": f"Bearer {self.access_token}"}
    
    from datetime import timedelta
    return JWTToken(
        access_token=token_data["access_token"],
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


def get_cluster_setup():
    """Get cluster configuration and authentication."""
    cluster_config = ClusterConfig(
        namespace=NAMESPACE,
        helm_release_name=HELM_RELEASE_NAME,
        keycloak_namespace=KEYCLOAK_NAMESPACE,
    )
    
    # Get Keycloak config
    keycloak_url = get_route_url(KEYCLOAK_NAMESPACE, "keycloak")
    if not keycloak_url:
        raise RuntimeError(f"Keycloak route not found in {KEYCLOAK_NAMESPACE}")
    
    client_id = "cost-management-operator"
    client_secret = get_secret_value(
        KEYCLOAK_NAMESPACE,
        "keycloak-client-secret-cost-management-operator",
        "CLIENT_SECRET",
    )
    if not client_secret:
        raise RuntimeError("Keycloak client secret not found")
    
    keycloak_config = KeycloakConfig(
        url=keycloak_url,
        client_id=client_id,
        client_secret=client_secret,
    )
    
    # Get ingress pod
    ingress_pod = get_pod_by_label(
        NAMESPACE, "app.kubernetes.io/component=ingress"
    )
    if not ingress_pod:
        raise RuntimeError("Ingress pod not found")
    
    # Get API URLs
    api_reads_url = get_koku_api_reads_url(HELM_RELEASE_NAME, NAMESPACE)
    api_writes_url = get_koku_api_writes_url(HELM_RELEASE_NAME, NAMESPACE)
    
    # Get ingress URL
    gateway_url = get_route_url(NAMESPACE, f"{HELM_RELEASE_NAME}-api")
    if gateway_url:
        ingress_url = f"{gateway_url}/ingress"
    else:
        raise RuntimeError("Gateway route not found")
    
    # Get database pod
    db_pod = get_pod_by_label(
        NAMESPACE, "app.kubernetes.io/component=database"
    )
    if not db_pod:
        raise RuntimeError("Database pod not found")
    
    # Create X-Rh-Identity header
    rh_identity = create_rh_identity_header(ORG_ID)
    
    return {
        "cluster_config": cluster_config,
        "keycloak_config": keycloak_config,
        "ingress_pod": ingress_pod,
        "api_reads_url": api_reads_url,
        "api_writes_url": api_writes_url,
        "ingress_url": ingress_url,
        "db_pod": db_pod,
        "rh_identity": rh_identity,
    }


def generate_cluster_data(cluster_info: dict, setup: dict, output_dir: str):
    """Generate and process data for a single cluster."""
    cluster_id = cluster_info["cluster_id"]
    display_name = cluster_info["display_name"]
    duration_days = cluster_info["duration_days"]
    
    print(f"\n{'='*70}")
    print(f"Processing Cluster: {display_name} ({cluster_id})")
    print(f"{'='*70}")
    
    # Calculate date range (last N days)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=duration_days)
    
    print(f"Date range: {start_date.date()} to {end_date.date()} ({duration_days} days)")
    
    # Step 1: Generate NISE data
    print(f"\n[1/5] Generating NISE data...")
    cluster_output_dir = os.path.join(output_dir, cluster_id)
    os.makedirs(cluster_output_dir, exist_ok=True)
    
    try:
        files = generate_nise_data(
            cluster_id=cluster_id,
            start_date=start_date,
            end_date=end_date,
            output_dir=cluster_output_dir,
            config=None,  # Use default NISE config
            include_ros=True,  # CRITICAL: Include ROS data
        )
        print(f"       Generated {len(files['all_files'])} CSV files")
        print(f"       - Pod usage files: {len(files['pod_usage_files'])}")
        print(f"       - ROS usage files: {len(files['ros_usage_files'])}")
        
        if not files["all_files"]:
            raise RuntimeError("NISE generated no CSV files")
        
        # Step 2: Register source
        print(f"\n[2/5] Registering source...")
        source_registration = register_source(
            namespace=setup["cluster_config"].namespace,
            pod=setup["ingress_pod"],
            api_reads_url=setup["api_reads_url"],
            api_writes_url=setup["api_writes_url"],
            rh_identity_header=setup["rh_identity"],
            cluster_id=cluster_id,
            org_id=ORG_ID,
            source_name=display_name,
            container="ingress",
        )
        print(f"       Source ID: {source_registration.source_id}")
        
        # Step 3: Wait for provider
        print(f"\n[3/5] Waiting for provider in Koku...")
        if not wait_for_provider(
            setup["cluster_config"].namespace,
            setup["db_pod"],
            cluster_id,
            timeout=300,
        ):
            raise RuntimeError(f"Provider not created for cluster {cluster_id}")
        print("       Provider created")
        
        # Step 4: Create upload package
        print(f"\n[4/5] Creating upload package...")
        package_path = create_upload_package_from_files(
            pod_usage_files=files["pod_usage_files"],
            ros_usage_files=files["ros_usage_files"],
            cluster_id=cluster_id,
            start_date=start_date,
            end_date=end_date,
            node_label_files=files.get("node_label_files") or None,
            namespace_label_files=files.get("namespace_label_files") or None,
        )
        package_size = os.path.getsize(package_path)
        print(f"       Package created: {package_path}")
        print(f"       Package size: {package_size:,} bytes")
        
        # Step 5: Upload data
        print(f"\n[5/5] Uploading data via ingress...")
        upload_url = f"{setup['ingress_url']}/v1/upload"
        print(f"       Upload URL: {upload_url}")
        
        # Get JWT token
        jwt_token = obtain_jwt_token(setup["keycloak_config"])
        
        # Upload with retry
        session = requests.Session()
        session.verify = False
        
        max_retries = 3
        retry_delay = 5
        upload_success = False
        
        for attempt in range(max_retries):
            try:
                with open(package_path, "rb") as f:
                    response = session.post(
                        upload_url,
                        files={"file": ("cost-mgmt.tar.gz", f, "application/vnd.redhat.hccm.filename+tgz")},
                        headers=jwt_token.authorization_header,
                        timeout=120,
                    )
                
                if response.status_code in [200, 201, 202]:
                    upload_success = True
                    print(f"       Upload successful: {response.status_code}")
                    break
                elif response.status_code >= 500 and attempt < max_retries - 1:
                    print(f"       Attempt {attempt + 1}/{max_retries} failed: HTTP {response.status_code}, retrying...")
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    raise RuntimeError(f"Upload failed: HTTP {response.status_code} - {response.text[:200]}")
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    print(f"       Attempt {attempt + 1}/{max_retries} failed: {e}, retrying...")
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    raise
        
        if not upload_success:
            raise RuntimeError("Upload failed after all retries")
        
        # Step 6: Wait for processing
        print(f"\n[6/6] Waiting for data processing...")
        schema_name = wait_for_summary_tables(
            setup["cluster_config"].namespace,
            setup["db_pod"],
            cluster_id,
            timeout=600,
        )
        
        if not schema_name:
            raise RuntimeError(f"Timeout waiting for summary tables for cluster {cluster_id}")
        print(f"       Summary tables populated in schema: {schema_name}")
        
        # Verify data count
        result = execute_db_query(
            setup["cluster_config"].namespace,
            setup["db_pod"],
            "costonprem_koku",
            "koku_user",
            f"""
            SELECT COUNT(*), MIN(usage_start), MAX(usage_start)
            FROM {schema_name}.reporting_ocpusagelineitem_daily_summary
            WHERE cluster_id = '{cluster_id}'
            """,
        )
        
        if result and result[0]:
            row_count = result[0][0]
            min_date = result[0][1]
            max_date = result[0][2]
            print(f"       Data rows in summary: {row_count}")
            print(f"       Date range: {min_date} to {max_date}")
        
        print(f"\n✅ Cluster {display_name} completed successfully!")
        
        return {
            "cluster_id": cluster_id,
            "source_id": source_registration.source_id,
            "schema_name": schema_name,
            "row_count": row_count if result and result[0] else 0,
            "status": "success",
        }
        
    except Exception as e:
        print(f"\n❌ Error processing cluster {cluster_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "cluster_id": cluster_id,
            "status": "failed",
            "error": str(e),
        }


def main():
    """Main execution function."""
    print("="*70)
    print("DEMO DATA GENERATION FOR PARODOS-DEV")
    print("="*70)
    print(f"Namespace: {NAMESPACE}")
    print(f"Helm Release: {HELM_RELEASE_NAME}")
    print(f"Keycloak Namespace: {KEYCLOAK_NAMESPACE}")
    print(f"Org ID: {ORG_ID}")
    print("="*70)
    
    # Get cluster setup
    print("\n[Setup] Getting cluster configuration...")
    setup = get_cluster_setup()
    print("       ✓ Cluster configuration ready")
    
    # Create output directory
    output_dir = tempfile.mkdtemp(prefix="demo-data-")
    print(f"\n[Setup] Output directory: {output_dir}")
    
    results = []
    
    try:
        # Process each cluster
        for cluster_info in CLUSTER_CONFIGS:
            result = generate_cluster_data(cluster_info, setup, output_dir)
            results.append(result)
            
            # Brief pause between clusters
            if cluster_info != CLUSTER_CONFIGS[-1]:
                print("\nWaiting 10 seconds before next cluster...")
                time.sleep(10)
        
        # Summary
        print("\n" + "="*70)
        print("GENERATION SUMMARY")
        print("="*70)
        
        for result in results:
            status_icon = "✅" if result["status"] == "success" else "❌"
            print(f"{status_icon} {result['cluster_id']}: {result.get('status', 'unknown')}")
            if result["status"] == "success":
                print(f"   Source ID: {result.get('source_id', 'N/A')}")
                print(f"   Schema: {result.get('schema_name', 'N/A')}")
                print(f"   Rows: {result.get('row_count', 0)}")
            elif "error" in result:
                print(f"   Error: {result['error']}")
        
        # Database verification
        print("\n" + "="*70)
        print("DATABASE VERIFICATION")
        print("="*70)
        
        db_query = """
        SELECT cluster_id, COUNT(*) as row_count, 
               MIN(usage_start) as min_date, MAX(usage_start) as max_date
        FROM reporting_common_costusagereportmanifest m
        JOIN api_provider p ON m.provider_id = p.uuid
        JOIN api_customer c ON p.customer_id = c.id
        WHERE m.cluster_id LIKE 'demo-%'
        GROUP BY cluster_id
        ORDER BY cluster_id;
        """
        
        # Try to get schema name first
        schema_result = execute_db_query(
            setup["cluster_config"].namespace,
            setup["db_pod"],
            "costonprem_koku",
            "koku_user",
            """
            SELECT DISTINCT c.schema_name 
            FROM reporting_common_costusagereportmanifest m
            JOIN api_provider p ON m.provider_id = p.uuid
            JOIN api_customer c ON p.customer_id = c.id
            WHERE m.cluster_id LIKE 'demo-%'
            LIMIT 1
            """,
        )
        
        if schema_result and schema_result[0]:
            schema_name = schema_result[0][0]
            summary_query = f"""
            SELECT cluster_id, COUNT(*) as row_count,
                   MIN(usage_start) as min_date, MAX(usage_start) as max_date
            FROM {schema_name}.reporting_ocpusagelineitem_daily_summary
            WHERE cluster_id LIKE 'demo-%'
            GROUP BY cluster_id
            ORDER BY cluster_id;
            """
            
            summary_result = execute_db_query(
                setup["cluster_config"].namespace,
                setup["db_pod"],
                "costonprem_koku",
                "koku_user",
                summary_query,
            )
            
            if summary_result:
                print("\nSummary Table Data:")
                for row in summary_result:
                    print(f"  {row[0]}: {row[1]} rows ({row[2]} to {row[3]})")
        
        print("\n" + "="*70)
        print("✅ DEMO DATA GENERATION COMPLETE")
        print("="*70)
        
    finally:
        # Cleanup temp directory
        if os.path.exists(output_dir):
            print(f"\n[Cleanup] Removing temp directory: {output_dir}")
            shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
