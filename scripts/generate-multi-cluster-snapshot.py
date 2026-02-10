#!/usr/bin/env python3
"""
Generate diverse multi-cluster snapshot demo (8 clusters with unique patterns).
Shows variety across different workload types, scales, and usage levels.
"""
import os
import sys
import subprocess
import tempfile
import csv
import random
from datetime import datetime, date, timedelta
from pathlib import Path
from multiprocessing import Pool, cpu_count

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value
from helpers import create_upload_package_from_files
import requests

random.seed(42)

# 8 diverse cluster scenarios
CLUSTERS = [
    {"id": "prod-ecommerce-us-east", "name": "Production E-commerce (US-East)", 
     "cpu": 3.2, "mem": 6.4, "desc": "High traffic web tier"},
    
    {"id": "prod-ecommerce-eu", "name": "Production E-commerce (EU)",
     "cpu": 2.8, "mem": 5.6, "desc": "Evening traffic peak"},
    
    {"id": "prod-api-gateway", "name": "Production API Gateway",
     "cpu": 4.1, "mem": 8.2, "desc": "Heavy API load"},
    
    {"id": "staging-performance", "name": "Staging Performance Testing",
     "cpu": 2.4, "mem": 4.8, "desc": "Load test in progress"},
    
    {"id": "dev-feature-team-a", "name": "Development Team A",
     "cpu": 1.3, "mem": 2.6, "desc": "Active development"},
    
    {"id": "dev-feature-team-b", "name": "Development Team B",
     "cpu": 0.7, "mem": 1.4, "desc": "Light usage"},
    
    {"id": "qa-automation", "name": "QA Automation",
     "cpu": 1.9, "mem": 3.8, "desc": "Test suite running"},
    
    {"id": "prod-data-pipeline", "name": "Production Data Pipeline",
     "cpu": 5.2, "mem": 10.4, "desc": "Batch processing active"},
]


def create_nise_config(cluster_id, cpu, mem):
    """Create NISE config with unique resource usage."""
    today = date.today().strftime("%Y-%m-%d")
    
    # Add slight randomization to make each cluster truly unique
    cpu_var = random.uniform(-0.05, 0.05)
    mem_var = random.uniform(-0.1, 0.1)
    
    return f"""---
generators:
  - OCPGenerator:
      start_date: {today}
      end_date: {today}
      nodes:
        - node:
          node_name: {cluster_id}-worker-1
          cpu_cores: 16
          memory_gig: 64
          resource_id: {cluster_id}-node-1
          labels: cluster:{cluster_id}
          namespaces:
            default:
              pods:
                - pod:
                  pod_name: app-primary
                  cpu_request: 2.0
                  mem_request_gig: 4.0
                  cpu_limit: 4.0
                  mem_limit_gig: 8.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {round(cpu + cpu_var, 3)}
                  mem_usage_gig:
                    full_period: {round(mem + mem_var, 3)}
                  labels: app:primary|cluster:{cluster_id}
                - pod:
                  pod_name: app-secondary
                  cpu_request: 1.5
                  mem_request_gig: 3.0
                  cpu_limit: 3.0
                  mem_limit_gig: 6.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {round(cpu * 0.6 + cpu_var, 3)}
                  mem_usage_gig:
                    full_period: {round(mem * 0.6 + mem_var, 3)}
                  labels: app:secondary|cluster:{cluster_id}
                - pod:
                  pod_name: database
                  cpu_request: 3.0
                  mem_request_gig: 8.0
                  cpu_limit: 6.0
                  mem_limit_gig: 16.0
                  pod_seconds: 86400
                  cpu_usage:
                    full_period: {round(cpu * 1.5 + cpu_var, 3)}
                  mem_usage_gig:
                    full_period: {round(mem * 2.0 + mem_var, 3)}
                  labels: app:database|cluster:{cluster_id}
"""


def gen_cluster(args):
    """Generate NISE data for one cluster."""
    cluster_data, work_dir = args
    cluster_id = cluster_data["id"]
    
    config_yaml = create_nise_config(cluster_id, cluster_data["cpu"], cluster_data["mem"])
    yaml_path = os.path.join(work_dir, f"{cluster_id}.yml")
    with open(yaml_path, 'w') as f:
        f.write(config_yaml)
    
    nise_dir = os.path.join(work_dir, f"{cluster_id}_out")
    os.makedirs(nise_dir, exist_ok=True)
    
    cmd = ['nise', 'report', 'ocp', '--static-report-file', yaml_path,
           '--ocp-cluster-id', cluster_id, '--ros-ocp-info', '-w']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=nise_dir)
        if result.returncode != 0:
            return {"cluster": cluster_id, "status": "failed", "error": result.stderr}
        
        files = {"pod": [], "ros": [], "node": [], "ns": []}
        for root, _, filenames in os.walk(nise_dir):
            for fn in filenames:
                if not fn.endswith('.csv'):
                    continue
                fp = os.path.join(root, fn)
                with open(fp, 'r') as f:
                    if len(f.readlines()) <= 1:
                        continue
                if 'pod_usage' in fn:
                    files["pod"].append(fp)
                elif 'ros_usage' in fn:
                    files["ros"].append(fp)
                elif 'node_label' in fn:
                    files["node"].append(fp)
                elif 'namespace_label' in fn:
                    files["ns"].append(fp)
        
        return {"cluster": cluster_id, "status": "success", "files": files, "data": cluster_data}
    except Exception as e:
        return {"cluster": cluster_id, "status": "failed", "error": str(e)}


def register_source(config, jwt, cluster_id, name):
    gateway_url = get_route_url(config.namespace, f"{config.helm_release_name}-api")
    api_base = f"{gateway_url}/api/cost-management/v1"
    
    resp = requests.get(f"{api_base}/source_types", headers={"Authorization": f"Bearer {jwt}"},
                        verify=False, timeout=30)
    resp.raise_for_status()
    source_type_id = next((st["id"] for st in resp.json().get("data", []) if st.get("name") == "openshift"), None)
    
    resp = requests.post(
        f"{api_base}/sources",
        json={"name": name, "source_type_id": source_type_id, "source_ref": cluster_id},
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        verify=False, timeout=60
    )
    resp.raise_for_status()
    source_id = resp.json().get("id")
    
    # Create application
    app_resp = requests.get(f"{api_base}/application_types", headers={"Authorization": f"Bearer {jwt}"},
                           verify=False, timeout=30)
    if app_resp.status_code == 200:
        app_type_id = next((at["id"] for at in app_resp.json().get("data", [])
                           if at.get("name") == "/insights/platform/cost-management"), None)
        if app_type_id:
            requests.post(
                f"{api_base}/applications",
                json={"source_id": source_id, "application_type_id": app_type_id,
                     "extra": {"bucket": "koku-bucket", "cluster_id": cluster_id}},
                headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
                verify=False, timeout=30
            )
    
    return source_id


def upload(config, tar_path, jwt):
    gateway_url = get_route_url(config.namespace, f"{config.helm_release_name}-api")
    with open(tar_path, "rb") as f:
        files = {"file": ("cost-mgmt.tar.gz", f, "application/vnd.redhat.hccm.filename+tgz")}
        resp = requests.post(f"{gateway_url}/api/ingress/v1/upload", files=files,
                            headers={"Authorization": f"Bearer {jwt}"}, verify=False, timeout=120)
        resp.raise_for_status()
        return resp.json()


def main():
    print("=" * 70)
    print("MULTI-CLUSTER SNAPSHOT DEMO (8 diverse clusters)")
    print("=" * 70)
    
    cluster_config = ClusterConfig(
        namespace=os.environ.get("NAMESPACE", "cost-onprem"),
        helm_release_name=os.environ.get("HELM_RELEASE_NAME", "cost-onprem"),
        keycloak_namespace=os.environ.get("KEYCLOAK_NAMESPACE", "keycloak"),
    )
    
    print(f"\nGenerating data for TODAY ({date.today()})")
    print(f"8 clusters with unique usage patterns:\n")
    for idx, c in enumerate(CLUSTERS, 1):
        print(f"  {idx}. {c['name']}: cpu={c['cpu']}, mem={c['mem']} - {c['desc']}")
    
    # Get JWT
    keycloak_url = get_route_url(cluster_config.keycloak_namespace, "keycloak")
    client_secret = get_secret_value(cluster_config.keycloak_namespace,
                                     "keycloak-client-secret-cost-management-operator", "CLIENT_SECRET")
    resp = requests.post(f"{keycloak_url}/realms/kubernetes/protocol/openid-connect/token",
                        data={"grant_type": "client_credentials", "client_id": "cost-management-operator",
                              "client_secret": client_secret}, verify=False, timeout=30)
    jwt_token = resp.json()["access_token"]
    
    print("\n" + "=" * 70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate all clusters in parallel
        print(f"[1/3] Generating 8 clusters in parallel...")
        args = [(c, tmpdir) for c in CLUSTERS]
        with Pool(min(8, cpu_count())) as pool:
            results = pool.map(gen_cluster, args)
        
        success = [r for r in results if r["status"] == "success"]
        print(f"  ✅ Generated {len(success)}/8 clusters\n")
        
        # Register and upload each
        print(f"[2/3] Registering sources and uploading data...\n")
        uploaded = []
        
        for r in success:
            cluster_id = r["cluster"]
            cluster_data = r["data"]
            
            try:
                # Register
                source_id = register_source(cluster_config, jwt_token, cluster_id, cluster_data["name"])
                print(f"  ✅ {cluster_data['name']}: registered (source {source_id})")
                
                # Package - use Feb 5 explicitly (laptop date) since NISE generates for system date
                feb_5 = datetime(2026, 2, 5)
                pkg = create_upload_package_from_files(
                    pod_usage_files=r["files"]["pod"],
                    ros_usage_files=r["files"]["ros"],
                    cluster_id=cluster_id,
                    start_date=feb_5,
                    end_date=datetime(2026, 2, 6),
                    node_label_files=r["files"]["node"],
                    namespace_label_files=r["files"]["ns"],
                )
                
                # Upload
                up_resp = upload(cluster_config, pkg, jwt_token)
                print(f"     Uploaded: {up_resp.get('request_id', 'OK')}")
                
                uploaded.append({
                    "id": cluster_id,
                    "name": cluster_data["name"],
                    "cpu": cluster_data["cpu"],
                    "mem": cluster_data["mem"],
                    "source_id": source_id
                })
                
            except Exception as e:
                print(f"  ❌ {cluster_data['name']}: {e}")
        
        print(f"\n[3/3] Waiting for processing...")
        import time
        time.sleep(30)
    
    print(f"\n{'=' * 70}")
    print("✅ MULTI-CLUSTER SNAPSHOT COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n📊 {len(uploaded)} clusters with unique usage patterns:")
    
    # Sort by CPU to show variety
    for c in sorted(uploaded, key=lambda x: x["cpu"]):
        print(f"  • {c['name']}: {c['cpu']} CPU cores, {c['mem']} GB RAM")
    
    print(f"\n🎯 Demo shows diverse workload ecosystem spanning:")
    print(f"  • CPU range: {min(c['cpu'] for c in uploaded):.1f} - {max(c['cpu'] for c in uploaded):.1f} cores")
    print(f"  • Memory range: {min(c['mem'] for c in uploaded):.1f} - {max(c['mem'] for c in uploaded):.1f} GB")
    print(f"\n💡 Each cluster has unique resource consumption for today!")


if __name__ == "__main__":
    main()
