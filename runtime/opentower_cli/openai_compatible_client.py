from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from .anthropic_client import AnthropicMessageResponse, ProviderError


DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 90.0


class OpenAICompatibleError(ProviderError):
    """Raised when an OpenAI-compatible API request cannot be completed."""


def normalize_base_url(base_url: str | None = None) -> str:
    raw = (
        base_url
        or os.environ.get("OPENTOWER_OPENAI_BASE_URL", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or DEFAULT_BASE_URL
    )
    normalized = raw.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def _request_timeout_seconds(timeout_seconds: float | None = None) -> float:
    if timeout_seconds is not None:
        return max(float(timeout_seconds), 1.0)
    configured = (
        os.environ.get("OPENTOWER_OPENAI_REQUEST_TIMEOUT_SECONDS", "").strip()
        or os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS", "").strip()
    )
    if not configured:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        return max(float(configured), 1.0)
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS


def _coerce_usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        return {}
    payload: dict[str, Any] = {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if isinstance(prompt_tokens, int):
        payload["input_tokens"] = prompt_tokens
    if isinstance(completion_tokens, int):
        payload["output_tokens"] = completion_tokens
    if isinstance(total_tokens, int):
        payload["total_tokens"] = total_tokens
    return payload


def _choice_text(choice: dict[str, Any]) -> str:
    message = choice.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for row in content:
            if not isinstance(row, dict):
                continue
            if row.get("type") == "text":
                text = row.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


@dataclass(frozen=True)
class OpenAICompatibleStatus:
    api_url: str
    configured_model: str
    api_key_present: bool
    execute_ready: bool
    status_detail: str | None = None


def provider_status(
    *,
    api_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> OpenAICompatibleStatus:
    resolved_api_url = normalize_base_url(api_url)
    resolved_model = (
        model
        or os.environ.get("OPENTOWER_OPENAI_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or DEFAULT_MODEL
    )
    resolved_api_key = (
        api_key
        or os.environ.get("OPENTOWER_OPENAI_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    ready = bool(resolved_api_url and resolved_model and resolved_api_key)
    detail = None if ready else "Missing OPENAI_API_KEY-compatible credentials."
    return OpenAICompatibleStatus(
        api_url=resolved_api_url,
        configured_model=resolved_model,
        api_key_present=bool(resolved_api_key),
        execute_ready=ready,
        status_detail=detail,
    )


class OpenAICompatibleMessagesClient:
    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_url = normalize_base_url(api_url)
        self.api_key = (
            api_key
            or os.environ.get("OPENTOWER_OPENAI_API_KEY", "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
        )
        self.timeout_seconds = _request_timeout_seconds(timeout_seconds)
        if not self.api_key:
            raise OpenAICompatibleError("Missing OPENAI_API_KEY")

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
            or os.environ.get("OPENTOWER_OPENAI_MODEL", "").strip()
            or os.environ.get("OPENAI_MODEL", "").strip()
            or DEFAULT_MODEL
        )
        messages = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_text})
        payload = {
            "model": resolved_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        req = request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise OpenAICompatibleError(f"OpenAI-compatible API HTTP {exc.code}: {raw}") from exc
        except error.URLError as exc:
            raise OpenAICompatibleError(f"OpenAI-compatible API connection error: {exc.reason}") from exc

        choices = data.get("choices", [])
        choice = choices[0] if isinstance(choices, list) and choices else {}
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return AnthropicMessageResponse(
            id=str(data.get("id", "")) or f"openai-compatible-{resolved_model}",
            model=str(data.get("model", resolved_model)),
            text=_choice_text(choice if isinstance(choice, dict) else {}),
            stop_reason=str(finish_reason) if finish_reason else None,
            usage=_coerce_usage(data),
            raw=data,
        )
