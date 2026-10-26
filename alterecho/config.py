from .i18n import message as t
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import math
import tomllib
import os
from .paths import data_dir, conversations_dir


class BridgeError(Exception):
    """Operational error that must stop the current operation."""


@dataclass
class Config:
    topic: str = "Che cosa rende utile una conversazione?"
    mode: str = "free"
    first: str = "codex"
    max_turns: int = 10
    delay: float = 0
    timeout: float = 180
    codex_model: str = ""
    codex_binary: str = "codex"
    codex_home: str = ""
    codex_effort: str = "low"
    ollama_model: str = "qwen3.5:9b"
    ollama_url: str = "http://localhost:11434"
    ollama_keep_alive: int | str = -1
    ollama_unload_on_exit: bool = True
    num_ctx: int = 4096
    num_predict: int = 512
    temperature: float = 0.7
    ollama_options: dict = field(default_factory=dict)
    adapter_pair: dict = field(default_factory=dict)
    api_max_output_tokens: int = 512
    roles: dict = field(default_factory=lambda: {"codex": "", "ollama": ""})
    positions: dict = field(default_factory=lambda: {
        "codex": "Sostieni la posizione favorevole.",
        "ollama": "Sostieni la posizione contraria.",
    })
    # Legacy field accepted for old TOML files and saved sessions; no longer used.
    codex_context_budget: int = 24000
    output_dir: str = field(default_factory=lambda: str(conversations_dir()))
    codex_work_dir: str = field(default_factory=lambda: str(data_dir() / "work/codex-dialogue"))

    def validate(self):
        if not isinstance(self.adapter_pair, dict):
            raise BridgeError(t('config.adapter_pair_must_be_a_table'))
        if self.adapter_pair:
            from .integrations import validate_profile
            if set(self.adapter_pair) != {"codex", "ollama"}:
                raise BridgeError(t('config.select_both_participants_a_and_b'))
            for profile in self.adapter_pair.values():
                validate_profile(profile)
            if self.adapter_pair["ollama"]["provider"] == "codex":
                raise BridgeError(t('config.codex_cli_can_only_occupy_position_a'))
            if sum(p["provider"] == "ollama" for p in self.adapter_pair.values()) > 1:
                raise BridgeError(t('config.only_one_ollama_model_is_allowed_per_conversation'))
        # A deliberate subset of Ollama's native duration/seconds formats.
        value = self.ollama_keep_alive
        if not ((type(value) is int and value in (-1, 0)) or
                (type(value) is str and value in ("5m", "10m"))):
            raise BridgeError(t('config.ollama_keep_alive_must_be_1_0_5m_or_10m'))
        if type(self.ollama_unload_on_exit) is not bool:
            raise BridgeError(t('config.ollama_unload_on_exit_must_be_true_or_false'))
        for name in ("topic", "codex_model", "codex_binary", "codex_home", "ollama_model", "ollama_url", "output_dir", "codex_work_dir"):
            if not isinstance(getattr(self, name), str):
                raise BridgeError(t('config.must_be_text' ,p0=name))
        if self.mode not in {"free", "debate", "blind"} or self.first not in {"codex", "ollama"}:
            raise BridgeError(t('config.invalid_mode_or_first_participant'))
        for name in ("max_turns", "num_ctx", "num_predict", "api_max_output_tokens"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise BridgeError(t('config.must_be_a_positive_integer' ,p0=name))
        if self.num_predict + 256 >= self.num_ctx:
            raise BridgeError(t('config.num_ctx_must_leave_room_for_input_response_and_margin_256'))
        for name in ("timeout", "delay", "temperature"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise BridgeError(t('config.invalid' ,p0=name))
        if self.timeout <= 0 or not self.topic.strip():
            raise BridgeError(t('config.a_positive_timeout_and_nonempty_topic_are_required'))
        if not self.output_dir or not self.codex_work_dir:
            raise BridgeError(t('config.invalid_storage_or_session_directories'))
        if self.codex_effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
            raise BridgeError(t('config.invalid_codex_reasoning_level'))
        if not isinstance(self.ollama_options, dict):
            raise BridgeError(t('config.ollama_options_must_be_a_table'))
        if {"num_ctx", "num_predict", "temperature"} & self.ollama_options.keys():
            raise BridgeError(t('config.set_num_ctx_num_predict_and_temperature_in_their_dedicated_fields'))
        for mapping in (self.roles, self.positions):
            if not isinstance(mapping, dict) or set(mapping) != {"codex", "ollama"} or not all(isinstance(v, str) for v in mapping.values()):
                raise BridgeError(t('config.roles_and_positions_must_contain_codex_and_ollama_as_text'))
        u = urlsplit(self.ollama_url)
        try:
            local = u.hostname == "localhost" or ipaddress.ip_address(u.hostname or "").is_loopback
        except ValueError:
            local = False
        trusted = {h.strip().lower() for h in os.environ.get("ALTERECHO_OLLAMA_HOSTS", "").split(",") if h.strip()}
        allowed = (local and u.scheme == "http") or (not local and u.hostname in trusted and u.scheme in {"http", "https"})
        try:
            port = u.port
        except ValueError as e:
            raise BridgeError(t('config.invalid_ollama_port')) from e
        if not allowed or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment or port == 0:
            raise BridgeError(t('config.ollama_requires_http_loopback_or_a_host_explicitly_authorized_on_the_server_with_alterecho_olla'))

    @classmethod
    def load(cls, path):
        file = Path(path).expanduser().resolve()
        with file.open("rb") as f:
            result = cls(**tomllib.load(f))
        result.resolve_paths(file.parent)
        result.validate()
        return result

    def resolve_paths(self, base):
        for name in ("output_dir", "codex_work_dir"):
            value = Path(getattr(self, name)).expanduser()
            setattr(self, name, str((value if value.is_absolute() else Path(base) / value).resolve()))
        if self.codex_home:
            value = Path(self.codex_home).expanduser()
            self.codex_home = str((value if value.is_absolute() else Path(base) / value).resolve())
        if "/" in self.codex_binary or "\\" in self.codex_binary:
            value = Path(self.codex_binary).expanduser()
            self.codex_binary = str((value if value.is_absolute() else Path(base) / value).resolve())

    def to_dict(self):
        return asdict(self)
