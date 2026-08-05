"""xbot(Hermes) LLM 백엔드 클라이언트 — 스테이트리스·격리 (docker exec 경로).

맥미니 로컬 전용: hermes-xbot 컨테이너가 떠 있어야 함(GitHub Actions에서는 불가).
외부 API 키 불필요(컨테이너 내장 OpenRouter 크레덴셜 사용).

주의:
- `--ignore-user-config`는 config.yaml의 openrouter 프로바이더 매핑을 없애 codex로
  폴백 → google/openai 모델 400. 절대 쓰지 말 것. `--ignore-rules`만 사용.
- stdout = 응답 본문, stderr = session_id/경고.
"""
from __future__ import annotations
import subprocess
import re

CONTAINER = "hermes-xbot"
HERMES_BIN = "/opt/hermes/.venv/bin/hermes"
_BANNER = re.compile(r'^\s*(⚠|↻|ℹ️|ℹ|Resumed|↻ Resumed|\[hermes\])')


def _strip_banners(text: str) -> str:
    lines = text.splitlines()
    while lines and (_BANNER.match(lines[0]) or lines[0].strip() == ""):
        lines.pop(0)
    return "\n".join(lines).strip()


def container_up() -> bool:
    """hermes-xbot 컨테이너가 healthy/up 인지."""
    try:
        p = subprocess.run(
            ["docker", "ps", "--filter", f"name={CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=15)
        return CONTAINER in p.stdout
    except Exception:
        return False


def complete(system: str, user: str,
             model: str = "openai/gpt-5.6-luna",
             timeout: int = 180) -> str:
    """1회 스테이트리스 텍스트 완성. 실패 시 RuntimeError."""
    prompt = f"[System] {system}\n\n[User] {user}"
    cmd = ["docker", "exec", "-u", "hermes", CONTAINER, HERMES_BIN, "chat", "-Q",
           "--ignore-rules", "--source", "tool", "--yolo",
           "-m", model, "-q", prompt]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"hermes rc={p.returncode}: {p.stderr[:400]}")
    return _strip_banners(p.stdout)
