"""E2E utilities: source registration, wait functions, Koku API helpers."""

import json
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests

from helpers.oc_utils import exec_in_pod, execute_db_query, wait_for_condition


DEFAULT_S3_BUCKET = "koku-bucket"
UPLOAD_CONTENT_TYPE = "application/vnd.redhat.hccm.filename+tgz"


@dataclass
class SourceRegistration:
    """Result of source registration."""

    source_id: str
    source_name: str
    cluster_id: str
    org_id: str


def get_koku_api_reads_url(helm_release_name: str, namespace: str) -> str:
    """Get the internal Koku API reads URL for GET operations."""
    return (
        f"http://{helm_release_name}-koku-api-reads."
        f"{namespace}.svc.cluster.local:8000/api/cost-management/v1"
    )


def get_koku_api_writes_url(helm_release_name: str, namespace: str) -> str:
    """Get the internal Koku API writes URL for POST/PUT/DELETE operations."""
    return (
        f"http://{helm_release_name}-koku-api-writes."
        f"{namespace}.svc.cluster.local:8000/api/cost-management/v1"
    )


def _get_source_type_id(
    namespace: str, pod: str, api_url: str, rh_identity_header: str,
    source_type_name: str = "openshift", container: str = "ingress",
) -> Optional[str]:
    result = exec_in_pod(
        namespace, pod,
        ["curl", "-s", f"{api_url}/source_types",
         "-H", "Content-Type: application/json",
         "-H", f"X-Rh-Identity: {rh_identity_header}"],
        container=container,
    )
    if not result:
        return None
    try:
        data = json.loads(result)
        for st in data.get("data", []):
            if st.get("name") == source_type_name:
                return st.get("id")
    except json.JSONDecodeError:
        pass
    return None


def _get_application_type_id(
    namespace: str, pod: str, api_url: str, rh_identity_header: str,
    app_type_name: str = "/insights/platform/cost-management",
    container: str = "ingress",
) -> Optional[str]:
    result = exec_in_pod(
        namespace, pod,
        ["curl", "-s", f"{api_url}/application_types",
         "-H", "Content-Type: application/json",
         "-H", f"X-Rh-Identity: {rh_identity_header}"],
        container=container,
    )
    if not result:
        return None
    try:
        data = json.loads(result)
        for at in data.get("data", []):
            if at.get("name") == app_type_name:
                return at.get("id")
    except json.JSONDecodeError:
        pass
    return None


def register_source(
    namespace: str,
    pod: str,
    api_reads_url: str,
    api_writes_url: str,
    rh_identity_header: str,
    cluster_id: str,
    org_id: str,
    source_name: Optional[str] = None,
    bucket: str = DEFAULT_S3_BUCKET,
    container: str = "ingress",
    max_retries: int = 5,
    initial_retry_delay: int = 5,
) -> SourceRegistration:
    """Register a source in Koku Sources API."""
    source_type_id = _get_source_type_id(
        namespace, pod, api_reads_url, rh_identity_header, container=container
    )
    if not source_type_id:
        raise RuntimeError("Could not get OpenShift source type ID")

    app_type_id = _get_application_type_id(
        namespace, pod, api_reads_url, rh_identity_header, container=container
    )

    if not source_name:
        source_name = f"e2e-source-{cluster_id[-8:]}"

    source_payload = json.dumps({
        "name": source_name,
        "source_type_id": source_type_id,
        "source_ref": cluster_id,
    })

    retry_delay = initial_retry_delay
    source_id = None
    last_error = None

    for attempt in range(max_retries):
        if attempt > 0:
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)

        result = exec_in_pod(
            namespace, pod,
            ["curl", "-s", "-w", "\n__HTTP_CODE__:%{http_code}", "-X", "POST",
             f"{api_writes_url}/sources",
             "-H", "Content-Type: application/json",
             "-H", f"X-Rh-Identity: {rh_identity_header}",
             "-d", source_payload],
            container=container, timeout=120,
        )

        if not result:
            last_error = "exec_in_pod returned None"
            continue

        http_code = None
        if "__HTTP_CODE__:" in result:
            body, http_code = result.rsplit("__HTTP_CODE__:", 1)
            result = body.strip()
            http_code = http_code.strip()

        if http_code and http_code not in ("200", "201"):
            last_error = f"HTTP {http_code}: {result[:200]}"
            if http_code.startswith("5"):
                continue
            break

        try:
            source_data = json.loads(result)
            source_id = source_data.get("id")
            if source_id:
                break
            else:
                last_error = f"No 'id' in response: {result[:200]}"
        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON: {result[:200]} - {e}"

    if not source_id:
        raise RuntimeError(
            f"Source creation failed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )

    if app_type_id:
        app_payload = json.dumps({
            "source_id": source_id,
            "application_type_id": app_type_id,
            "extra": {"bucket": bucket, "cluster_id": cluster_id},
        })
        exec_in_pod(
            namespace, pod,
            ["curl", "-s", "-X", "POST", f"{api_writes_url}/applications",
             "-H", "Content-Type: application/json",
             "-H", f"X-Rh-Identity: {rh_identity_header}",
             "-d", app_payload],
            container=container,
        )

    return SourceRegistration(
        source_id=source_id, source_name=source_name,
        cluster_id=cluster_id, org_id=org_id,
    )


def wait_for_provider(
    namespace: str, db_pod: str, cluster_id: str,
    timeout: int = 300, interval: int = 10,
) -> bool:
    """Wait for provider to be created in Koku database."""
    def check_provider():
        result = execute_db_query(
            namespace, db_pod, "costonprem_koku", "koku_user",
            f"""
            SELECT p.uuid FROM api_provider p
            JOIN api_providerauthentication pa ON p.authentication_id = pa.id
            WHERE pa.credentials->>'cluster_id' = '{cluster_id}'
               OR p.additional_context->>'cluster_id' = '{cluster_id}'
            """
        )
        return result and result[0][0]

    return wait_for_condition(check_provider, timeout=timeout, interval=interval)


def wait_for_summary_tables(
    namespace: str, db_pod: str, cluster_id: str,
    timeout: int = 600, interval: int = 30,
) -> Optional[str]:
    """Wait for summary tables to be populated and return schema name."""
    found_schema = {"name": None}

    def check_summary():
        result = execute_db_query(
            namespace, db_pod, "costonprem_koku", "koku_user",
            f"""
            SELECT c.schema_name FROM reporting_common_costusagereportmanifest m
            JOIN api_provider p ON m.provider_id = p.uuid
            JOIN api_customer c ON p.customer_id = c.id
            WHERE m.cluster_id = '{cluster_id}' LIMIT 1
            """
        )
        if not result or not result[0][0]:
            return False

        schema = result[0][0].strip()
        result = execute_db_query(
            namespace, db_pod, "costonprem_koku", "koku_user",
            f"SELECT COUNT(*) FROM {schema}.reporting_ocpusagelineitem_daily_summary "
            f"WHERE cluster_id = '{cluster_id}'"
        )

        if result and int(result[0][0]) > 0:
            found_schema["name"] = schema
            return True
        return False

    if wait_for_condition(check_summary, timeout=timeout, interval=interval):
        return found_schema["name"]
    return None


def upload_with_retry(
    session: requests.Session,
    url: str,
    package_path: str,
    auth_header: Dict[str, str],
    max_retries: int = 3,
    retry_delay: int = 5,
) -> requests.Response:
    """Upload file with retry logic for transient errors."""
    last_error = None

    for attempt in range(max_retries):
        try:
            with open(package_path, "rb") as f:
                response = session.post(
                    url,
                    files={"file": ("cost-mgmt.tar.gz", f, UPLOAD_CONTENT_TYPE)},
                    headers=auth_header,
                    timeout=60,
                )

            if response.status_code in [200, 201, 202]:
                return response

            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                print(f"  Attempt {attempt + 1}/{max_retries} failed: {last_error}")
                time.sleep(retry_delay * (attempt + 1))
                continue

            return response

        except requests.exceptions.RequestException as e:
            last_error = str(e)
            print(f"  Attempt {attempt + 1}/{max_retries} failed: {last_error}")
            time.sleep(retry_delay * (attempt + 1))

    raise RuntimeError(f"Upload failed after {max_retries} attempts: {last_error}")
