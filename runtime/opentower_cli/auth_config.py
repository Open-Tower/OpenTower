from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .anthropic_client import API_URL as ANTHROPIC_API_URL
from .anthropic_client import DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL
from .config_loader import ConfigError
from .ollama_client import DEFAULT_BASE_URL as OLLAMA_DEFAULT_BASE_URL
from .ollama_client import DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL
from .openai_compatible_client import DEFAULT_MODEL as OPENAI_COMPATIBLE_DEFAULT_MODEL
from .provider_runtime import DEFAULT_PROVIDER, normalize_provider_name


AUTH_FILE_NAME = "auth.json"


@dataclass(frozen=True)
class AuthProfile:
    path: Path
    provider: str
    model: str | None = None
    api_base_url: str | None = None
    api_key: str | None = None
    created: bool = False


def auth_config_path(root: Path) -> Path:
    return root / AUTH_FILE_NAME


def auth_template_payload() -> dict[str, Any]:
    return {
        "active_provider": DEFAULT_PROVIDER,
        "providers": {
            "anthropic": {
                "model": ANTHROPIC_DEFAULT_MODEL,
                "api_base_url": ANTHROPIC_API_URL,
                "api_key": "",
            },
            "openai-compatible": {
                "model": OPENAI_COMPATIBLE_DEFAULT_MODEL,
                "api_base_url": "https://api.openai.com/v1",
                "api_key": "",
            },
            "ollama": {
                "model": OLLAMA_DEFAULT_MODEL,
                "api_base_url": OLLAMA_DEFAULT_BASE_URL,
                "api_key": "",
            },
        },
    }


def ensure_auth_config(root: Path) -> Path:
    path = auth_config_path(root)
    if path.exists():
        return path
    path.write_text(json.dumps(auth_template_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _clean_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _profile_from_env_style(path: Path, payload: dict[str, Any], *, created: bool) -> AuthProfile | None:
    if not any(key in payload for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_API_KEY", "OPENTOWER_MODEL_PROVIDER")):
        return None

    provider_hint = (
        _clean_str(payload.get("OPENTOWER_MODEL_PROVIDER"))
        or ("anthropic" if _clean_str(payload.get("ANTHROPIC_API_KEY")) else None)
        or ("ollama" if _clean_str(payload.get("OLLAMA_API_KEY")) else None)
        or ("openai-compatible" if _clean_str(payload.get("OPENAI_API_KEY")) else None)
        or DEFAULT_PROVIDER
    )
    provider = normalize_provider_name(provider_hint)

    if provider == "anthropic":
        return AuthProfile(
            path=path,
            provider=provider,
            model=_clean_str(payload.get("OPENTOWER_CLAUDE_MODEL") or payload.get("ANTHROPIC_MODEL")),
            api_base_url=_clean_str(payload.get("OPENTOWER_ANTHROPIC_API_URL") or payload.get("ANTHROPIC_API_URL")),
            api_key=_clean_str(payload.get("OPENTOWER_ANTHROPIC_API_KEY") or payload.get("ANTHROPIC_API_KEY")),
            created=created,
        )
    if provider == "ollama":
        return AuthProfile(
            path=path,
            provider=provider,
            model=_clean_str(payload.get("OPENTOWER_OLLAMA_MODEL") or payload.get("OLLAMA_MODEL")),
            api_base_url=_clean_str(payload.get("OPENTOWER_OLLAMA_BASE_URL") or payload.get("OLLAMA_BASE_URL")),
            api_key=_clean_str(payload.get("OLLAMA_API_KEY")),
            created=created,
        )
    return AuthProfile(
        path=path,
        provider=provider,
        model=_clean_str(payload.get("OPENTOWER_OPENAI_MODEL") or payload.get("OPENAI_MODEL")),
        api_base_url=_clean_str(payload.get("OPENTOWER_OPENAI_BASE_URL") or payload.get("OPENAI_BASE_URL")),
        api_key=_clean_str(payload.get("OPENTOWER_OPENAI_API_KEY") or payload.get("OPENAI_API_KEY")),
        created=created,
    )


def load_auth_profile(root: Path, *, create_if_missing: bool = True) -> AuthProfile:
    path = auth_config_path(root)
    created = False
    if not path.exists():
        if not create_if_missing:
            return AuthProfile(path=path, provider=DEFAULT_PROVIDER, created=False)
        ensure_auth_config(root)
        created = True

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"{path} must contain a JSON object.")

    env_profile = _profile_from_env_style(path, payload, created=created)
    if env_profile is not None:
        return env_profile

    provider_raw = _clean_str(payload.get("active_provider") or payload.get("provider")) or DEFAULT_PROVIDER
    provider = normalize_provider_name(provider_raw)

    providers = payload.get("providers", {})
    if providers and not isinstance(providers, dict):
        raise ConfigError(f"{path} field 'providers' must be an object.")

    section = providers.get(provider, {}) if isinstance(providers, dict) else {}
    if section and not isinstance(section, dict):
        raise ConfigError(f"{path} field 'providers.{provider}' must be an object.")

    model = _clean_str(section.get("model") if isinstance(section, dict) else None) or _clean_str(payload.get("model"))
    api_base_url = _clean_str(section.get("api_base_url") if isinstance(section, dict) else None) or _clean_str(payload.get("api_base_url"))
    api_key = _clean_str(section.get("api_key") if isinstance(section, dict) else None) or _clean_str(payload.get("api_key"))

    return AuthProfile(
        path=path,
        provider=provider,
        model=model,
        api_base_url=api_base_url,
        api_key=api_key,
        created=created,
    )


def auth_env_overrides(profile: AuthProfile) -> dict[str, str]:
    overrides: dict[str, str] = {"OPENTOWER_MODEL_PROVIDER": profile.provider}
    if profile.provider == "anthropic":
        if profile.model:
            overrides["OPENTOWER_CLAUDE_MODEL"] = profile.model
            overrides["ANTHROPIC_MODEL"] = profile.model
        if profile.api_base_url:
            overrides["OPENTOWER_ANTHROPIC_API_URL"] = profile.api_base_url
            overrides["ANTHROPIC_API_URL"] = profile.api_base_url
        if profile.api_key:
            overrides["OPENTOWER_ANTHROPIC_API_KEY"] = profile.api_key
            overrides["ANTHROPIC_API_KEY"] = profile.api_key
        return overrides
    if profile.provider == "openai-compatible":
        if profile.model:
            overrides["OPENTOWER_OPENAI_MODEL"] = profile.model
            overrides["OPENAI_MODEL"] = profile.model
        if profile.api_base_url:
            overrides["OPENTOWER_OPENAI_BASE_URL"] = profile.api_base_url
            overrides["OPENAI_BASE_URL"] = profile.api_base_url
        if profile.api_key:
            overrides["OPENTOWER_OPENAI_API_KEY"] = profile.api_key
            overrides["OPENAI_API_KEY"] = profile.api_key
        return overrides
    if profile.model:
        overrides["OPENTOWER_OLLAMA_MODEL"] = profile.model
        overrides["OLLAMA_MODEL"] = profile.model
    if profile.api_base_url:
        overrides["OPENTOWER_OLLAMA_BASE_URL"] = profile.api_base_url
        overrides["OLLAMA_BASE_URL"] = profile.api_base_url
    if profile.api_key:
        overrides["OLLAMA_API_KEY"] = profile.api_key
    return overrides


__all__ = [
    "AUTH_FILE_NAME",
    "AuthProfile",
    "auth_config_path",
    "auth_env_overrides",
    "auth_template_payload",
    "ensure_auth_config",
    "load_auth_profile",
]
