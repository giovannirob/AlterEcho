import json
import os
from pathlib import Path
from dataclasses import dataclass

from .history import Conversation, participant_label
from .stats import summarize
from .config import BridgeError


@dataclass
class SavedConversation:
    path: Path
    conversation: Conversation
    modified: float


def scan_conversations(directories):
    entries, errors, seen = [], [], set()
    for directory in directories:
        try:
            for file in Path(directory).rglob("*.json"):
                path = file.resolve()
                if path in seen:
                    continue
                seen.add(path)
                try:
                    entries.append(SavedConversation(path, Store(path).load(), path.stat().st_mtime))
                except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
                    errors.append((path, str(e)))
        except OSError as e:
            errors.append((Path(directory), str(e)))
    entries.sort(key=lambda item: (item.modified, str(item.path)), reverse=True)
    return entries, errors


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Store:
    def __init__(self, path):
        self.path = Path(path)

    def save(self, conversation):
        atomic_write(self.path, json.dumps(conversation.to_dict(), ensure_ascii=False, indent=2))

    def load(self):
        return Conversation.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def export(self, conversation, formats=None):
        formats = set(formats or ("md", "txt", "html"))
        invalid = formats - {"md", "txt", "html"}
        if invalid:
            raise BridgeError("Formato di esportazione non supportato: " + ", ".join(sorted(invalid)))
        md = ["# AlterEcho", "", f"Argomento: {conversation.config['topic']}", f"Modalità: {conversation.config['mode']}", f"Stato: {conversation.status}", ""]
        txt = ["AlterEcho", f"Argomento: {conversation.config['topic']}", f"Stato: {conversation.status}", ""]
        for i, m in enumerate(conversation.messages, 1):
            label = participant_label(conversation.config, m.speaker) if conversation.config.get('adapter_pair') else m.speaker
            title = f"{i}. {label} / {m.model} · {m.timestamp} · {m.seconds:.2f}s"
            md.extend([f"## {title}", "", m.text, ""])
            txt.extend([title, m.text, ""])
        if conversation.partial:
            label = "RISPOSTA PARZIALE — non inoltrata"
            md.extend([f"## {label}", "", conversation.partial.get("text", ""), ""])
            txt.extend([label, conversation.partial.get("text", ""), ""])
        stats = json.dumps(summarize(conversation), ensure_ascii=False, indent=2)
        md.extend(["## Statistiche", "", "```json", stats, "```"])
        txt.extend(["Statistiche", stats])
        written = []
        if "md" in formats:
            target = self.path.with_suffix(".md")
            atomic_write(target, "\n".join(md))
            written.append(target)
        if "txt" in formats:
            target = self.path.with_suffix(".txt")
            atomic_write(target, "\n".join(txt))
            written.append(target)
        if "html" in formats:
            from .exporters.html import render_html
            target = self.path.with_suffix(".html")
            atomic_write(target, render_html(conversation))
            written.append(target)
        return written

    def delete(self, conversation_id=None):
        """Delete one selected conversation and its generated exports."""
        if self.path.suffix.lower() != ".json":
            raise BridgeError("Si può eliminare soltanto uno storico JSON.")
        removed = []
        for path in (self.path, self.path.with_suffix(".md"), self.path.with_suffix(".txt"), self.path.with_suffix(".html")):
            try:
                existed = path.exists()
                path.unlink(missing_ok=True)
                if existed:
                    removed.append(path)
            except OSError as e:
                raise BridgeError(f"Impossibile eliminare {path}: {e}") from e
        # New conversations live in a directory named after their ID. Remove
        # that directory only when it is now empty and the ID matches.
        if conversation_id and self.path.stem == conversation_id and self.path.parent.name == conversation_id:
            try:
                self.path.parent.rmdir()
            except OSError:
                pass
        return removed
