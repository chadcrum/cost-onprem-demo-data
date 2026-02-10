"""NISE data generation utilities."""

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


DEFAULT_NISE_CONFIG = {
    "node_name": "test-node-1",
    "namespace": "test-namespace",
    "pod_name": "test-pod-1",
    "resource_id": "test-resource-1",
    "cpu_cores": 2,
    "memory_gig": 8,
    "cpu_request": 0.5,
    "mem_request_gig": 1,
    "cpu_limit": 1,
    "mem_limit_gig": 2,
    "pod_seconds": 3600,
    "cpu_usage": 0.25,
    "mem_usage_gig": 0.5,
    "labels": "environment:test|app:e2e-test",
}


@dataclass
class NISEConfig:
    """Configuration for NISE data generation."""

    node_name: str = DEFAULT_NISE_CONFIG["node_name"]
    namespace: str = DEFAULT_NISE_CONFIG["namespace"]
    pod_name: str = DEFAULT_NISE_CONFIG["pod_name"]
    resource_id: str = DEFAULT_NISE_CONFIG["resource_id"]
    cpu_cores: int = DEFAULT_NISE_CONFIG["cpu_cores"]
    memory_gig: int = DEFAULT_NISE_CONFIG["memory_gig"]
    cpu_request: float = DEFAULT_NISE_CONFIG["cpu_request"]
    mem_request_gig: float = DEFAULT_NISE_CONFIG["mem_request_gig"]
    cpu_limit: float = DEFAULT_NISE_CONFIG["cpu_limit"]
    mem_limit_gig: float = DEFAULT_NISE_CONFIG["mem_limit_gig"]
    pod_seconds: int = DEFAULT_NISE_CONFIG["pod_seconds"]
    cpu_usage: float = DEFAULT_NISE_CONFIG["cpu_usage"]
    mem_usage_gig: float = DEFAULT_NISE_CONFIG["mem_usage_gig"]
    labels: str = DEFAULT_NISE_CONFIG["labels"]

    def to_yaml(self, cluster_id: str, start_date: datetime, end_date: datetime) -> str:
        """Generate NISE static report YAML."""
        return f"""---
generators:
  - OCPGenerator:
      start_date: {start_date.strftime('%Y-%m-%d')}
      end_date: {end_date.strftime('%Y-%m-%d')}
      nodes:
        - node:
          node_name: {self.node_name}
          cpu_cores: {self.cpu_cores}
          memory_gig: {self.memory_gig}
          resource_id: {self.resource_id}
          labels: node-role.kubernetes.io/worker:true|kubernetes.io/os:linux
          namespaces:
            {self.namespace}:
              labels: openshift.io/cluster-monitoring:true
              pods:
                - pod:
                  pod_name: {self.pod_name}
                  cpu_request: {self.cpu_request}
                  mem_request_gig: {self.mem_request_gig}
                  cpu_limit: {self.cpu_limit}
                  mem_limit_gig: {self.mem_limit_gig}
                  pod_seconds: {self.pod_seconds}
                  cpu_usage:
                    full_period: {self.cpu_usage}
                  mem_usage_gig:
                    full_period: {self.mem_usage_gig}
                  labels: {self.labels}
"""


def is_nise_available() -> bool:
    """Check if NISE is available for data generation."""
    try:
        result = subprocess.run(
            ["nise", "--version"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_nise() -> bool:
    """Attempt to install NISE via pip."""
    try:
        print("  Installing koku-nise...")
        result = subprocess.run(
            ["pip", "install", "koku-nise"], capture_output=True, text=True, timeout=120
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_nise_available() -> bool:
    """Ensure NISE is available, installing if necessary."""
    if is_nise_available():
        return True
    return install_nise()


def generate_nise_data(
    cluster_id: str,
    start_date: datetime,
    end_date: datetime,
    output_dir: str,
    config: Optional[NISEConfig] = None,
    include_ros: bool = True,
) -> Dict[str, List[str]]:
    """Generate NISE OCP data and return categorized file paths."""
    if config is None:
        config = NISEConfig()

    yaml_content = config.to_yaml(cluster_id, start_date, end_date)
    yaml_path = os.path.join(output_dir, "static_report.yml")
    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    nise_output = os.path.join(output_dir, "nise_output")
    os.makedirs(nise_output, exist_ok=True)

    cmd = [
        "nise", "report", "ocp",
        "--static-report-file", yaml_path,
        "--ocp-cluster-id", cluster_id,
        "-w",
    ]
    if include_ros:
        cmd.append("--ros-ocp-info")

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300, cwd=nise_output
    )

    if result.returncode != 0:
        raise RuntimeError(f"NISE failed: {result.stderr}")

    files = {
        "pod_usage_files": [],
        "ros_usage_files": [],
        "node_label_files": [],
        "namespace_label_files": [],
        "all_files": [],
    }

    for root, _, filenames in os.walk(nise_output):
        for f in filenames:
            if f.endswith(".csv"):
                full_path = os.path.join(root, f)
                files["all_files"].append(full_path)

                if "pod_usage" in f:
                    files["pod_usage_files"].append(full_path)
                elif "ros_usage" in f:
                    files["ros_usage_files"].append(full_path)
                elif "node_label" in f:
                    files["node_label_files"].append(full_path)
                elif "namespace_label" in f:
                    files["namespace_label_files"].append(full_path)

    if not files["ros_usage_files"]:
        files["ros_usage_files"] = files["pod_usage_files"]

    return files
