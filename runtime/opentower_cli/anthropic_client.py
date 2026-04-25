from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ProviderError(RuntimeError):
    """Raised when a model provider request cannot be completed."""


class AnthropicError(ProviderError):
    """Raised when an Anthropic API request cannot be completed."""


def normalize_api_url(api_url: str | None) -> str:
    raw = str(api_url or API_URL).strip() or API_URL
    normalized = raw.rstrip("/")
    if normalized.endswith("/messages"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + "/messages"
    return normalized + "/v1/messages"


@dataclass
class AnthropicMessageResponse:
    id: str
    model: str
    text: str
    stop_reason: str | None
    usage: dict[str, Any]
    raw: dict[str, Any]


def _text_from_blocks(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(part for part in parts if part).strip()


class AnthropicMessagesClient:
    provider_name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str = API_URL,
        api_version: str = API_VERSION,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("OPENTOWER_ANTHROPIC_API_KEY", "").strip()
            or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        )
        resolved_api_url = (
            os.environ.get("OPENTOWER_ANTHROPIC_API_URL", "").strip()
            or os.environ.get("ANTHROPIC_API_URL", "").strip()
            or api_url
        )
        self.api_url = normalize_api_url(resolved_api_url)
        self.api_version = (
            os.environ.get("OPENTOWER_ANTHROPIC_API_VERSION", "").strip()
            or os.environ.get("ANTHROPIC_API_VERSION", "").strip()
            or api_version
        )
        if not self.api_key:
            raise AnthropicError("Missing ANTHROPIC_API_KEY")

    def create_message(
        self,
        *,
        system: str,
        user_text: str,
        model: str | None = None,
        max_tokens: int = 1400,
        temperature: float = 0.2,
    ) -> AnthropicMessageResponse:
        payload = {
            "model": model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user_text}],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.api_url,
            data=body,
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise AnthropicError(f"Anthropic API HTTP {exc.code}: {raw}") from exc
        except error.URLError as exc:
            raise AnthropicError(f"Anthropic API connection error: {exc.reason}") from exc

        text = _text_from_blocks(data.get("content", []))
        return AnthropicMessageResponse(
            id=str(data.get("id", "")),
            model=str(data.get("model", payload["model"])),
            text=text,
            stop_reason=data.get("stop_reason"),
            usage=data.get("usage", {}),
            raw=data,
        )
