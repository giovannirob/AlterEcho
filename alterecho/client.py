"""HTTP-only clients. Importing this module never loads a provider or engine."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .config import Config, BridgeError
from .paths import config_dir
from .storage import atomic_write


SLOTS = {"A": "codex", "B": "ollama"}
LETTERS = {v: k for k, v in SLOTS.items()}


class Connection:
    def __init__(self, server=None, token=None):
        self.path = config_dir() / "client.json"
        saved = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.server = (server or os.environ.get("ALTERECHO_SERVER") or saved.get("server") or "http://127.0.0.1:8765").rstrip("/")
        u = urlsplit(self.server)
        if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in {"", "/"}:
            raise BridgeError("Indirizzo server non valido: usa http(s)://host:porta.")
        self.token = token if token is not None else os.environ.get("ALTERECHO_TOKEN", "")
        token_file = os.environ.get("ALTERECHO_TOKEN_FILE") or saved.get("token_file")
        if not self.token and token_file:
            self.token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
        if not self.token and u.hostname in {"localhost", "127.0.0.1", "::1"}:
            file = config_dir() / "server-token"
            if file.exists():
                self.token = file.read_text(encoding="utf-8").strip()

    def save(self, token_file=None):
        values = {"server": self.server}
        if token_file:
            file = Path(token_file).expanduser().resolve()
            if not file.is_file():
                raise BridgeError("File del token non trovato.")
            values["token_file"] = str(file)
        atomic_write(self.path, json.dumps(values, indent=2))


class APIClient:
    def __init__(self, connection=None, session=None):
        self.connection = connection or Connection()
        self.session = session or httpx.Client(base_url=self.connection.server, timeout=30,
                                               trust_env=False, follow_redirects=False)
        self.headers = {"Authorization": "Bearer " + self.connection.token}

    def close(self):
        self.session.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, "/api/v1" + path, headers=self.headers, **kwargs)
            self.check(response)
            return response
        except httpx.HTTPError as e:
            raise BridgeError(f"Avvia 'alterecho serve' oppure configura --server / ALTERECHO_SERVER.\nServer AlterEcho non raggiungibile a {self.connection.server}.") from e

    @staticmethod
    def check(response):
        if response.is_error:
            try:
                detail = response.json().get("detail", "Richiesta rifiutata.")
            except ValueError:
                detail = "Risposta del server non valida."
            if response.status_code == 401:
                detail = "Token del servizio assente o non valido. Configura ALTERECHO_TOKEN oppure 'alterecho connect --token-file FILE'."
            raise BridgeError(str(detail))

    def get(self, path):
        return self.request("GET", path).json()

    def post(self, path, data=None):
        return self.request("POST", path, json=data or {}).json()

    def put(self, path, data):
        return self.request("PUT", path, json=data).json()

    def events(self, cid, cursor=None):
        headers = dict(self.headers)
        if cursor:
            headers["Last-Event-ID"] = cursor
        try:
            with self.session.stream("GET", f"/api/v1/conversations/{cid}/events", headers=headers, timeout=None) as response:
                self.check(response)
                data = []
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        yield json.loads("\n".join(data))
                        data.clear()
        except httpx.HTTPError as e:
            raise BridgeError("Stream disconnesso; la conversazione continua sul server.") from e


class ClientConfig(Config):
    def validate(self):
        # Local validation is presentational; endpoint trust belongs to the
        # server, whose allowlist may differ from this remote machine's env.
        clone = Config(**self.to_dict())
        clone.ollama_url = "http://localhost:11434"
        for p in clone.adapter_pair.values():
            if p["provider"] == "ollama":
                p["url"] = clone.ollama_url
        clone.validate()


def to_config(values, profiles):
    values = dict(values)
    selected = values.pop("participants")
    values["first"] = SLOTS[values["first"]]
    for key in ("roles", "positions"):
        values[key] = {SLOTS[k]: v for k, v in values[key].items()}
    pair = {}
    for letter, p in selected.items():
        profile = next((dict(v) for v in profiles if v["id"] == p["profile_id"]), None)
        if profile is None:
            # A saved history retains a snapshot even after profile removal.
            from .integrations import new_profile
            profile = new_profile(p["provider"], p["name"])
            profile["id"] = p["profile_id"]
        profile.pop("billable", None)
        profile.setdefault("binary", "codex" if profile["provider"] == "codex" else "")
        profile["model"] = p["model"]
        pair[SLOTS[letter]] = profile
    values.update(adapter_pair=pair, codex_model=pair["codex"]["model"], ollama_model=pair["ollama"]["model"])
    return ClientConfig(**values)


def configuration(cfg):
    fields = {"topic", "mode", "max_turns", "delay", "timeout", "codex_effort", "ollama_keep_alive", "ollama_unload_on_exit", "num_ctx", "num_predict", "api_max_output_tokens", "temperature", "ollama_options"}
    values = {k: v for k, v in cfg.to_dict().items() if k in fields}
    values.update(first=LETTERS[cfg.first], roles={LETTERS[k]: v for k, v in cfg.roles.items()},
                  positions={LETTERS[k]: v for k, v in cfg.positions.items()})
    if cfg.adapter_pair:
        values["participants"] = {LETTERS[k]: {"profile_id": p["id"], "model": p["model"]} for k, p in cfg.adapter_pair.items()}
    return values


class RemoteCatalog:
    def __init__(self, client):
        self.client = client

    def load(self, cfg=None):
        result = self.client.get("/profiles")
        for p in result:
            p.pop("billable", None)
            p["binary"] = "codex" if p["provider"] == "codex" else ""
        return result

    def save(self, profiles):
        data = []
        for p in profiles:
            if p.get("binary") not in {"", "codex"}:
                raise BridgeError("Configura l'eseguibile Codex direttamente sul server.")
            data.append({k: v for k, v in p.items() if k not in {"binary", "billable"}})
        self.client.put("/profiles", {"profiles": data})


class RemotePreferences:
    remote = True
    def __init__(self, client):
        self.client = client
        self.path = client.connection.server + "/api/v1/settings"
        self.catalog = RemoteCatalog(client)

    def load(self):
        return to_config(self.client.get("/settings"), self.client.get("/profiles"))

    def save(self, cfg):
        self.client.put("/settings", configuration(cfg))
