from __future__ import annotations

from pathlib import Path

from opentower_cli.auth_config import auth_env_overrides, load_auth_profile


def test_load_auth_profile_creates_template_when_missing(tmp_path) -> None:
    profile = load_auth_profile(tmp_path)

    assert profile.created is True
    assert profile.path == tmp_path / "auth.json"
    assert profile.path.exists()
    assert profile.provider == "anthropic"


def test_auth_env_overrides_map_openai_compatible_credentials(tmp_path) -> None:
    auth_path = Path(tmp_path) / "auth.json"
    auth_path.write_text(
        """
{
  "active_provider": "openai-compatible",
  "providers": {
    "openai-compatible": {
      "model": "gpt-4o-mini",
      "api_base_url": "https://example.com/v1",
      "api_key": "sk-demo"
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    profile = load_auth_profile(tmp_path, create_if_missing=False)
    overrides = auth_env_overrides(profile)

    assert overrides["OPENTOWER_MODEL_PROVIDER"] == "openai-compatible"
    assert overrides["OPENTOWER_OPENAI_MODEL"] == "gpt-4o-mini"
    assert overrides["OPENTOWER_OPENAI_BASE_URL"] == "https://example.com/v1"
    assert overrides["OPENAI_API_KEY"] == "sk-demo"


def test_load_auth_profile_supports_env_style_json(tmp_path) -> None:
    auth_path = Path(tmp_path) / "auth.json"
    auth_path.write_text(
        """
{
  "OPENAI_API_KEY": "sk-demo",
  "OPENAI_BASE_URL": "https://api.deepseek.com/v1"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    profile = load_auth_profile(tmp_path, create_if_missing=False)

    assert profile.provider == "openai-compatible"
    assert profile.api_key == "sk-demo"
    assert profile.api_base_url == "https://api.deepseek.com/v1"
