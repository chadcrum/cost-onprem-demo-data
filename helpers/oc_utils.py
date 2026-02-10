"""OpenShift/Kubernetes CLI utilities."""

import base64
import json
import subprocess
import time
from typing import Optional


def run_oc_command(
    args: list[str],
    check: bool = True,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """Run an oc command and return the result."""
    cmd = ["oc"] + args
    return subprocess.run(
        cmd, capture_output=True, text=True, check=check, timeout=timeout
    )


def get_route_url(namespace: str, route_name: str) -> Optional[str]:
    """Get the URL for an OpenShift route."""
    try:
        result = run_oc_command(
            ["get", "route", route_name, "-n", namespace, "-o", "jsonpath={.spec.host}"]
        )
        host = result.stdout.strip()
        if not host:
            return None

        tls_result = run_oc_command(
            ["get", "route", route_name, "-n", namespace,
             "-o", "jsonpath={.spec.tls.termination}"],
            check=False,
        )
        tls = tls_result.stdout.strip()
        scheme = "https" if tls else "http"
        return f"{scheme}://{host}"
    except subprocess.CalledProcessError:
        return None


def get_secret_value(namespace: str, secret_name: str, key: str) -> Optional[str]:
    """Get a decoded value from a Kubernetes secret."""
    try:
        result = run_oc_command(
            ["get", "secret", secret_name, "-n", namespace,
             "-o", f"jsonpath={{.data.{key}}}"]
        )
        encoded = result.stdout.strip()
        if not encoded:
            return None
        return base64.b64decode(encoded).decode("utf-8")
    except (subprocess.CalledProcessError, ValueError):
        return None


def get_pod_by_label(namespace: str, label: str) -> Optional[str]:
    """Get the first pod name matching a label selector."""
    try:
        result = run_oc_command(
            ["get", "pods", "-n", namespace, "-l", label,
             "-o", "jsonpath={.items[0].metadata.name}"],
            check=False,
        )
        pod_name = result.stdout.strip()
        return pod_name if pod_name else None
    except subprocess.CalledProcessError:
        return None


def exec_in_pod(
    namespace: str,
    pod_name: str,
    command: list[str],
    container: Optional[str] = None,
    timeout: int = 60,
) -> Optional[str]:
    """Execute a command in a pod and return stdout."""
    try:
        args = ["exec", "-n", namespace, pod_name]
        if container:
            args.extend(["-c", container])
        args.append("--")
        args.extend(command)

        result = run_oc_command(args, check=False, timeout=timeout)
        return result.stdout if result.returncode == 0 else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def execute_db_query(
    namespace: str,
    pod_name: str,
    database: str,
    user: str,
    query: str,
    password: Optional[str] = None,
) -> Optional[list[tuple]]:
    """Execute a SQL query via kubectl exec and return results."""
    try:
        env_prefix = []
        if password:
            env_prefix = ["env", f"PGPASSWORD={password}"]

        cmd = env_prefix + [
            "psql", "-U", user, "-d", database,
            "-t", "-A", "-F", "|", "-c", query,
        ]

        result = exec_in_pod(namespace, pod_name, cmd, timeout=120)
        if not result:
            return None

        rows = []
        for line in result.strip().split("\n"):
            if line:
                rows.append(tuple(line.split("|")))
        return rows
    except Exception:
        return None


def wait_for_condition(
    check_func,
    timeout: int = 300,
    interval: int = 10,
    description: str = "condition",
) -> bool:
    """Wait for a condition to become true."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_func():
            return True
        time.sleep(interval)
    return False


def create_rh_identity_header(org_id: str, account_number: str = None) -> str:
    """Create X-Rh-Identity header value for Koku authentication."""
    if account_number is None:
        account_number = org_id

    identity_json = {
        "org_id": org_id,
        "identity": {
            "org_id": org_id,
            "account_number": account_number,
            "type": "User",
            "user": {
                "username": "test",
                "email": "test@example.com",
                "is_org_admin": True,
            },
        },
        "entitlements": {
            "cost_management": {"is_entitled": True},
        },
    }

    return base64.b64encode(json.dumps(identity_json).encode()).decode()
