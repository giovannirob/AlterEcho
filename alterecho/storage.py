import json
import os
from pathlib import Path

from .history import Conversation
from .stats import summarize


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

    def export(self, conversation):
        md = ["# AlterEcho", "", f"Argomento: {conversation.config['topic']}", f"Modalità: {conversation.config['mode']}", f"Stato: {conversation.status}", ""]
        txt = ["AlterEcho", f"Argomento: {conversation.config['topic']}", f"Stato: {conversation.status}", ""]
        for i, m in enumerate(conversation.messages, 1):
            title = f"{i}. {m.speaker} / {m.model} · {m.timestamp} · {m.seconds:.2f}s"
            md.extend([f"## {title}", "", m.text, ""])
            txt.extend([title, m.text, ""])
        if conversation.partial:
            label = "RISPOSTA PARZIALE — non inoltrata"
            md.extend([f"## {label}", "", conversation.partial.get("text", ""), ""])
            txt.extend([label, conversation.partial.get("text", ""), ""])
        stats = json.dumps(summarize(conversation), ensure_ascii=False, indent=2)
        md.extend(["## Statistiche", "", "```json", stats, "```"])
        txt.extend(["Statistiche", stats])
        atomic_write(self.path.with_suffix(".md"), "\n".join(md))
        atomic_write(self.path.with_suffix(".txt"), "\n".join(txt))
