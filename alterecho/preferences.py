import json
from pathlib import Path

from .config import Config, BridgeError
from .paths import config_dir, data_dir, project_root
from .storage import atomic_write


class UserSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "config.json"
        self.migrated_from = None

    def load(self):
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(saved, dict) or saved.get("schema_version") != 1:
                    raise ValueError("versione non supportata")
                cfg = Config(**saved["config"])
                cfg.resolve_paths(self.path.parent)
                cfg.validate()
                return cfg
            except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
                raise BridgeError(f"Impostazioni non valide in {self.path}: {e}. Il file non è stato modificato.") from e
        root = project_root()
        legacy = root / "config.toml" if root else None
        if legacy and legacy.is_file():
            cfg = Config.load(legacy)
            self.migrated_from = legacy
            return cfg
        return Config()

    def save(self, cfg):
        cfg.validate()
        values = cfg.to_dict()
        directories = self.known_history_dirs()
        directories.append(str(Path(cfg.output_dir).expanduser().resolve()))
        atomic_write(self.path, json.dumps({"schema_version": 1, "config": values,
                    "history_directories": list(dict.fromkeys(directories))}, ensure_ascii=False, indent=2))

    def known_history_dirs(self):
        if not self.path.exists():
            return []
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            roots = saved.get("history_directories", [])
            if not isinstance(roots, list) or not all(isinstance(p, str) and Path(p).is_absolute() for p in roots):
                raise ValueError("cartelle degli storici non valide")
            previous = saved.get("config", {}).get("output_dir")
            if isinstance(previous, str) and Path(previous).is_absolute():
                roots = roots + [previous]
            return list(dict.fromkeys(roots))
        except (OSError, ValueError, TypeError, AttributeError) as e:
            raise BridgeError(f"Impostazioni non valide in {self.path}: {e}. Il file non è stato modificato.") from e


def history_directories(cfg, preferences=None):
    roots = [Path(cfg.output_dir), data_dir() / "conversations"]
    if preferences:
        roots.extend(Path(p) for p in preferences.known_history_dirs())
    project = project_root()
    if project:
        roots.append(project / "outputs/conversations")
    return list(dict.fromkeys(p.expanduser().resolve() for p in roots))


def resumed_config(conversation, path):
    cfg = Config(**conversation.config)
    # Old sessions used <project>/work/codex-dialogue. Preserve that location.
    if "codex_work_dir" not in conversation.config:
        output = Path(conversation.config.get("output_dir", "outputs/conversations"))
        directory = Path(path).resolve().parent
        if not output.is_absolute() and output.parts and tuple(directory.parts[-len(output.parts):]) == output.parts:
            base = directory
            for _ in output.parts:
                base = base.parent
        else:
            base = project_root() or data_dir()
        cfg.codex_work_dir = str(base / "work/codex-dialogue")
    cfg.output_dir = str(Path(path).resolve().parent)
    cfg.resolve_paths(Path(path).resolve().parent)
    return cfg
