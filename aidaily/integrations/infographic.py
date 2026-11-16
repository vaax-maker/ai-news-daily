"""Client for the local infographic service."""

from __future__ import annotations

import json
import os
from pathlib import Path

from aidaily import config
from aidaily.integrations.http import request_bytes


class InfographicClient:
    def __init__(self, url: str | None = None, token_path: str | None = None):
        self.url = url or config.INFOGRAPHIC_API_URL
        self.token_path = Path(token_path or os.environ.get(
            "INFOGRAPHIC_API_TOKEN_FILE", "~/nlm-infographic/.api_token"
        )).expanduser()

    def generate(self, payload: dict, timeout: int = 1200) -> tuple[bytes, dict]:
        token = self.token_path.read_text(encoding="utf-8").strip()
        return request_bytes(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-API-Token": token},
            timeout=timeout,
        )
