from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import math
import tomllib
from .paths import data_dir


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
    output_dir: str = field(default_factory=lambda: str(data_dir() / "conversations"))
    codex_work_dir: str = field(default_factory=lambda: str(data_dir() / "work/codex-dialogue"))

    def validate(self):
        for name in ("topic", "codex_model", "codex_binary", "codex_home", "ollama_model", "ollama_url", "output_dir", "codex_work_dir"):
            if not isinstance(getattr(self, name), str):
                raise BridgeError(f"{name} deve essere un testo.")
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
        if not self.output_dir or not self.codex_work_dir:
            raise BridgeError("Cartelle dei salvataggi e delle sessioni non valide.")
        if self.codex_effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
            raise BridgeError("Livello di ragionamento Codex non valido.")
        if not isinstance(self.ollama_options, dict):
            raise BridgeError("ollama_options deve essere una tabella.")
        if {"num_ctx", "num_predict", "temperature"} & self.ollama_options.keys():
            raise BridgeError("Impostare num_ctx, num_predict e temperature nei campi dedicati.")
        for mapping in (self.roles, self.positions):
            if not isinstance(mapping, dict) or set(mapping) != {"codex", "ollama"} or not all(isinstance(v, str) for v in mapping.values()):
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
