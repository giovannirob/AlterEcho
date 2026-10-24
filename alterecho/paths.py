"""User paths independent of the terminal's current directory."""
import os
import shlex
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


def _windows_documents():
    # CSIDL_PERSONAL follows the user's redirected/localized Documents folder,
    # including OneDrive redirection, without guessing its displayed name.
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)
    if result != 0 or not buffer.value:
        raise OSError("Cartella Documenti Windows non disponibile.")
    return Path(buffer.value)


def documents_dir():
    if sys.platform == "win32":
        try:
            return _windows_documents()
        except (OSError, AttributeError):
            return Path.home() / "Documents"
    if sys.platform.startswith("linux"):
        config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        try:
            for line in (config / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
                key, sep, value = line.strip().partition("=")
                if sep and key == "XDG_DOCUMENTS_DIR":
                    parts = shlex.split(value, comments=True)
                    if len(parts) == 1:
                        value = parts[0].replace("${HOME}", str(Path.home())).replace("$HOME", str(Path.home()))
                        path = Path(value)
                        if "$" not in value and path.is_absolute():
                            return path
        except (OSError, ValueError):
            pass
    return Path.home() / "Documents"


def conversations_dir():
    if portable_home():
        return data_dir() / "conversations"
    return documents_dir() / "AlterEcho" / "conversations"


def project_root():
    root = Path(__file__).resolve().parents[1]
    return root if (root / "pyproject.toml").is_file() else None
