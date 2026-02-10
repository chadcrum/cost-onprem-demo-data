#!/usr/bin/env python3
"""
Delete existing demo sources via Cost Management gateway API (JWT).
Use before running generate-demo-data.py to get a clean 3 sources (prod, dev, staging).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import urllib3
import requests
from helpers.config import ClusterConfig
from helpers.oc_utils import get_route_url, get_secret_value

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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


def main():
    cc = get_cluster_config()
    gateway_url = get_route_url(cc.namespace, f"{cc.helm_release_name}-api")
    if not gateway_url:
        raise RuntimeError("Gateway route not found")
    api_base = f"https://{gateway_url}/api/cost-management/v1"
    token = get_jwt_token(cc)
    headers = {"Authorization": f"Bearer {token}"}

    # List sources
    r = requests.get(f"{api_base}/sources", headers=headers, verify=False, timeout=30)
    r.raise_for_status()
    data = r.json()
    sources = data.get("data", [])
    to_delete = [s for s in sources if s.get("source_ref", "").startswith("demo-")]
    if not to_delete:
        print("No demo sources found. Nothing to delete.")
        return
    print(f"Deleting {len(to_delete)} demo source(s):")
    for s in to_delete:
        uid = s.get("id") or s.get("uuid")
        if uid is not None:
            uid = str(uid)
        name = s.get("name", "")
        ref = s.get("source_ref", "")
        if not uid:
            print(f"  Skip (no id): {name} / {ref}")
            continue
        del_r = requests.delete(
            f"{api_base}/sources/{uid}",
            headers=headers,
            verify=False,
            timeout=30,
        )
        if del_r.status_code in (200, 204):
            print(f"  Deleted: {name} ({ref})")
        else:
            print(f"  Failed to delete {name}: {del_r.status_code} {del_r.text[:200]}")


if __name__ == "__main__":
    main()
