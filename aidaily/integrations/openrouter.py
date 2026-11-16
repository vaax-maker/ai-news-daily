#!/usr/bin/env python3
"""AI Daily text entry point: fleet Qwen first, journaled OpenRouter fallback.

The positional caller interface and JSON extraction remain compatible. ``retries``
is accepted for compatibility, but uncertain external POSTs are never retried.
Request identities are content-derived unless an optional business request_id is
supplied. Incompatible business IDs are journaled with a stable fleet-safe ID.
Receipts (including private completions) stay in the project's runtime data root.
"""
import contextvars
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import re
import ssl
import sys
import time
import urllib.error
from pathlib import Path

from aidaily import config
from aidaily.integrations.http import request_json

URL = config.OPENROUTER_API_URL
PROJECT = config.OPENROUTER_APP_TITLE
_USAGE = contextvars.ContextVar("aidaily_llm_usage", default=None)
_FLEET = None


class RoutingBlocked(RuntimeError):
    """Stop generation; authentication, quality or unresolved submission needs review."""


class CompletionPending(RoutingBlocked):
    def __init__(self, request_id):
        self.request_id = request_id
        super().__init__(f"LLM request pending; resume the same request: {request_id}")


def last_usage():
    """Metadata for this context's last successful completion (no prompt or key)."""
    return _USAGE.get()


def _fleet_module():
    global _FLEET
    if _FLEET is None:
        path = Path.home() / "abot-inference/inference_client.py"
        spec = importlib.util.spec_from_file_location("aidaily_fleet_client", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _FLEET = module
    return _FLEET


def _new_client(state):
    fleet = _fleet_module()
    # Resolve the common registry; use only this host's installed authentication.
    client = fleet.InferenceClient(PROJECT, state_dir=state / "fleet")
    client.headers.update({"X-Title": PROJECT,
                           "HTTP-Referer": config.OPENROUTER_APP_REFERER})
    original_health = client.health

    def health():
        try:
            return original_health()
        except urllib.error.URLError as exc:
            # The shared client classifies certificate failures. Also guard other
            # TLS errors so they can never be mistaken for offline availability.
            if isinstance(exc.reason, ssl.SSLError):
                raise RoutingBlocked("Fleet TLS validation failed") from None
            raise
    client.health = health
    return client


def _save(path, receipt):
    temporary = path.with_suffix(".new")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(receipt, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _text(result):
    try:
        text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RoutingBlocked("LLM completion shape needs review") from None
    if not isinstance(text, str) or not text.strip():
        raise RoutingBlocked("LLM completion content needs review")
    return text


def _key_from_file(path):
    try:
        for line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
            line = line.strip()
            name, sep, value = line.partition("=")
            if sep and name.strip() == "OPENROUTER_API_KEY":
                return value.strip().strip('"').strip("'")
    except (OSError, UnicodeError):
        pass
    return ""


def _load_key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if k:
        return k
    configured = os.environ.get("AIDAILY_ENV_FILE", "").strip()
    paths = [configured] if configured else ["~/.config/aidaily/.env"]
    for path in paths:
        if path and (k := _key_from_file(path)):
            return k
    return ""


KEY = _load_key()

LOCAL_PENDING_MAX_SECONDS = int(os.environ.get("AIDAILY_LOCAL_PENDING_MAX_SECONDS", "600"))

# 기본 모델 + 폴백 사슬(앞에서부터). 뉴스 파이프라인이 매일 쓰는 gpt-6-luna가 1순위.
DEFAULT_MODELS = [m.strip() for m in os.environ.get(
    "LLM_MODELS",
    "openai/gpt-6-luna,google/gemini-3.1-flash-lite"
).split(",") if m.strip()]


def complete(system, user, models=None, temperature=0.2, timeout=90, retries=2,
             max_tokens=None, *, request_id=None, allow_external=True):
    """system+user -> text, preserving full input and paid provider key lookup.

    Busy or uncertain work raises CompletionPending. Call again with the same
    input/ID to resume. Cached successful calls do not submit or publish again.
    Known offline/unsupported/engine failures may use the existing paid route.
    """
    _USAGE.set(None)
    if not isinstance(system, str) or not isinstance(user, str):
        raise TypeError("system and user must be text")
    # Invalid inputs are caller errors, not paid-eligible capability misses.
    # Validate before opening state, loading the fleet SDK or any transport.
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            raise TypeError("max_tokens must be a positive integer or None")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise TypeError("temperature must be a finite number")
    if not 0 <= temperature <= 2 or not math.isfinite(temperature):
        raise ValueError("temperature must be finite and between 0 and 2")
    if request_id is not None and not isinstance(request_id, str):
        raise TypeError("request_id must be a business ID string or None")
    selected = [m.strip() for m in (models or DEFAULT_MODELS) if m.strip()]
    identity = {"project": PROJECT, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}],
        "models": selected, "temperature": temperature, "max_tokens": max_tokens}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    request_id = "text-" + fingerprint if request_id is None else request_id
    state = Path(os.environ.get("AIDAILY_LLM_STATE_DIR", str(config.DATA_ROOT / "llm"))).expanduser()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = hashlib.sha256((PROJECT + "\0" + request_id).encode()).hexdigest()
    path = state / (filename + ".json")
    with (state / (filename + ".lock")).open("a") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        receipt = json.loads(path.read_text()) if path.exists() else {}
        if receipt and receipt["fingerprint"] != fingerprint:
            raise ValueError("Request ID already belongs to different input")

        def save(status, **fields):
            receipt.update(fingerprint=fingerprint, request_id=request_id,
                           project=PROJECT, state=status, **fields)
            _save(path, receipt)

        if receipt.get("state") == "succeeded":
            text = _text(receipt["result"])
            _USAGE.set(receipt["metadata"])
            return text
        if receipt.get("state") in ("external_submitting", "external_pending", "review", "blocked"):
            raise CompletionPending(request_id)
        # Preserve every persisted mapping and all existing valid fleet IDs.
        # A legacy incompatible receipt may represent accepted/uncertain work;
        # never mint an alternate ID for it, even if it appears blocked/rejected.
        fleet_request_id = receipt.get("fleet_request_id", request_id)
        if "fleet_request_id" in receipt:
            if not isinstance(fleet_request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", fleet_request_id):
                raise CompletionPending(request_id)
        elif not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", request_id):
            legacy_fleet = state / "fleet" / (filename + ".json")
            # The former adapter treated an explicitly empty ID as automatic.
            legacy_empty = state / (hashlib.sha256(
                (PROJECT + "\0text-" + fingerprint).encode()).hexdigest() + ".json")
            if receipt or legacy_fleet.exists() or (request_id == "" and legacy_empty.exists()):
                raise CompletionPending(request_id)
            fleet_request_id = "business-" + hashlib.sha256(
                (PROJECT + "\0" + request_id).encode()).hexdigest()
            # The project business ID remains the journal key. Persist mapping
            # before health/submission or fallback, so crash/resume uses this ID.
            save("prepared", fleet_request_id=fleet_request_id)
        started = time.monotonic()

        def external(payload, routing):
            if not allow_external:raise RoutingBlocked('External replacement is disabled for this local quality operation')
            # Called only by common client after confirmed pre-submit inability
            # or engine failure, or our explicit capability check below.
            key = KEY or _load_key()
            if not key:
                raise RoutingBlocked("OPENROUTER_API_KEY unavailable for fallback")
            if not selected:
                raise RoutingBlocked("No external model configured")
            for model in selected:
                body = {"model": model, "temperature": temperature,
                        "messages": identity["messages"]}
                if max_tokens:
                    body["max_tokens"] = max_tokens
                # Persist before each POST. Only an explicit endpoint/model 404
                # rejection permits the next model; uncertain work never does.
                save("external_submitting", provider="openrouter", model=model,
                     fallback_reason=routing["reason"])
                try:
                    result = request_json(URL, data=json.dumps(body).encode(), headers={
                        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                        "HTTP-Referer": config.OPENROUTER_APP_REFERER, "X-Title": PROJECT},
                        timeout=timeout)
                except urllib.error.HTTPError as exc:
                    if exc.code == 404:
                        save("external_rejected", rejection_code=404)
                        continue
                    save("external_pending", rejection_code=exc.code)
                    raise CompletionPending(request_id) from None
                except Exception:
                    save("external_pending")
                    raise CompletionPending(request_id) from None
                save("external_pending", provider_job_id=result.get("id") if isinstance(result, dict) else None)
                return result
            save("blocked", error_type="ExternalModelsRejected")
            raise RoutingBlocked("External models explicitly rejected")

        # Never truncate long transcripts to force local eligibility. The existing
        # paid path receives the original input when outside the common contract.
        local_tokens = max_tokens if max_tokens is not None else 8192
        supported = len(system) + len(user) <= 16000 and local_tokens <= 12288
        fleet = None
        try:
            if not supported:
                # Once a local attempt exists, a changed contract/installation
                # must not turn unresolved local work into a paid replacement.
                if receipt.get("state") == "local_pending":
                    raise CompletionPending(request_id)
                result = external(None, {"reason": "local_request_unsupported"})
            elif receipt.get("state") == "local_abandoned" or (
                    receipt.get("state") == "local_pending" and time.time() - receipt.get(
                        "local_pending_since", path.stat().st_mtime) > LOCAL_PENDING_MAX_SECONDS):
                # User-approved rule (2026-11-08): a local job pending beyond the
                # limit is abandoned (its result is never used) and replaced once.
                save("local_abandoned", local_abandoned_at=time.time())
                result = external(None, {"reason": "local_pending_timeout"})
            else:
                fleet = _fleet_module()
                client = _new_client(state)
                save("local_pending", local_pending_since=receipt.get(
                    "local_pending_since", path.stat().st_mtime if path.exists() else time.time()))
                result = client.chat(identity["messages"], request_id=fleet_request_id,
                                     max_tokens=local_tokens, temperature=temperature,
                                     fallback=external, max_wait=timeout)
        except RoutingBlocked:
            raise
        except Exception as exc:
            if fleet is not None and isinstance(exc, (fleet.LocalBusy, fleet.SubmissionPending)):
                raise CompletionPending(request_id) from None
            # Missing auth/registry, HTTP authentication, TLS and unclassified
            # failures are review conditions, never reasons for paid replacement.
            save("blocked", error_type=type(exc).__name__)
            raise RoutingBlocked(f"Fleet routing blocked: {type(exc).__name__}") from None
        try:
            text = _text(result)
        except RoutingBlocked:
            save("review")
            raise
        provider = "openrouter" if receipt.get("provider") == "openrouter" else "local:qwen3.8"
        usage = result.get("usage") or {}
        metadata = {"request_id": request_id, "provider": provider,
                    "model": result.get("model") or (receipt.get("model") if provider == "openrouter" else "qwen3.8-27b"),
                    "cost_usd": 0.0 if provider == "local:qwen3.8" else usage.get("cost"),
                    "usage": usage, "latency_seconds": round(time.monotonic() - started, 3)}
        if fleet_request_id != request_id:
            metadata["fleet_request_id"] = fleet_request_id
        save("succeeded", result=result, metadata=metadata)
        _USAGE.set(metadata)
        print(f"[llm] ok provider={provider} model={metadata['model']}", file=sys.stderr)
        return text


def _repair_local_delimiters(candidate):
    """Repair at most two closing delimiters, preserving every content token.

    Qwen occasionally closes a final string array with ``}`` instead of ``]}``.
    Only insert an array close immediately before its enclosing object close,
    and remove a resulting surplus final array close. Never repair truncation,
    strings, missing keys/values or any other syntax/semantic quality problem.
    """
    stack, output = [], []
    quoted = escaped = False
    changes = 0
    for index, char in enumerate(candidate):
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "[{":
            stack.append(char)
        elif char in "]}":
            expected = "[" if char == "]" else "{"
            if char == "}" and len(stack) >= 2 and stack[-2:] == ["{", "["]:
                output.append("]")
                stack.pop()
                changes += 1
            if not stack:
                if char == "]" and not candidate[index + 1:].strip():
                    changes += 1
                    continue
                return None
            if stack.pop() != expected:
                return None
        output.append(char)
    if stack or quoted or not 1 <= changes <= 2:
        return None
    try:
        return json.loads("".join(output))
    except (ValueError, TypeError):
        return None


def complete_json(system, user, **kw):
    """Extract JSON; limited local delimiter repair never sends another request."""
    txt = complete(system, user, **kw)
    txt = re.sub(r"```(json)?", "", txt).replace("```", "").strip()
    m = re.search(r"[\[{].*[\]}]", txt, re.S)
    if not m:
        return None
    candidate = m.group(0)
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        if (last_usage() or {}).get("provider") != "local:qwen3.8":
            return None
        repaired = _repair_local_delimiters(candidate)
        if repaired is not None:
            _USAGE.set({**last_usage(), "json_delimiter_repaired": True})
        return repaired
