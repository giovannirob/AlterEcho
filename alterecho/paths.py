"""User paths independent of the terminal's current directory."""
import os
from pathlib import Path
import sys


def portable_home():
    value = os.environ.get("ALTERECHO_HOME")
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("ALTERECHO_HOME deve essere un percorso assoluto.")
    return path


def config_dir():
    if portable_home():
        return portable_home() / "config"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "AlterEcho"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "alterecho"


def data_dir():
    if portable_home():
        return portable_home() / "data"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "AlterEcho"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "alterecho"


def project_root():
    root = Path(__file__).resolve().parents[1]
    return root if (root / "pyproject.toml").is_file() else None
