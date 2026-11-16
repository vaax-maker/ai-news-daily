"""Firestore REST client used by the AI News source adapter."""

from __future__ import annotations

import os

from aidaily import config
from aidaily.integrations.http import request_json


class FirestoreClient:
    def __init__(self, project: str, api_key: str | None = None, timeout: int = 25):
        self.project = project
        self.api_key = (api_key or os.environ.get("FIRESTORE_API_KEY", "")).strip()
        self.timeout = timeout

    @property
    def run_query_url(self) -> str:
        base = config.FIRESTORE_API_URL.format(project=self.project)
        return f"{base}?key={self.api_key}" if self.api_key else base

    def run_query(self, structured_query: dict):
        return request_json(
            self.run_query_url,
            payload={"structuredQuery": structured_query},
            timeout=self.timeout,
        )
