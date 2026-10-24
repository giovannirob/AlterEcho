"""Server configuration and singleton lease; never supplied by API callers."""
from dataclasses import dataclass, field
import ipaddress
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from .config import BridgeError
from .paths import config_dir, data_dir
from .storage import atomic_write


def loopback(host):
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = ""
    origins: list[str] = field(default_factory=list)
    allowed_hosts: list[str] = field(default_factory=list)
    config_path: Path | None = None
    data_path: Path | None = None
    max_active: int = 4

    @classmethod
    def from_env(cls, host=None, port=None):
        token = os.environ.get("ALTERECHO_TOKEN", "")
        if not token and os.environ.get("ALTERECHO_TOKEN_FILE"):
            token = Path(os.environ["ALTERECHO_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
        return cls(host=host or os.environ.get("ALTERECHO_HOST", "127.0.0.1"),
                   port=port or int(os.environ.get("ALTERECHO_PORT", "8765")),
                   token=token,
                   origins=[v.strip().rstrip("/") for v in os.environ.get("ALTERECHO_ORIGINS", "").split(",") if v.strip()],
                   allowed_hosts=[v.strip() for v in os.environ.get("ALTERECHO_ALLOWED_HOSTS", "").split(",") if v.strip()])

    @property
    def directory(self):
        return Path(self.config_path) if self.config_path else config_dir()

    @property
    def runtime(self):
        return Path(self.data_path) if self.data_path else data_dir()

    def prepare(self):
        if not 0 < self.port < 65536:
            raise BridgeError("Porta del server non valida.")
        if not loopback(self.host) and (not self.token or not self.origins or not self.allowed_hosts):
            raise BridgeError("Accesso di rete: imposta ALTERECHO_TOKEN (almeno 32 caratteri), ALTERECHO_ORIGINS e ALTERECHO_ALLOWED_HOSTS.")
        file = self.directory / "server-token"
        if not self.token:
            self.directory.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                self.token = file.read_text(encoding="utf-8").strip()
            else:
                self.token = secrets.token_urlsafe(32)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(self.token)
        if len(self.token) < 32:
            raise BridgeError("Il token del servizio deve contenere almeno 32 caratteri.")
        if not self.origins:
            self.origins = [f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}", f"http://[::1]:{self.port}"]
        if not self.allowed_hosts:
            self.allowed_hosts = ["127.0.0.1", "localhost", "[::1]"]
        for origin in self.origins:
            url = urlsplit(origin)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.path or url.query or url.fragment or "*" in origin:
                raise BridgeError("ALTERECHO_ORIGINS richiede origini HTTP(S) esatte, senza wildcard o percorsi.")
        if any("*" in h or "/" in h for h in self.allowed_hosts):
            raise BridgeError("ALTERECHO_ALLOWED_HOSTS richiede hostname/IP espliciti, senza wildcard o percorsi.")


class ServerLease:
    """OS-released lock: also prevents two servers on different TCP ports."""
    def __init__(self, path):
        self.path, self.stream = Path(path), None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(b"0")
            self.stream = self.path.open("r+b")
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if self.stream:
                self.stream.close()
            self.stream = None
            raise BridgeError("Un server AlterEcho possiede già questa directory dati.") from e

    def release(self):
        if self.stream:
            self.stream.close()
            self.stream = None
