"""Cluster and authentication configuration dataclasses."""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class ClusterConfig:
    """Configuration for the target cluster."""

    namespace: str
    helm_release_name: str
    keycloak_namespace: str
    platform: str = "openshift"
    project_root: str = field(
        default_factory=lambda: os.path.dirname(os.path.dirname(__file__))
    )


@dataclass
class KeycloakConfig:
    """Keycloak authentication configuration."""

    url: str
    client_id: str
    client_secret: str
    realm: str = "kubernetes"

    @property
    def token_url(self) -> str:
        """Get the token endpoint URL."""
        return f"{self.url}/realms/{self.realm}/protocol/openid-connect/token"


@dataclass
class JWTToken:
    """JWT token with expiry tracking."""

    access_token: str
    expires_at: datetime
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def authorization_header(self) -> dict:
        return {"Authorization": f"{self.token_type} {self.access_token}"}


def obtain_jwt_token(keycloak_config: KeycloakConfig) -> JWTToken:
    """Obtain a JWT token from Keycloak using client credentials flow."""
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
        raise RuntimeError(
            f"Failed to obtain JWT token: {response.status_code} - {response.text}"
        )

    token_data = response.json()
    expires_in = token_data.get("expires_in", 300)

    return JWTToken(
        access_token=token_data["access_token"],
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )
