"""User-managed adapter profiles. Store configuration, never API key values."""
from .i18n import message as t
import json
from pathlib import Path
import re
from uuid import uuid4

from .config import Config, BridgeError
from .paths import config_dir
from .storage import atomic_write


PROVIDERS = {"codex": "Codex CLI · ChatGPT", "ollama": "Ollama · locale",
             "openai": "OpenAI · API", "openrouter": "OpenRouter · API"}
API_URLS = {"openai": "https://api.openai.com/v1", "openrouter": "https://openrouter.ai/api/v1"}


def new_profile(provider, name):
    return {"id": str(uuid4()), "name": name, "provider": provider, "model": "",
            "binary": "codex" if provider == "codex" else "",
            "url": API_URLS.get(provider, "http://localhost:11434" if provider == "ollama" else ""),
            "api_key_env": {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(provider, "")}


def validate_profile(profile):
    fields = {"id", "name", "provider", "model", "binary", "url", "api_key_env"}
    if not isinstance(profile, dict) or set(profile) != fields or not all(isinstance(v, str) for v in profile.values()):
        raise BridgeError(t('integrations.invalid_adapter_profile_only_expected_fields_without_credentials_are_allowed'))
    if not profile["id"] or not profile["name"].strip() or profile["provider"] not in PROVIDERS:
        raise BridgeError(t('integrations.invalid_adapter_name_id_or_type'))
    provider = profile["provider"]
    if provider in API_URLS:
        if profile["url"] != API_URLS[provider] or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", profile["api_key_env"]):
            raise BridgeError(t('integrations.use_the_official_endpoint_and_the_name_of_the_api_key_environment_variable'))
    elif provider == "ollama":
        Config(ollama_url=profile["url"]).validate()
    elif not profile["binary"] or (("/" in profile["binary"] or "\\" in profile["binary"]) and not Path(profile["binary"]).expanduser().is_absolute()):
        raise BridgeError(t('integrations.codex_executable_must_be_in_path_or_specified_by_an_absolute_path'))


class AdapterCatalog:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "adapters.json"

    def load(self, cfg=None):
        if not self.path.exists():
            cfg = cfg or Config()
            if cfg.adapter_pair:
                return list({p["id"]: dict(p) for p in cfg.adapter_pair.values()}.values())
            a, b = new_profile("codex", "Codex"), new_profile("ollama", "Ollama")
            a.update(id="codex-default", model=cfg.codex_model, binary=cfg.codex_binary)
            b.update(id="ollama-default", model=cfg.ollama_model, url=cfg.ollama_url)
            return [a, b]
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if saved.get("schema_version") != 1:
                raise ValueError(t('integrations.unsupported_version'))
            profiles = saved["adapters"]
            self.validate(profiles)
            return profiles
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
            raise BridgeError(t('integrations.invalid_adapter_catalog' ,p0=self.path, p1=e)) from e

    def validate(self, profiles):
        if not isinstance(profiles, list) or not profiles:
            raise BridgeError(t('integrations.the_catalog_must_contain_at_least_one_adapter'))
        for profile in profiles:
            validate_profile(profile)
        if len({p["id"] for p in profiles}) != len(profiles):
            raise BridgeError(t('integrations.duplicate_adapter_id'))

    def save(self, profiles):
        self.validate(profiles)
        atomic_write(self.path, json.dumps({"schema_version": 1, "adapters": profiles}, ensure_ascii=False, indent=2))
