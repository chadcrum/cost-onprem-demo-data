"""Upload package creation utilities."""

import json
import os
import tarfile
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


def create_upload_package_from_files(
    pod_usage_files: list[str],
    ros_usage_files: list[str],
    cluster_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    node_label_files: Optional[list[str]] = None,
    namespace_label_files: Optional[list[str]] = None,
) -> str:
    """Create a tar.gz upload package from NISE-generated files.

    Returns:
        Path to the created tar.gz file
    """
    temp_dir = tempfile.mkdtemp()
    manifest_file = Path(temp_dir) / "manifest.json"
    tar_file = Path(temp_dir) / "cost-mgmt.tar.gz"

    now = datetime.now(timezone.utc)
    if start_date is None:
        start_date = now - timedelta(days=1)
    if end_date is None:
        end_date = now

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    pod_filenames = [os.path.basename(f) for f in pod_usage_files]
    ros_filenames = [os.path.basename(f) for f in ros_usage_files]
    node_label_filenames = [os.path.basename(f) for f in (node_label_files or [])]
    namespace_label_filenames = [os.path.basename(f) for f in (namespace_label_files or [])]

    all_data_files = pod_filenames + node_label_filenames + namespace_label_filenames

    manifest = {
        "uuid": str(uuid.uuid4()),
        "cluster_id": cluster_id,
        "cluster_alias": f"e2e-source-{cluster_id[-8:]}",
        "date": now.isoformat(),
        "files": all_data_files,
        "resource_optimization_files": ros_filenames,
        "certified": True,
        "operator_version": "1.0.0",
        "daily_reports": False,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }
    manifest_file.write_text(json.dumps(manifest, indent=2))

    with tarfile.open(tar_file, "w:gz") as tar:
        for filepath in pod_usage_files:
            tar.add(filepath, arcname=os.path.basename(filepath))
        for filepath in ros_usage_files:
            tar.add(filepath, arcname=os.path.basename(filepath))
        if node_label_files:
            for filepath in node_label_files:
                tar.add(filepath, arcname=os.path.basename(filepath))
        if namespace_label_files:
            for filepath in namespace_label_files:
                tar.add(filepath, arcname=os.path.basename(filepath))
        tar.add(manifest_file, arcname="manifest.json")

    return str(tar_file)
