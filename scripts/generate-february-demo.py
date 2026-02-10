#!/usr/bin/env python3
"""
Generate full February 2026 demo data (Feb 5-28 = 24 days).
Uses existing sources, generates varied unique daily values.
"""
import os
import sys
import subprocess
import tempfile
import csv
import random
from datetime import datetime, timedelta, date
from pathlib import Path
from multiprocessing import Pool, cpu_count

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value
from helpers import create_upload_package_from_files
import requests

random.seed(42)

def get_daily_config(cluster_id: str, date_obj: date):
    """Get unique CPU/memory config for a specific date."""
    weekday = date_obj.weekday()
    day = date_obj.day
    time_factor = (day * 7 + weekday) / 100.0
    
    if cluster_id == "demo-prod-cluster":
        if 22 <= day <= 23:
            base_cpu, base_mem, variation = 3.5, 7.0, 0.3
        elif weekday >= 5:
            base_cpu, base_mem, variation = 2.4, 4.8, 0.25
        elif weekday == 4:
            base_cpu, base_mem, variation = 1.9, 3.8, 0.15
        elif weekday == 0:
            base_cpu, base_mem, variation = 1.3, 2.6, 0.12
        else:
            base_cpu, base_mem, variation = 1.6, 3.2, 0.15
        
        daily_var = random.uniform(-variation, variation)
        cpu = round(base_cpu + daily_var + time_factor * 0.01, 3)
        mem = round(base_mem + daily_var * 2 + time_factor * 0.02, 3)
        return {"cpu": cpu, "mem": mem}
    
    elif cluster_id == "demo-dev-cluster":
        if day in [6, 13, 20, 27]:
            base_cpu, base_mem, variation = 3.0, 6.0, 0.4
        elif weekday >= 5:
            base_cpu, base_mem, variation = 0.2, 0.5, 0.08
        else:
            base_cpu, base_mem, variation = 1.1, 2.2, 0.2
        
        daily_var = random.uniform(-variation, variation)
        cpu = max(0.1, round(base_cpu + daily_var + time_factor * 0.01, 3))
        mem = max(0.3, round(base_mem + daily_var * 2 + time_factor * 0.02, 3))
        return {"cpu": cpu, "mem": mem}
    
    elif cluster_id == "demo-staging-cluster":
        if day in [6, 13, 20, 27]:
            base_cpu, base_mem, variation = 2.8, 5.6, 0.35
        else:
            base_cpu, base_mem, variation = 1.0, 2.0, 0.25
        
        daily_var = random.uniform(-variation, variation)
        cpu = round(base_cpu + daily_var + time_factor * 0.02, 3)
        mem = round(base_mem + daily_var * 2 + time_factor * 0.04, 3)
        return {"cpu": cpu, "mem": mem}
    
    return {"cpu": 1.0, "mem": 2.0}


def create_nise_config(cluster_id, cpu, mem, date_str):
    return f"""---
generators:
  - OCPGenerator:
      start_date: {date_str}
      end_date: {date_str}
      nodes:
        - node:
          node_name: {cluster_id}-w1
          cpu_cores: 16
          memory_gig: 64
          resource_id: {cluster_id}-n1
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
"""


def gen_day(args):
    cluster_id, date_str, work_dir = args
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    config = get_daily_config(cluster_id, date_obj)
    
    yaml_content = create_nise_config(cluster_id, config["cpu"], config["mem"], date_str)
    yaml_path = os.path.join(work_dir, f"{cluster_id}_{date_str}.yml")
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)
    
    nise_dir = os.path.join(work_dir, f"{cluster_id}_{date_str}_out")
    os.makedirs(nise_dir, exist_ok=True)
    
    cmd = ['nise', 'report', 'ocp', '--static-report-file', yaml_path,
           '--ocp-cluster-id', cluster_id, '--ros-ocp-info', '-w']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=nise_dir)
        if result.returncode != 0:
            return {"date": date_str, "status": "failed", "config": config}
        
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
        
        return {"date": date_str, "status": "success", "files": files, "config": config}
    except Exception as e:
        return {"date": date_str, "status": "failed", "error": str(e), "config": config}


def merge_csvs(file_list, output):
    if not file_list:
        return
    with open(file_list[0], 'r') as f:
        header = next(csv.reader(f))
    with open(output, 'w', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(header)
        for fp in sorted(file_list):
            with open(fp, 'r') as inf:
                next(csv.reader(inf))
                for row in csv.reader(inf):
                    writer.writerow(row)


def main():
    print("=" * 70)
    print("FEBRUARY 2026 DEMO DATA (24 days: Feb 5-28)")
    print("=" * 70)
    
    cluster_config = ClusterConfig(
        namespace=os.environ.get("NAMESPACE", "cost-onprem"),
        helm_release_name=os.environ.get("HELM_RELEASE_NAME", "cost-onprem"),
        keycloak_namespace=os.environ.get("KEYCLOAK_NAMESPACE", "keycloak"),
    )
    
    # Generate Feb 5-28
    today = date.today()
    dates = []
    current = today
    while current.month == 2:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    print(f"\nDates: {len(dates)} days ({dates[0]} to {dates[-1]})")
    
    keycloak_url = get_route_url(cluster_config.keycloak_namespace, "keycloak")
    client_secret = get_secret_value(cluster_config.keycloak_namespace,
                                     "keycloak-client-secret-cost-management-operator", "CLIENT_SECRET")
    resp = requests.post(f"{keycloak_url}/realms/kubernetes/protocol/openid-connect/token",
                        data={"grant_type": "client_credentials", "client_id": "cost-management-operator",
                              "client_secret": client_secret}, verify=False, timeout=30)
    jwt_token = resp.json()["access_token"]
    
    clusters = {
        "demo-prod-cluster": "Production E-commerce",
        "demo-dev-cluster": "Development & CI/CD",
        "demo-staging-cluster": "Staging & Load Testing",
    }
    
    for cluster_id, name in clusters.items():
        print(f"\n{'=' * 70}")
        print(f"{name}")
        print(f"{'=' * 70}")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"  [1/3] Generating {len(dates)} days...")
            args = [(cluster_id, d, tmpdir) for d in dates]
            with Pool(min(12, cpu_count())) as pool:
                results = pool.map(gen_day, args)
            
            success = [r for r in results if r["status"] == "success"]
            print(f"    ✅ {len(success)}/{len(dates)} days")
            
            print(f"  [2/3] Merging CSVs...")
            merged_dir = os.path.join(tmpdir, 'merged')
            os.makedirs(merged_dir)
            
            pod_files = []
            ros_files = []
            node_files = []
            ns_files = []
            for r in success:
                pod_files.extend(r["files"]["pod"])
                ros_files.extend(r["files"]["ros"])
                node_files.extend(r["files"]["node"])
                ns_files.extend(r["files"]["ns"])
            
            pod_out = os.path.join(merged_dir, f"February-2026-{cluster_id}-ocp_pod_usage.csv")
            ros_out = os.path.join(merged_dir, f"February-2026-{cluster_id}-ocp_ros_usage.csv")
            node_out = os.path.join(merged_dir, f"February-2026-{cluster_id}-ocp_node_label.csv")
            ns_out = os.path.join(merged_dir, f"February-2026-{cluster_id}-ocp_namespace_label.csv")
            
            merge_csvs(pod_files, pod_out)
            merge_csvs(ros_files, ros_out)
            merge_csvs(node_files, node_out)
            merge_csvs(ns_files, ns_out)
            
            pkg = create_upload_package_from_files(
                pod_usage_files=[pod_out],
                ros_usage_files=[ros_out],
                cluster_id=cluster_id,
                start_date=datetime(2026, 2, 1),
                end_date=datetime(2026, 3, 1),
                node_label_files=[node_out],
                namespace_label_files=[ns_out],
            )
            print(f"    ✅ Package: {os.path.getsize(pkg) / 1024:.1f} KB")
            
            print(f"  [3/3] Uploading...")
            gateway_url = get_route_url(cluster_config.namespace, f"{cluster_config.helm_release_name}-api")
            with open(pkg, "rb") as f:
                files = {"file": ("cost-mgmt.tar.gz", f, "application/vnd.redhat.hccm.filename+tgz")}
                up_resp = requests.post(f"{gateway_url}/api/ingress/v1/upload", files=files,
                                       headers={"Authorization": f"Bearer {jwt_token}"}, verify=False, timeout=120)
                up_resp.raise_for_status()
                print(f"    ✅ {up_resp.json().get('request_id', 'OK')}")
    
    print(f"\n{'=' * 70}")
    print("✅ COMPLETE - 24 days of varied data uploaded!")
    print("=" * 70)


if __name__ == "__main__":
    main()
