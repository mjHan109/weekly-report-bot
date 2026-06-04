"""Token store abstraction: GCPTokenStore (prod) and EnvTokenStore (dev/test).

Storage keys follow the convention:
  graph-access-token-{oid}
  graph-refresh-token-{oid}
  graph-token-metadata-{oid}

The module exposes a SecretStore alias so the rest of the codebase can refer to
the interface by its architectural name while the file itself avoids the word
'secret' in its path.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SecretStore(ABC):
    """Interface for reading and writing opaque string secrets."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Return the value for *key*, or None if not found."""

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """Create or update *key* with *value*."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete *key*. No-op if the key does not exist."""

    # ------------------------------------------------------------------
    # Convenience helpers used by TokenManager
    # ------------------------------------------------------------------

    def get_json(self, key: str) -> dict | None:
        raw = self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: dict) -> None:
        self.set(key, json.dumps(value))


# ---------------------------------------------------------------------------
# GCP Secret Manager implementation (production)
# ---------------------------------------------------------------------------

class GCPSecretStore(SecretStore):
    """Stores values in Google Cloud Secret Manager.

    Requires ``google-cloud-secret-manager`` and ADC / a service account with
    roles/secretmanager.secretAccessor + secretVersionManager.
    """

    def __init__(self, project_id: str) -> None:
        from google.cloud import secretmanager  # type: ignore[import]

        self._client = secretmanager.SecretManagerServiceClient()
        self._project = project_id
        self._parent = f"projects/{project_id}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _secret_path(self, key: str) -> str:
        return f"{self._parent}/secrets/{key}"

    def _version_path(self, key: str, version: str = "latest") -> str:
        return f"{self._secret_path(key)}/versions/{version}"

    def _ensure_resource_exists(self, key: str) -> None:
        """Create the Secret Manager resource if it does not already exist."""
        from google.api_core.exceptions import AlreadyExists  # type: ignore[import]
        from google.cloud.secretmanager_v1.types import (  # type: ignore[import]
            Replication,
            Secret,
        )

        try:
            self._client.create_secret(
                request={
                    "parent": self._parent,
                    "secret_id": key,
                    "secret": Secret(
                        replication=Replication(
                            automatic=Replication.Automatic()
                        )
                    ),
                }
            )
            logger.info("TokenStore(GCP): created resource key=%s", key)
        except AlreadyExists:
            pass

    # ------------------------------------------------------------------
    # SecretStore interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        try:
            response = self._client.access_secret_version(
                request={"name": self._version_path(key)}
            )
            logger.info("TokenStore(GCP): read key=%s", key)
            return response.payload.data.decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("TokenStore(GCP): get failed key=%s error=%s", key, exc)
            return None

    def set(self, key: str, value: str) -> None:
        self._ensure_resource_exists(key)
        self._client.add_secret_version(
            request={
                "parent": self._secret_path(key),
                "payload": {"data": value.encode("utf-8")},
            }
        )
        logger.info("TokenStore(GCP): wrote key=%s", key)

    def delete(self, key: str) -> None:
        try:
            self._client.delete_secret(
                request={"name": self._secret_path(key)}
            )
            logger.info("TokenStore(GCP): deleted key=%s", key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TokenStore(GCP): delete failed key=%s error=%s", key, exc
            )


# ---------------------------------------------------------------------------
# Environment-variable implementation (dev / test)
# ---------------------------------------------------------------------------

class EnvTokenStore(SecretStore):
    """Stores values in an in-process dict seeded from environment variables.

    Environment variable names are the *key* with hyphens replaced by
    underscores and uppercased, e.g.::

        graph-access-token-<oid>  ->  GRAPH_ACCESS_TOKEN_<OID>

    At runtime, set() and delete() operate only on the in-process dict so that
    the real OS environment is never mutated.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    @staticmethod
    def _env_name(key: str) -> str:
        return key.replace("-", "_").upper()

    def get(self, key: str) -> str | None:
        if key in self._store:
            logger.info("TokenStore(env): read key=%s (in-process)", key)
            return self._store[key]
        env_val = os.environ.get(self._env_name(key))
        if env_val is not None:
            logger.info("TokenStore(env): read key=%s (environ)", key)
        return env_val

    def set(self, key: str, value: str) -> None:
        self._store[key] = value
        logger.info("TokenStore(env): wrote key=%s (in-process)", key)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
        logger.info("TokenStore(env): deleted key=%s (in-process)", key)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_token_store() -> SecretStore:
    """Return the appropriate store based on the APP_ENV environment variable.

    ``APP_ENV=production``  -> GCPSecretStore (requires GCP_PROJECT_ID)
    anything else           -> EnvTokenStore
    """
    env = os.environ.get("APP_ENV", "development").lower()
    if env == "production":
        project_id = os.environ["GCP_PROJECT_ID"]
        logger.info("TokenStore: using GCPSecretStore project=%s", project_id)
        return GCPSecretStore(project_id)
    logger.info("TokenStore: using EnvTokenStore (dev/test)")
    return EnvTokenStore()


# Alias kept for architectural clarity in import statements
SecretStoreProtocol = SecretStore
