import re
import sys
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, FloatPrompt

from .stats import summarize


def safe_text(value):
    # Strip terminal control sequences, without changing the saved/forwarded content.
    value = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))", "", str(value))
    return "".join(c for c in value if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159))


class Terminal:
    def __init__(self):
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        self.console = Console(highlight=False)
        self.mock = False

    def say(self, text):
        self.console.print(Text(safe_text(text)))

    def waiting(self, speaker, count, total):
        status = "simulazione locale" if self.mock else "connessioni verificate"
        self.say(f"[{count}/{total}] {speaker} sta rispondendo… · {status} · Ctrl+C per fermare")

    def message(self, m, count, total):
        style = "cyan" if m.speaker == "codex" else "green"
        usage = m.usage
        details = f"{m.seconds:.2f}s"
        if usage.get("input_tokens") is not None:
            details += f" · input {usage['input_tokens']} token"
        if usage.get("output_tokens") is not None:
            details += f" · output {usage['output_tokens']} token"
        if usage.get("tokens_per_second") is not None:
            details += f" · {usage['tokens_per_second']:.1f} token/s di generazione"
        self.console.print(Panel(Text(safe_text(m.text)), title=Text(safe_text(f"{count}/{total} · {m.speaker} · {m.model}")), subtitle=Text(details), border_style=style))

    def error(self, text):
        self.console.print(Panel(Text(safe_text(text)), title="Arresto", border_style="red"))

    def summary(self, conversation, path):
        stats = summarize(conversation)
        self.say(f"Stato: {conversation.status} · messaggi: {stats['messages']} · generazione: {stats['seconds']:.2f}s")
        for speaker, values in stats["speakers"].items():
            self.say(f"{speaker}: {values['messages']} messaggi · token input/output rilevati {values['input_tokens']}/{values['output_tokens']} ({values['usage_samples']} campioni)")
        self.say(f"Salvato: {path.resolve()} (+ .md e .txt)")

    def select(self, label, values, default):
        if not values:
            raise ValueError(f"Nessun modello disponibile: {label}")
        table = Table(title=label)
        table.add_column("#")
        table.add_column("Modello")
        for i, value in enumerate(values, 1):
            table.add_row(str(i), safe_text(value))
        self.console.print(table)
        index = values.index(default) + 1 if default in values else 1
        choice = Prompt.ask("Seleziona", choices=[str(i) for i in range(1, len(values) + 1)], default=str(index), console=self.console)
        return values[int(choice) - 1]

    def configure(self, cfg, codex_models, ollama_models):
        cfg.ollama_model = self.select("Ollama · modelli installati", ollama_models, cfg.ollama_model)
        cfg.codex_model = self.select("Codex · catalogo CLI (accesso effettivo verificabile alla prima risposta)", [m["model"] for m in codex_models], cfg.codex_model)
        selected = next(m for m in codex_models if m["model"] == cfg.codex_model)
        efforts = [e["reasoningEffort"] for e in selected.get("supportedReasoningEfforts", [])]
        if efforts:
            cfg.codex_effort = Prompt.ask("Ragionamento Codex", choices=efforts, default=cfg.codex_effort if cfg.codex_effort in efforts else selected.get("defaultReasoningEffort", efforts[0]), console=self.console)
        cfg.topic = Prompt.ask("Argomento", default=cfg.topic, console=self.console)
        cfg.mode = Prompt.ask("Modalità: free=libera, debate=dibattito, blind=cieca", choices=["free", "debate", "blind"], default=cfg.mode, console=self.console)
        for speaker in ("codex", "ollama"):
            cfg.roles[speaker] = Prompt.ask(f"Ruolo/personalità {speaker} (facoltativo)", default=cfg.roles[speaker], console=self.console)
            if cfg.mode == "debate":
                cfg.positions[speaker] = Prompt.ask(f"Posizione {speaker}", default=cfg.positions[speaker], console=self.console)
        cfg.first = Prompt.ask("Chi inizia", choices=["codex", "ollama"], default=cfg.first, console=self.console)
        cfg.max_turns = IntPrompt.ask("Numero massimo di messaggi totali", default=cfg.max_turns, console=self.console)
        cfg.delay = FloatPrompt.ask("Ritardo tra messaggi (secondi)", default=cfg.delay, console=self.console)
        cfg.validate()
        self.say(f"{cfg.codex_model} ↔ {cfg.ollama_model} · {cfg.mode} · massimo {cfg.max_turns} messaggi")
        Prompt.ask("Invio per avviare (Ctrl+C annulla)", default="", console=self.console)
