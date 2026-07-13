"""Azure Blob Storage TTL cache for CatalogService."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONTAINER = "mcp-cache"


def sanitize_blob_key(key: str) -> str:
    """Sanitize cache keys into valid Azure Blob names."""
    text = str(key)
    text = text.replace(" ", "_")
    text = text.replace("(", "{")
    text = text.replace(")", "}")
    text = text.replace(":", "-")
    if len(text) > 1024:
        text = text[:1024]
    return text


class BlobStorageCache:
    """Best-effort persistent TTL cache backed by Azure Blob Storage.

    Authentication:
    - local: AZURE_STORAGE_CONNECTION_STRING
    - Azure: DefaultAzureCredential + AZURE_STORAGE_ACCOUNT_NAME

    Enabled when either credential env var is present. All failures are logged
    and swallowed so cache outages never break session requests.
    """

    def __init__(self, container_name: str | None = None) -> None:
        self._container_name = (
            container_name
            or os.environ.get("MCP_CACHE_CONTAINER")
            or DEFAULT_CONTAINER
        )
        self._client = None
        self._container = None
        self._enabled = False
        self._initialize()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _initialize(self) -> None:
        connection = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        account = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME")
        if not connection and not account:
            logger.info("BlobStorageCache disabled: no Azure storage credentials configured")
            return
        try:
            if connection:
                from azure.storage.blob import BlobServiceClient

                service = BlobServiceClient.from_connection_string(connection)
            else:
                from azure.identity import DefaultAzureCredential
                from azure.storage.blob import BlobServiceClient

                credential = DefaultAzureCredential()
                account_url = f"https://{account}.blob.core.windows.net"
                service = BlobServiceClient(account_url=account_url, credential=credential)

            container = service.get_container_client(self._container_name)
            try:
                container.create_container()
            except Exception:
                # Container may already exist; ignore create races/errors.
                pass
            self._client = service
            self._container = container
            self._enabled = True
            logger.info(
                "BlobStorageCache enabled for container %s", self._container_name
            )
        except Exception:
            logger.exception("BlobStorageCache initialization failed; continuing without Blob cache")
            self._client = None
            self._container = None
            self._enabled = False

    def get(self, key: str, ttl: float) -> Any | None:
        """Return payload if present and younger than ttl seconds; else miss."""
        if not self._enabled or self._container is None:
            return None
        blob_name = sanitize_blob_key(key)
        try:
            blob = self._container.get_blob_client(blob_name)
            if not blob.exists():
                return None
            raw = blob.download_blob().readall()
            entry = json.loads(raw.decode("utf-8"))
            created_at = float(entry.get("_created_at", 0))
            age = time.time() - created_at
            if age > float(ttl):
                try:
                    blob.delete_blob()
                except Exception:
                    logger.exception("Failed deleting expired blob %s", blob_name)
                return None
            return entry.get("payload")
        except Exception:
            logger.exception("BlobStorageCache get failed for key %s", blob_name)
            return None

    def set(self, key: str, payload: Any) -> None:
        """Store payload with _created_at timestamp. Best-effort."""
        if not self._enabled or self._container is None:
            return
        blob_name = sanitize_blob_key(key)
        try:
            entry = {"_created_at": time.time(), "payload": payload}
            data = json.dumps(entry, default=str).encode("utf-8")
            blob = self._container.get_blob_client(blob_name)
            blob.upload_blob(data, overwrite=True)
        except Exception:
            logger.exception("BlobStorageCache set failed for key %s", blob_name)
