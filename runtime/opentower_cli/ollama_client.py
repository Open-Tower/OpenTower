from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit, urlunsplit

from .anthropic_client import AnthropicMessageResponse, ProviderError


DEFAULT_MODEL = "qwen3:8b"
DEFAULT_BASE_URL = "http://localhost:11434/api"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 90.0


class OllamaError(ProviderError):
    """Raised when an Ollama API request cannot be completed."""


def normalize_base_url(base_url: str | None = None) -> str:
    raw = (
        base_url
        or os.environ.get("OPENTOWER_OLLAMA_BASE_URL", "").strip()
        or os.environ.get("OLLAMA_BASE_URL", "").strip()
        or DEFAULT_BASE_URL
    )
    normalized = raw.rstrip("/")
    parsed = urlsplit(normalized)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3] + "/api"
    elif "/api/" in path:
        path = path.split("/api/", 1)[0] + "/api"
    elif not path.endswith("/api"):
        path = f"{path}/api" if path else "/api"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _endpoint_url(base_url: str, path: str) -> str:
    return f"{normalize_base_url(base_url)}/{path.lstrip('/')}"


def _request_timeout_seconds(timeout_seconds: float | None = None) -> float:
    if timeout_seconds is not None:
        return max(float(timeout_seconds), 1.0)
    configured = (
        os.environ.get("OPENTOWER_OLLAMA_REQUEST_TIMEOUT_SECONDS", "").strip()
        or os.environ.get("OLLAMA_REQUEST_TIMEOUT_SECONDS", "").strip()
    )
    if not configured:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        return max(float(configured), 1.0)
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS


def _thinking_enabled() -> bool:
    raw = (
        os.environ.get("OPENTOWER_OLLAMA_THINK", "").strip()
        or os.environ.get("OLLAMA_THINK", "").strip()
    )
    if not raw:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def _coerce_usage(data: dict[str, Any]) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")
    if isinstance(prompt_tokens, int):
        usage["input_tokens"] = prompt_tokens
    if isinstance(completion_tokens, int):
        usage["output_tokens"] = completion_tokens
    for field in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        value = data.get(field)
        if isinstance(value, int):
            usage[field] = value
    return usage


@dataclass(frozen=True)
class OllamaModelStatus:
    api_url: str
    configured_model: str
    available_models: list[str]
    reachable: bool
    model_available: bool
    error_message: str | None = None


def inspect_local_model(
    *,
    base_url: str | None = None,
    model: str | None = None,
    timeout: float = 2.0,
    api_key: str | None = None,
) -> OllamaModelStatus:
    resolved_base_url = normalize_base_url(base_url)
    resolved_model = (
        model
        or os.environ.get("OPENTOWER_OLLAMA_MODEL", "").strip()
        or os.environ.get("OLLAMA_MODEL", "").strip()
        or DEFAULT_MODEL
    )
    headers = {"content-type": "application/json"}
    resolved_api_key = api_key or os.environ.get("OLLAMA_API_KEY", "").strip()
    if resolved_api_key:
        headers["authorization"] = f"Bearer {resolved_api_key}"
    req = request.Request(
        _endpoint_url(resolved_base_url, "tags"),
        headers=headers,
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return OllamaModelStatus(
            api_url=resolved_base_url,
            configured_model=resolved_model,
            available_models=[],
            reachable=False,
            model_available=False,
            error_message=f"Ollama API HTTP {exc.code}: {raw}",
        )
    except error.URLError as exc:
        return OllamaModelStatus(
            api_url=resolved_base_url,
            configured_model=resolved_model,
            available_models=[],
            reachable=False,
            model_available=False,
            error_message=f"Ollama API connection error: {exc.reason}",
        )
    models = data.get("models", [])
    available = [
        str(row.get("name", "")).strip()
        for row in models
        if isinstance(row, dict) and str(row.get("name", "")).strip()
    ]
    model_available = resolved_model in available
    return OllamaModelStatus(
        api_url=resolved_base_url,
        configured_model=resolved_model,
        available_models=available,
        reachable=True,
        model_available=model_available,
        error_message=None if model_available else f"Configured model '{resolved_model}' is not pulled in Ollama.",
    )


class OllamaMessagesClient:
    provider_name = "ollama"

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_url = normalize_base_url(api_url)
        self.api_key = api_key or os.environ.get("OLLAMA_API_KEY", "").strip()
        self.timeout_seconds = _request_timeout_seconds(timeout_seconds)

    def create_message(
        self,
        *,
        system: str,
        user_text: str,
        model: str | None = None,
        max_tokens: int = 1400,
        temperature: float = 0.2,
    ) -> AnthropicMessageResponse:
        resolved_model = (
            model
            or os.environ.get("OPENTOWER_OLLAMA_MODEL", "").strip()
            or os.environ.get("OLLAMA_MODEL", "").strip()
            or DEFAULT_MODEL
        )
        messages = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_text})
        payload = {
            "model": resolved_model,
            "stream": False,
            "think": _thinking_enabled(),
            "messages": messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        req = request.Request(
            _endpoint_url(self.api_url, "chat"),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama API HTTP {exc.code}: {raw}") from exc
        except error.URLError as exc:
            raise OllamaError(f"Ollama API connection error: {exc.reason}") from exc

        message = data.get("message", {})
        text = ""
        if isinstance(message, dict):
            text = str(message.get("content", "")).strip()
        return AnthropicMessageResponse(
            id=str(data.get("created_at", "")) or f"ollama-{resolved_model}",
            model=str(data.get("model", resolved_model)),
            text=text,
            stop_reason="end_turn" if bool(data.get("done", False)) else None,
            usage=_coerce_usage(data),
            raw=data,
        )
