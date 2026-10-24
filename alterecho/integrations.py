"""User-managed adapter profiles. Store configuration, never API key values."""
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
        raise BridgeError("Profilo adapter non valido; sono ammessi solo i campi previsti, senza credenziali.")
    if not profile["id"] or not profile["name"].strip() or profile["provider"] not in PROVIDERS:
        raise BridgeError("Nome, ID o tipo di adapter non valido.")
    provider = profile["provider"]
    if provider in API_URLS:
        if profile["url"] != API_URLS[provider] or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", profile["api_key_env"]):
            raise BridgeError("Usa l'endpoint ufficiale e il nome della variabile d'ambiente della chiave API.")
    elif provider == "ollama":
        Config(ollama_url=profile["url"]).validate()
    elif not profile["binary"] or (("/" in profile["binary"] or "\\" in profile["binary"]) and not Path(profile["binary"]).expanduser().is_absolute()):
        raise BridgeError("L'eseguibile Codex deve essere nel PATH oppure indicato con un percorso assoluto.")


class AdapterCatalog:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "adapters.json"

    def load(self, cfg=None):
        if not self.path.exists():
            cfg = cfg or Config()
            a, b = new_profile("codex", "Codex"), new_profile("ollama", "Ollama")
            a.update(id="codex-default", model=cfg.codex_model, binary=cfg.codex_binary)
            b.update(id="ollama-default", model=cfg.ollama_model, url=cfg.ollama_url)
            return [a, b]
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if saved.get("schema_version") != 1:
                raise ValueError("versione non supportata")
            profiles = saved["adapters"]
            self.validate(profiles)
            return profiles
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
            raise BridgeError(f"Catalogo adapter non valido: {self.path}. {e}") from e

    def validate(self, profiles):
        if not isinstance(profiles, list) or not profiles:
            raise BridgeError("Il catalogo deve contenere almeno un adapter.")
        for profile in profiles:
            validate_profile(profile)
        if len({p["id"] for p in profiles}) != len(profiles):
            raise BridgeError("ID adapter duplicato.")

    def save(self, profiles):
        self.validate(profiles)
        atomic_write(self.path, json.dumps({"schema_version": 1, "adapters": profiles}, ensure_ascii=False, indent=2))
