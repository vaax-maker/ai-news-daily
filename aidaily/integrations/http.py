"""Small stdlib HTTP transport shared by external API clients."""

from __future__ import annotations

import json
import urllib.request


def request_bytes(url: str, *, data: bytes | None = None, headers: dict | None = None,
                  timeout: int = 30) -> tuple[bytes, dict]:
    request = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), dict(response.headers)


def request_text(url: str, *, data: bytes | None = None, headers: dict | None = None,
                 timeout: int = 30, encoding: str = "utf-8") -> str:
    raw, _ = request_bytes(url, data=data, headers=headers, timeout=timeout)
    return raw.decode(encoding, "replace")


def request_json(url: str, *, payload=None, data: bytes | None = None,
                 headers: dict | None = None, timeout: int = 30):
    if payload is not None:
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", **(headers or {})}
    return json.loads(request_text(url, data=data, headers=headers, timeout=timeout))
