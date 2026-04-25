from __future__ import annotations

import os
from dataclasses import dataclass

from .anthropic_client import API_URL as ANTHROPIC_API_URL
from .anthropic_client import API_VERSION as ANTHROPIC_API_VERSION
from .anthropic_client import DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL
from .anthropic_client import normalize_api_url as normalize_anthropic_api_url
from .ollama_client import DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL
from .ollama_client import inspect_local_model, normalize_base_url as normalize_ollama_base_url
from .openai_compatible_client import DEFAULT_MODEL as OPENAI_COMPATIBLE_DEFAULT_MODEL
from .openai_compatible_client import normalize_base_url as normalize_openai_compatible_base_url
from .openai_compatible_client import provider_status as openai_compatible_raw_status


DEFAULT_PROVIDER = "anthropic"


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    api_url: str
    api_version: str
    api_key_present: bool
    configured_model: str
    configured_opus_model: str
    execute_ready: bool
    model_available: bool | None = None
    available_models: list[str] | None = None
    status_detail: str | None = None


def normalize_provider_name(configured: str | None = None) -> str:
    raw = (
        configured
        if configured is not None
        else os.environ.get("OPENTOWER_MODEL_PROVIDER", DEFAULT_PROVIDER)
    )
    configured_text = str(raw).strip().lower() or DEFAULT_PROVIDER
    aliases = {
        "anthropic": "anthropic",
        "claude": "anthropic",
        "ollama": "ollama",
        "local": "ollama",
        "openai": "openai-compatible",
        "openai-compatible": "openai-compatible",
        "compatible": "openai-compatible",
        "openrouter": "openai-compatible",
        "siliconflow": "openai-compatible",
    }
    provider = aliases.get(configured_text)
    if provider is None:
        raise ValueError(f"Unsupported OPENTOWER_MODEL_PROVIDER: {configured_text}")
    return provider


def active_provider_name() -> str:
    return normalize_provider_name()


def anthropic_provider_status() -> ProviderStatus:
    api_key = os.environ.get("OPENTOWER_ANTHROPIC_API_KEY", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    api_url = os.environ.get("OPENTOWER_ANTHROPIC_API_URL", "").strip() or os.environ.get("ANTHROPIC_API_URL", "").strip()
    configured_model = os.environ.get("OPENTOWER_CLAUDE_MODEL", "").strip() or os.environ.get("ANTHROPIC_MODEL", "").strip()
    configured_opus_model = os.environ.get("OPENTOWER_CLAUDE_OPUS_MODEL", "").strip()
    return ProviderStatus(
        provider="anthropic",
        api_url=normalize_anthropic_api_url(api_url or ANTHROPIC_API_URL),
        api_version=ANTHROPIC_API_VERSION,
        api_key_present=bool(api_key),
        configured_model=configured_model or ANTHROPIC_DEFAULT_MODEL,
        configured_opus_model=configured_opus_model or "claude-opus-4-1-20250805",
        execute_ready=bool(api_key),
        model_available=None,
        status_detail=None if api_key else "Missing ANTHROPIC_API_KEY.",
    )


def ollama_provider_status() -> ProviderStatus:
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    model_status = inspect_local_model(api_key=api_key or None)
    return ProviderStatus(
        provider="ollama",
        api_url=model_status.api_url,
        api_version="local",
        api_key_present=bool(api_key),
        configured_model=model_status.configured_model or OLLAMA_DEFAULT_MODEL,
        configured_opus_model="",
        execute_ready=model_status.reachable and model_status.model_available,
        model_available=model_status.model_available,
        available_models=model_status.available_models,
        status_detail=model_status.error_message,
    )


def openai_compatible_provider_status() -> ProviderStatus:
    status = openai_compatible_raw_status()
    return ProviderStatus(
        provider="openai-compatible",
        api_url=status.api_url or normalize_openai_compatible_base_url(),
        api_version="chat-completions",
        api_key_present=status.api_key_present,
        configured_model=status.configured_model or OPENAI_COMPATIBLE_DEFAULT_MODEL,
        configured_opus_model="",
        execute_ready=status.execute_ready,
        model_available=None,
        available_models=None,
        status_detail=status.status_detail,
    )


def provider_status() -> ProviderStatus:
    provider = active_provider_name()
    if provider == "anthropic":
        return anthropic_provider_status()
    if provider == "openai-compatible":
        return openai_compatible_provider_status()
    return ollama_provider_status()


__all__ = [
    "DEFAULT_PROVIDER",
    "ProviderStatus",
    "active_provider_name",
    "anthropic_provider_status",
    "normalize_ollama_base_url",
    "normalize_openai_compatible_base_url",
    "normalize_provider_name",
    "ollama_provider_status",
    "openai_compatible_provider_status",
    "provider_status",
]
