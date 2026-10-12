from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import math
import tomllib


class BridgeError(Exception):
    """Errore operativo che deve arrestare il ciclo."""


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
    num_ctx: int = 4096
    num_predict: int = 512
    temperature: float = 0.7
    ollama_options: dict = field(default_factory=dict)
    roles: dict = field(default_factory=lambda: {"codex": "", "ollama": ""})
    positions: dict = field(default_factory=lambda: {
        "codex": "Sostieni la posizione favorevole.",
        "ollama": "Sostieni la posizione contraria.",
    })
    # Legacy field accepted for old TOML files and saved sessions; no longer used.
    codex_context_budget: int = 24000
    output_dir: str = "outputs/conversations"

    def validate(self):
        if self.mode not in {"free", "debate", "blind"} or self.first not in {"codex", "ollama"}:
            raise BridgeError("Modalità o primo interlocutore non validi.")
        for name in ("max_turns", "num_ctx", "num_predict"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise BridgeError(f"{name} deve essere un intero positivo.")
        if self.num_predict + 256 >= self.num_ctx:
            raise BridgeError("num_ctx deve lasciare spazio per input, risposta e margine (256).")
        for name in ("timeout", "delay", "temperature"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise BridgeError(f"{name} non valido.")
        if self.timeout <= 0 or not self.topic.strip():
            raise BridgeError("Timeout positivo e argomento non vuoto richiesti.")
        if self.codex_effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
            raise BridgeError("Livello di ragionamento Codex non valido.")
        if not isinstance(self.ollama_options, dict):
            raise BridgeError("ollama_options deve essere una tabella.")
        if {"num_ctx", "num_predict", "temperature"} & self.ollama_options.keys():
            raise BridgeError("Impostare num_ctx, num_predict e temperature nei campi dedicati.")
        for mapping in (self.roles, self.positions):
            if set(mapping) != {"codex", "ollama"} or not all(isinstance(v, str) for v in mapping.values()):
                raise BridgeError("Ruoli e posizioni devono contenere codex e ollama come testi.")
        u = urlsplit(self.ollama_url)
        try:
            local = u.hostname == "localhost" or ipaddress.ip_address(u.hostname or "").is_loopback
        except ValueError:
            local = False
        if u.scheme != "http" or not local or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
            raise BridgeError("Ollama deve usare HTTP su localhost/loopback, senza credenziali o percorsi.")

    @classmethod
    def load(cls, path):
        with Path(path).open("rb") as f:
            result = cls(**tomllib.load(f))
        result.validate()
        return result

    def to_dict(self):
        return asdict(self)
