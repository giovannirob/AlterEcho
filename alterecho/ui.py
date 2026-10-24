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
from .history import participant_label


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
        self.labels = {}

    def say(self, text):
        self.console.print(Text(safe_text(text)))

    def waiting(self, speaker, count, total):
        status = "simulazione locale" if self.mock else "connessioni verificate"
        self.say(f"[{count}/{total}] {self.labels.get(speaker, speaker)} sta rispondendo… · {status} · Ctrl+C scollega il client")

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
        if usage.get("load_seconds") is not None:
            details += f" · caricamento {usage['load_seconds']:.3f}s"
        if usage.get("generation_seconds") is not None:
            details += f" · generazione {usage['generation_seconds']:.3f}s"
        self.console.print(Panel(Text(safe_text(m.text)), title=Text(safe_text(f"{count}/{total} · {self.labels.get(m.speaker, m.speaker)} · {m.model}")), subtitle=Text(details), border_style=style))

    def error(self, text):
        self.console.print(Panel(Text(safe_text(text)), title="Arresto", border_style="red"))

    def summary(self, conversation, path):
        stats = summarize(conversation)
        states = {"ready": "pronta", "running": "in corso", "completed": "completata", "stopped": "arrestata", "interrupted": "interrotta", "failed": "errore"}
        self.say(f"Stato: {states.get(conversation.status, conversation.status)} · messaggi: {stats['messages']} · generazione: {stats['seconds']:.2f}s")
        for speaker, values in stats["speakers"].items():
            self.say(f"{participant_label(conversation.config, speaker)}: {values['messages']} messaggi · token input/output rilevati {values['input_tokens']}/{values['output_tokens']} ({values['usage_samples']} campioni)")
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
        text += f"\nOllama keep_alive: {cfg.ollama_keep_alive} · scaricamento finale prudente: {'Sì' if cfg.ollama_unload_on_exit else 'No'}"
        if cfg.adapter_pair:
            text = (f"A · {participant_label(cfg, 'codex')}: {cfg.codex_model}\n"
                    f"B · {participant_label(cfg, 'ollama')}: {cfg.ollama_model}\n"
                    f"Argomento: {cfg.topic}\nModalità: {modes[cfg.mode]} · inizia: {participant_label(cfg, cfg.first)}\n"
                    f"Messaggi totali: {cfg.max_turns} · già salvati: {completed}\nSalvataggi: {cfg.output_dir}\nTimeout: {cfg.timeout}s")
            if any(p['provider'] in {'openai', 'openrouter'} for p in cfg.adapter_pair.values()):
                text += "\nProvider API selezionato: le generazioni usano il relativo account API e possono avere costi a consumo."
        for speaker in ("codex", "ollama"):
            if cfg.roles[speaker]:
                text += f"\nPersonalità {participant_label(cfg, speaker)}: {cfg.roles[speaker]}"
            if cfg.mode == "debate":
                text += f"\nPosizione {participant_label(cfg, speaker)}: {cfg.positions[speaker]}"
        self.console.print(Panel(Text(safe_text(text)), title="Riprendi conversazione" if completed else "Nuova conversazione", border_style="cyan"))
        return self.confirm("Avviare?")

    def configure_profiles(self, cfg, catalogs):
        for slot in ("codex", "ollama"):
            profile = cfg.adapter_pair[slot]
            if profile['provider'] in {'openai', 'openrouter'}:
                self.say("Il catalogo API può includere modelli non compatibili con chat; accesso e compatibilità vengono verificati alla prima generazione.")
            values = [m["model"] for m in catalogs[slot]] if profile["provider"] == "codex" else catalogs[slot]
            profile["model"] = self.select(profile["name"] + " · modelli disponibili", values, profile["model"])
            if profile["provider"] == "codex":
                selected = next(m for m in catalogs[slot] if m["model"] == profile["model"])
                efforts = [e["reasoningEffort"] for e in selected.get("supportedReasoningEfforts", [])]
                if efforts and cfg.codex_effort not in efforts:
                    cfg.codex_effort = selected.get("defaultReasoningEffort", efforts[0])
                    if cfg.codex_effort not in efforts:
                        cfg.codex_effort = efforts[0]
        cfg.codex_model, cfg.ollama_model = cfg.adapter_pair["codex"]["model"], cfg.adapter_pair["ollama"]["model"]
        cfg.topic = self.ask("Argomento", default=cfg.topic)
        cfg.max_turns = self.integer("Numero massimo di messaggi totali", cfg.max_turns, minimum=1)
        cfg.validate()
        return self.confirm_run(cfg)

    def main_menu(self):
        while True:
            self.console.print(Panel("ALTERECHO\nDialogo autonomo fra due IA", border_style="cyan"))
            self.say("1. Nuova conversazione\n2. Archivio conversazioni\n   Riprendi, elimina o visualizza una chat salvata\n3. Impostazioni\n0. Esci")
            choice = self.ask("Seleziona", choices=["1", "2", "3", "0"], default="1")
            if choice == "0":
                return "6"
            if choice == "1":
                return "1"
            if choice == "3":
                return "5"
            self.say("ARCHIVIO CONVERSAZIONI\n1. Riprendi conversazione\n2. Elimina conversazione\n3. Visualizza in HTML\n0. Torna al menu principale")
            action = self.ask("Seleziona", choices=["1", "2", "3", "0"], default="0")
            if action != "0":
                return {"1": "2", "2": "3", "3": "4"}[action]

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
            self.say(f"{index}. {date} — {c.config['topic']}\n   {participant_label(c.config, 'codex')}: {c.config['codex_model']} ↔ {participant_label(c.config, 'ollama')}: {c.config['ollama_model']} | {len(c.messages)} messaggi | {states.get(c.status, c.status)}")
        self.say("0. Torna al menu")
        value = self.ask("Seleziona", choices=[str(i) for i in range(len(entries) + 1)], default="0")
        return entries[int(value) - 1] if value != "0" else None

    def settings(self, preferences, diagnostics):
        groups = {
            "1": ("Conversazione", [("1", "Modalità"), ("2", "Personalità"), ("6", "Chi inizia")]),
            "2": ("Modelli e adapter", [("10", "Adapter e integrazioni"), ("3", "Ragionamento e installazione Codex"), ("4", "Parametri Ollama")]),
            "3": ("Esecuzione e salvataggi", [("5", "Limiti, timeout e ritardo"), ("7", "Cartella salvataggi")]),
            "4": ("Diagnostica e manutenzione", [("8", "Diagnostica connessioni"), ("9", "Ripristina impostazioni predefinite")]),
        }
        section = None
        while True:
            cfg = preferences.load()
            if section is None:
                self.say(f"IMPOSTAZIONI · {preferences.path}")
                for number, (title, _) in groups.items():
                    self.say(f"{number}. {title}")
                self.say("0. Torna al menu")
                section = self.ask("Seleziona", choices=["0", *groups], default="0")
                if section == "0":
                    return
                continue
            title, actions = groups[section]
            self.say(f"IMPOSTAZIONI → {title}")
            for number, (_, label) in enumerate(actions, 1):
                self.say(f"{number}. {label}")
            self.say("0. Torna alle impostazioni")
            selected = self.ask("Seleziona", choices=[str(i) for i in range(len(actions) + 1)], default="0")
            if selected == "0":
                section = None
                continue
            choice = actions[int(selected) - 1][0]
            if choice == "8":
                diagnostics(cfg)
                continue
            if choice == "10":
                self.adapter_settings(preferences)
                continue
            candidate = type(cfg)(**cfg.to_dict())
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
                        value = self.ask(f"Personalità {participant_label(cfg, speaker)}", default=cfg.roles[speaker])
                        candidate.roles[speaker] = "" if value == "-" else value
                elif choice == "3":
                    self.say("Il supporto del ragionamento viene verificato con il catalogo del modello scelto.")
                    candidate.codex_effort = self.select("Ragionamento Codex", ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"], cfg.codex_effort)
                    if getattr(preferences, "remote", False):
                        self.say("Eseguibile, percorsi e autenticazione Codex si configurano direttamente sul server.")
                        candidate.validate()
                        preferences.save(candidate)
                        continue
                    candidate.codex_binary = self.ask("Eseguibile Codex (nome o percorso)", default=cfg.codex_binary)
                    if ("/" in candidate.codex_binary or "\\" in candidate.codex_binary) and not Path(candidate.codex_binary).expanduser().is_absolute():
                        raise BridgeError("Per l'eseguibile Codex usa un nome nel PATH o un percorso assoluto.")
                    self.say("Directory Codex: '-' ripristina il rilevamento automatico. Credenziali gestite soltanto da Codex.")
                    value = self.ask("codex_home (facoltativo)", default=cfg.codex_home)
                    candidate.codex_home = "" if value == "-" else value
                    if candidate.codex_home and not Path(candidate.codex_home).expanduser().is_absolute():
                        raise BridgeError("codex_home deve essere un percorso assoluto.")
                elif choice == "4":
                    if getattr(preferences, "remote", False):
                        self.say("Modifica l'endpoint in Adapter e integrazioni; gli host di rete devono essere autorizzati sul server.")
                    else:
                        candidate.ollama_url = self.ask("URL Ollama locale", default=cfg.ollama_url)
                    candidate.num_ctx = self.integer("Contesto in token (più contesto usa più memoria)", cfg.num_ctx, 1)
                    candidate.num_predict = self.integer("Massimo token per risposta", cfg.num_predict, 1)
                    candidate.temperature = self.decimal("Temperature", cfg.temperature)
                    self.say('Opzioni aggiuntive JSON, ad esempio {"top_p": 0.9}; {} le azzera.')
                    candidate.ollama_options = json.loads(self.ask("Opzioni Ollama", default=json.dumps(cfg.ollama_options)))
                    self.say("Memoria Ollama: -1 senza scadenza, 10m o 5m a tempo, 0 scarica dopo ogni risposta.")
                    value = self.ask("keep_alive", choices=["-1", "10m", "5m", "0"], default=str(cfg.ollama_keep_alive))
                    candidate.ollama_keep_alive = int(value) if value in ("-1", "0") else value
                    self.say("Lo scaricamento finale richiede uso esclusivo verificabile; con l'API condivisa viene omesso per proteggere altri client.")
                    candidate.ollama_unload_on_exit = self.ask("Scarica il modello alla fine della conversazione (solo se sicuro)?", choices=["s", "n"], default="s" if cfg.ollama_unload_on_exit else "n", case_sensitive=False) == "s"
                elif choice == "5":
                    candidate.max_turns = self.integer("Messaggi predefiniti", cfg.max_turns, 1)
                    candidate.timeout = self.decimal("Timeout generazione (secondi)", cfg.timeout, positive=True)
                    candidate.delay = self.decimal("Ritardo fra messaggi (secondi)", cfg.delay)
                elif choice == "6":
                    if cfg.adapter_pair:
                        slots = ["codex", "ollama"]
                        names = [f"{letter} · {participant_label(cfg, slot)}" for letter, slot in zip(("A", "B"), slots)]
                        selected = self.select("Chi inizia", names, names[slots.index(cfg.first)])
                        candidate.first = slots[names.index(selected)]
                    else:
                        candidate.first = self.select("Chi inizia", ["codex", "ollama"], cfg.first)
                elif choice == "7":
                    if getattr(preferences, "remote", False):
                        self.say("La cartella operativa si configura soltanto sul server (config.json / ALTERECHO_HOME).")
                        continue
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

    def adapter_settings(self, preferences):
        from .integrations import AdapterCatalog, PROVIDERS, new_profile, validate_profile
        catalog = getattr(preferences, "catalog", None) or AdapterCatalog()
        while True:
            cfg = preferences.load()
            profiles = catalog.load(cfg)
            self.say("ADAPTER E INTEGRAZIONI\n1. Elenco adapter\n2. Aggiungi adapter\n3. Modifica adapter\n4. Rimuovi adapter\n5. Scegli interlocutori A e B\n6. Torna a Codex e Ollama predefiniti\n7. Informazioni MCP e API\n8. Limite token delle risposte API\n0. Torna alle impostazioni")
            choice = self.ask("Seleziona", choices=[str(i) for i in range(9)], default="0")
            if choice == "0":
                return
            try:
                if choice == "1":
                    for p in profiles:
                        self.say(f"{p['name']} · {PROVIDERS[p['provider']]} · modello: {p['model'] or 'da scegliere'}")
                    self.say("Coppia attiva: " + (" ↔ ".join(p['name'] for p in cfg.adapter_pair.values()) if cfg.adapter_pair else "Codex ↔ Ollama predefiniti"))
                    continue
                if choice == "7":
                    self.say("OpenAI e OpenRouter sono provider API: aggiungili come adapter. MCP collega strumenti e risorse, non sostituisce un modello. Questa versione non collega server MCP né abilita strumenti nei dialoghi. Claude Code richiede un adapter dedicato, non ancora incluso.")
                    continue
                if choice == "8":
                    cfg.api_max_output_tokens = self.integer("Massimo token di risposta API", cfg.api_max_output_tokens, 1)
                    preferences.save(cfg)
                    continue
                if choice == "6":
                    cfg.adapter_pair = {}
                    for p in profiles:
                        if p['id'] == 'codex-default':
                            cfg.codex_model, cfg.codex_binary = p['model'], p['binary']
                        elif p['id'] == 'ollama-default':
                            cfg.ollama_model, cfg.ollama_url = p['model'], p['url']
                    preferences.save(cfg)
                    self.say("Ripristinati Codex e Ollama predefiniti.")
                    continue
                if choice == "5":
                    pair = {}
                    for slot, label in (("codex", "A"), ("ollama", "B")):
                        allowed = [p for p in profiles if not (slot == "ollama" and (p['provider'] == 'codex' or (pair['codex']['provider'] == 'ollama' and p['provider'] == 'ollama')))]
                        if not allowed:
                            raise BridgeError("Aggiungi un adapter compatibile per il secondo interlocutore.")
                        values = [f"{p['name']} · {PROVIDERS[p['provider']]} · {p['id'][:8]}" for p in allowed]
                        value = self.select(f"Interlocutore {label}", values, values[0])
                        pair[slot] = dict(allowed[values.index(value)])
                    cfg.adapter_pair = pair
                    cfg.validate()
                    preferences.save(cfg)
                    self.say("Interlocutori salvati per i nuovi dialoghi. Gli storici mantengono i propri adapter.")
                    continue
                if choice == "2":
                    labels = list(PROVIDERS.values())
                    label = self.select("Tipo adapter", labels, labels[0])
                    profile = new_profile(next(k for k, v in PROVIDERS.items() if v == label), self.ask("Nome del profilo"))
                else:
                    values = [f"{p['name']} · {p['id'][:8]}" for p in profiles]
                    value = self.select("Adapter", values, values[0])
                    profile = dict(profiles[values.index(value)])
                    if choice == "4":
                        if any(p['id'] == profile['id'] for p in cfg.adapter_pair.values()):
                            raise BridgeError("Adapter nella coppia attiva: scegli altri interlocutori prima di rimuoverlo.")
                        if self.confirm("Rimuovere il profilo? Gli storici restano intatti"):
                            catalog.save([p for p in profiles if p['id'] != profile['id']])
                        continue
                    profile['name'] = self.ask("Nome del profilo", default=profile['name'])
                if profile['provider'] == 'codex':
                    profile['binary'] = self.ask("Eseguibile Codex", default=profile['binary'])
                elif profile['provider'] == 'ollama':
                    profile['url'] = self.ask("URL Ollama locale", default=profile['url'])
                else:
                    self.say("Inserisci il NOME della variabile d'ambiente, non il valore della chiave API. La scelta dell'adapter API può comportare costi di generazione.")
                    profile['api_key_env'] = self.ask("Variabile della chiave API", default=profile['api_key_env'])
                model = self.ask("Modello preferito (facoltativo; '-' cancella)", default=profile['model'])
                profile['model'] = '' if model == '-' else model
                validate_profile(profile)
                profiles = [p for p in profiles if p['id'] != profile['id']] + [profile]
                catalog.save(profiles)
                for slot, previous in cfg.adapter_pair.items():
                    if previous['id'] == profile['id']:
                        cfg.adapter_pair[slot] = dict(profile)
                preferences.save(cfg)
                self.say("Adapter salvato. Usa 'Scegli interlocutori A e B' per selezionarlo.")
            except (BridgeError, OSError, ValueError, TypeError) as e:
                self.error(str(e))
