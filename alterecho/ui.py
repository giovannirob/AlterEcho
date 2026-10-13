import re
import sys
import json
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.prompt import Prompt

from .stats import summarize
from .config import Config, BridgeError


class ItalianPrompt(Prompt):
    validate_error_message = "Inserisci una delle scelte indicate."
    illegal_choice_message = "Inserisci una delle scelte indicate."


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
        states = {"ready": "pronta", "running": "in corso", "completed": "completata", "stopped": "arrestata", "interrupted": "interrotta", "failed": "errore"}
        self.say(f"Stato: {states.get(conversation.status, conversation.status)} · messaggi: {stats['messages']} · generazione: {stats['seconds']:.2f}s")
        for speaker, values in stats["speakers"].items():
            self.say(f"{speaker}: {values['messages']} messaggi · token input/output rilevati {values['input_tokens']}/{values['output_tokens']} ({values['usage_samples']} campioni)")
        self.say(f"Salvato: {path.resolve()} (+ .md, .txt e .html)")

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
        choice = self.ask("Seleziona", choices=[str(i) for i in range(1, len(values) + 1)], default=str(index))
        return values[int(choice) - 1]

    def configure(self, cfg, codex_models, ollama_models):
        cfg.ollama_model = self.select("Ollama · modelli installati", ollama_models, cfg.ollama_model)
        cfg.codex_model = self.select("Codex · catalogo CLI (accesso effettivo verificabile alla prima risposta)", [m["model"] for m in codex_models], cfg.codex_model)
        selected = next(m for m in codex_models if m["model"] == cfg.codex_model)
        efforts = [e["reasoningEffort"] for e in selected.get("supportedReasoningEfforts", [])]
        if efforts and cfg.codex_effort not in efforts:
            cfg.codex_effort = selected.get("defaultReasoningEffort", efforts[0])
            if cfg.codex_effort not in efforts:
                cfg.codex_effort = efforts[0]
            self.say(f"Ragionamento impostato a {cfg.codex_effort}, supportato dal modello scelto.")
        cfg.topic = self.ask("Argomento", default=cfg.topic)
        cfg.max_turns = self.integer("Numero massimo di messaggi totali", cfg.max_turns, minimum=1)
        cfg.validate()
        return self.confirm_run(cfg)

    def ask(self, label, **kwargs):
        # Text defaults may contain user content; never treat them as Rich markup.
        kwargs.setdefault("console", self.console)
        if "default" in kwargs:
            kwargs["default"] = safe_text(kwargs["default"])
        return ItalianPrompt.ask(label, **kwargs)

    def integer(self, label, default, minimum=0):
        while True:
            value = self.ask(label, default=str(default))
            try:
                number = int(value)
                if number >= minimum:
                    return number
            except ValueError:
                pass
            self.say(f"Inserisci un numero intero maggiore o uguale a {minimum}.")

    def decimal(self, label, default, positive=False):
        import math
        while True:
            try:
                value = float(self.ask(label, default=str(default)).replace(",", "."))
                if math.isfinite(value) and (value > 0 if positive else value >= 0):
                    return value
            except ValueError:
                pass
            self.say("Inserisci un numero positivo." if positive else "Inserisci un numero finito maggiore o uguale a zero.")

    def confirm(self, label):
        return self.ask(label, choices=["s", "n"], default="s", case_sensitive=False) == "s"

    def confirm_run(self, cfg, completed=0):
        modes = {"free": "Libera", "debate": "Dibattito", "blind": "Esperimento cieco"}
        text = (f"Codex: {cfg.codex_model}\nOllama: {cfg.ollama_model}\nArgomento: {cfg.topic}\n"
                f"Modalità: {modes[cfg.mode]} · inizia: {cfg.first}\n"
                f"Messaggi: {cfg.max_turns}" + (f" ({completed} salvati + {cfg.max_turns - completed} nuovi)" if completed else "") +
                f"\nRagionamento Codex: {cfg.codex_effort}\nOllama: contesto {cfg.num_ctx}, risposta {cfg.num_predict} token\n"
                f"Ritardo: {cfg.delay}s · timeout: {cfg.timeout}s\nSalvataggi: {cfg.output_dir}")
        for speaker in ("codex", "ollama"):
            if cfg.roles[speaker]:
                text += f"\nPersonalità {speaker}: {cfg.roles[speaker]}"
            if cfg.mode == "debate":
                text += f"\nPosizione {speaker}: {cfg.positions[speaker]}"
        self.console.print(Panel(Text(safe_text(text)), title="Riprendi conversazione" if completed else "Nuova conversazione", border_style="cyan"))
        return self.confirm("Avviare?")

    def main_menu(self):
        self.console.print(Panel("ALTERECHO\nDialogo autonomo fra due IA", border_style="cyan"))
        self.say("1. Nuova conversazione\n2. Riprendi conversazione\n3. Elimina conversazione\n4. Visualizza in HTML\n5. Impostazioni\n6. Esci")
        return self.ask("Seleziona", choices=["1", "2", "3", "4", "5", "6"], default="1")

    def choose_history(self, entries, action="riprendere"):
        if not entries:
            self.say("Nessuna conversazione salvata nelle cartelle configurate.")
            return None
        self.say(f"CONVERSAZIONI DA {action.upper()} · più recenti per prime")
        states = {"ready": "Pronta", "running": "In corso", "completed": "Completata", "stopped": "Arrestata", "interrupted": "Interrotta", "failed": "Errore"}
        for index, entry in enumerate(entries, 1):
            c = entry.conversation
            try:
                date = datetime.fromisoformat(c.created_at).astimezone().strftime("%d/%m/%Y %H:%M")
            except ValueError:
                date = c.created_at
            self.say(f"{index}. {date} — {c.config['topic']}\n   {c.config['codex_model']} ↔ {c.config['ollama_model']} | {len(c.messages)} messaggi | {states.get(c.status, c.status)}")
        self.say("0. Torna al menu")
        value = self.ask("Seleziona", choices=[str(i) for i in range(len(entries) + 1)], default="0")
        return entries[int(value) - 1] if value != "0" else None

    def settings(self, preferences, diagnostics):
        while True:
            cfg = preferences.load()
            self.say(f"IMPOSTAZIONI · {preferences.path}\n1. Modalità conversazione\n2. Personalità dei modelli\n3. Ragionamento e installazione Codex\n4. Parametri Ollama\n5. Limiti e timeout\n6. Modello che inizia\n7. Cartella salvataggi\n8. Diagnostica connessioni\n9. Ripristina impostazioni predefinite\n0. Torna al menu")
            choice = self.ask("Seleziona", choices=[str(i) for i in range(10)], default="0")
            if choice == "0":
                return
            if choice == "8":
                diagnostics(cfg)
                continue
            candidate = Config(**cfg.to_dict())
            try:
                if choice == "1":
                    modes = {"free": "Libera", "debate": "Dibattito", "blind": "Esperimento cieco"}
                    label = self.select("Modalità", list(modes.values()), modes[cfg.mode])
                    candidate.mode = next(key for key, value in modes.items() if value == label)
                    if candidate.mode == "debate":
                        for speaker in ("codex", "ollama"):
                            candidate.positions[speaker] = self.ask(f"Posizione {speaker}", default=cfg.positions[speaker])
                elif choice == "2":
                    self.say("Invio conserva il valore; '-' cancella la personalità.")
                    for speaker in ("codex", "ollama"):
                        value = self.ask(f"Personalità {speaker}", default=cfg.roles[speaker])
                        candidate.roles[speaker] = "" if value == "-" else value
                elif choice == "3":
                    self.say("Il supporto del ragionamento viene verificato con il catalogo del modello scelto.")
                    candidate.codex_effort = self.select("Ragionamento Codex", ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"], cfg.codex_effort)
                    candidate.codex_binary = self.ask("Eseguibile Codex (nome o percorso)", default=cfg.codex_binary)
                    if ("/" in candidate.codex_binary or "\\" in candidate.codex_binary) and not Path(candidate.codex_binary).expanduser().is_absolute():
                        raise BridgeError("Per l'eseguibile Codex usa un nome nel PATH o un percorso assoluto.")
                    self.say("Directory Codex: '-' ripristina il rilevamento automatico. Credenziali gestite soltanto da Codex.")
                    value = self.ask("codex_home (facoltativo)", default=cfg.codex_home)
                    candidate.codex_home = "" if value == "-" else value
                    if candidate.codex_home and not Path(candidate.codex_home).expanduser().is_absolute():
                        raise BridgeError("codex_home deve essere un percorso assoluto.")
                elif choice == "4":
                    candidate.ollama_url = self.ask("URL Ollama locale", default=cfg.ollama_url)
                    candidate.num_ctx = self.integer("Contesto in token (più contesto usa più memoria)", cfg.num_ctx, 1)
                    candidate.num_predict = self.integer("Massimo token per risposta", cfg.num_predict, 1)
                    candidate.temperature = self.decimal("Temperature", cfg.temperature)
                    self.say('Opzioni aggiuntive JSON, ad esempio {"top_p": 0.9}; {} le azzera.')
                    candidate.ollama_options = json.loads(self.ask("Opzioni Ollama", default=json.dumps(cfg.ollama_options)))
                elif choice == "5":
                    candidate.max_turns = self.integer("Messaggi predefiniti", cfg.max_turns, 1)
                    candidate.timeout = self.decimal("Timeout generazione (secondi)", cfg.timeout, positive=True)
                    candidate.delay = self.decimal("Ritardo fra messaggi (secondi)", cfg.delay)
                elif choice == "6":
                    candidate.first = self.select("Chi inizia", ["codex", "ollama"], cfg.first)
                elif choice == "7":
                    value = Path(self.ask("Cartella salvataggi (percorso assoluto)", default=cfg.output_dir)).expanduser()
                    if not value.is_absolute():
                        raise BridgeError("Inserisci un percorso assoluto per avviare AlterEcho da qualsiasi cartella.")
                    candidate.output_dir = str(value.resolve())
                elif choice == "9":
                    if not self.confirm("Ripristinare le impostazioni? Gli storici restano intatti"):
                        continue
                    candidate = Config()
                candidate.validate()
                preferences.save(candidate)
                self.say("Impostazioni salvate.")
            except (BridgeError, ValueError, TypeError, OSError) as e:
                self.error(f"Impostazioni non salvate: {e}")
