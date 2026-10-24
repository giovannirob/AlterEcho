import argparse
import asyncio
from pathlib import Path
import sys
import webbrowser

from .config import Config, BridgeError
from .history import Conversation, participant_label
from .storage import Store, scan_conversations
from .preferences import UserSettings, history_directories, resumed_config
from .coordinator import Coordinator
from .adapters.codex import CodexAdapter
from .adapters.ollama import OllamaAdapter
from .adapters.base import Reply
from .ui import Terminal


class ItalianParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._positionals.title = "Argomenti"
        self._optionals.title = "Opzioni"
        if self._actions:
            self._actions[0].help = "Mostra questa guida ed esci"

    def format_help(self):
        return super().format_help().replace("usage:", "Uso:")

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"Argomenti non validi: {message}\nUsa 'alterecho help' per la guida.\n")


def parser():
    p = ItalianParser(prog="alterecho", description="AlterEcho — dialoghi autonomi con Codex/Ollama e adapter API opzionali OpenAI/OpenRouter.",
                      formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="Per iniziare: alterecho\nIl menu permette di avviare, riprendere, esportare e configurare i dialoghi.\nImpostazioni e salvataggi sono personali, indipendenti dalla cartella corrente.\nJSON, Markdown, TXT e HTML vengono salvati automaticamente. Ctrl+C conserva lo storico.\nPer le opzioni avanzate: alterecho help COMANDO (oppure COMANDO --help).\nDocumentazione: README.md. doctor non genera; demo usa soltanto simulazioni.")
    sub = p.add_subparsers(dest="action", title="Comandi")
    commands = {}
    for name, help_text in [("run", "Nuovo dialogo: quattro scelte e conferma"), ("doctor", "Verifica connessioni e autenticazione, senza generare"), ("demo", "Simulazione locale senza modelli né quote")]:
        command = sub.add_parser(name, help=help_text, description=help_text)
        commands[name] = command
        command.add_argument("--config", help="File TOML; i percorsi relativi partono dalla sua cartella")
        if name != "doctor":
            command.add_argument("--turns", type=int, help="Massimo messaggi totali, non coppie")
        if name == "run":
            command.add_argument("--num-ctx", type=int, help="Contesto Ollama in token (più contesto usa più memoria)")
            command.add_argument("--non-interactive", action="store_true", help="Usa la configurazione senza domande; avvia inferenza reale immediatamente")
    resume = sub.add_parser("resume", help="Riprendi uno storico JSON verificando il thread Codex", description="Ripresa avanzata: --turns indica il nuovo massimo TOTALE. Nel menu puoi scegliere la chat e i messaggi aggiuntivi senza percorsi.")
    commands["resume"] = resume
    resume.add_argument("path", help="Storico JSON")
    resume.add_argument("--turns", type=int, required=True, help="Nuovo massimo TOTALE, inclusi i messaggi già salvati")
    resume.add_argument("--num-ctx", type=int, help="Contesto Ollama: preserva messaggi e sessione Codex")
    export = sub.add_parser("export", help="Esporta uno storico JSON in Markdown, TXT e HTML", description="Genera file autonomi accanto al JSON senza contattare i modelli.")
    commands["export"] = export
    export.add_argument("path", help="Storico JSON")
    export.add_argument("--format", dest="formats", nargs="+", choices=["md", "txt", "html"], help="Genera soltanto i formati indicati; senza opzione genera tutti i formati")
    guide = sub.add_parser("help", help="Guida generale o di un comando")
    guide.add_argument("command", nargs="?", choices=list(commands), help="Comando da approfondire")
    p.commands = commands
    return p


class DemoAdapter:
    def __init__(self, speaker):
        self.speaker = speaker

    async def generate(self, conversation, checkpoint):
        await asyncio.sleep(0.03)
        index = len(conversation.messages) + 1
        return Reply(f"Messaggio simulato {index}. Ho ricevuto {len(conversation.messages)} messaggi di storico. Argomento: {conversation.config['topic']}", f"mock-{self.speaker}")

    async def close(self):
        pass


async def diagnose(cfg, ui):
    """Independent checks: a failed provider must not hide the other one's status."""
    if cfg.adapter_pair:
        from .profile_runtime import diagnose_profiles
        return await diagnose_profiles(cfg, ui)
    codex, ollama = CodexAdapter(cfg), OllamaAdapter(cfg)
    try:
        results = await asyncio.gather(codex.start(), ollama.models(), return_exceptions=True)
        good = True
        for label, result in zip(("Codex / ChatGPT", "Ollama locale"), results):
            if isinstance(result, BaseException):
                good = False
                ui.error(f"{label}: {result}")
            else:
                ui.say(f"{label}: connesso")
                for model in result:
                    ui.say("  " + (model["model"] if isinstance(model, dict) else model))
        ui.say("Nessuna inferenza avviata. Il catalogo Codex non garantisce le quote per una futura richiesta.")
        return 0 if good else 1
    finally:
        await asyncio.gather(codex.close(), ollama.close())


async def execute(args, ui, preferences=None):
    action = args.action
    ui.mock = action == "demo"
    ui.labels = {}
    if action == "export":
        store = Store(args.path)
        conversation = store.load()
        store.export(conversation, getattr(args, "formats", None))
        ui.summary(conversation, store.path)
        return 0
    if action == "resume":
        store = Store(args.path)
        conversation = store.load()
        cfg = resumed_config(conversation, store.path)
        cfg.max_turns = args.turns
        if args.num_ctx is not None:
            cfg.num_ctx = args.num_ctx
        if cfg.max_turns <= len(conversation.messages):
            raise BridgeError("--turns deve superare i messaggi già completati.")
        if conversation.messages and all(m.model.startswith("mock-") for m in conversation.messages):
            raise BridgeError("Gli storici demo non possono essere ripresi con modelli reali.")
        cfg.validate()
    else:
        cfg = Config.load(args.config) if getattr(args, "config", None) else (preferences.load() if preferences else Config())
        if getattr(args, "turns", None) is not None:
            cfg.max_turns = args.turns
        if getattr(args, "num_ctx", None) is not None:
            cfg.num_ctx = args.num_ctx
        cfg.validate()
        conversation = None
        store = None
    if action == "doctor":
        return await diagnose(cfg, ui)
    if action in {"run", "resume"} and cfg.adapter_pair:
        from .profile_runtime import execute_profiles
        return await execute_profiles(args, ui, preferences, cfg, conversation, store)
    if action == "demo":
        cfg.codex_model = "mock-codex"
        conversation = Conversation(cfg.to_dict())
        store = Store(Path(cfg.output_dir) / conversation.id / f"{conversation.id}.json")
        await Coordinator(cfg, conversation, {s: DemoAdapter(s) for s in ("codex", "ollama")}, store, ui).run()
        return 0
    codex, ollama = CodexAdapter(cfg), OllamaAdapter(cfg)
    persist = False
    try:
        ui.say("Connessioni: verifica Codex/ChatGPT e Ollama… (nessuna generazione)")
        codex_models = await codex.start()
        ollama_models = await ollama.models()
        ui.say("Codex: connesso, autenticazione ChatGPT · Ollama: connesso")
        if action == "run":
            if not getattr(args, "non_interactive", False):
                if not ui.configure(cfg, codex_models, ollama_models):
                    ui.say("Avvio annullato. Nessun messaggio generato.")
                    return 0
            elif not cfg.codex_model:
                raise BridgeError("Scegli codex_model nelle impostazioni o nel TOML; doctor mostra il catalogo.")
            cfg.validate()
            if cfg.ollama_model not in ollama_models:
                raise BridgeError(f"Modello Ollama non installato: {cfg.ollama_model}. Usa Impostazioni → Diagnostica.")
            if preferences and not getattr(args, "config", None):
                preferences.save(cfg)
            conversation = Conversation(cfg.to_dict())
            store = Store(Path(cfg.output_dir) / conversation.id / f"{conversation.id}.json")
            persist = True
            store.save(conversation)
            await codex.attach(conversation, lambda: store.save(conversation))
        else:
            if cfg.ollama_model not in ollama_models:
                raise BridgeError(f"Modello Ollama della chat non installato: {cfg.ollama_model}. Ripristinalo prima della ripresa.")
            # Preflight may recover a completed remote reply. Defer local writes until confirmation.
            await codex.attach(conversation, lambda: None)
            if getattr(args, "additional_turns", None) is not None:
                cfg.max_turns = len(conversation.messages) + args.additional_turns
            if getattr(args, "confirm", False) and not ui.confirm_run(cfg, len(conversation.messages)):
                ui.say("Ripresa annullata. Lo storico non è stato modificato.")
                return 0
            if cfg.max_turns <= len(conversation.messages):
                raise BridgeError("Il recupero ha già raggiunto il limite. Scegli un massimo totale maggiore.")
            conversation.config = cfg.to_dict()
            persist = True
            store.save(conversation)
        ui.say(f"Salvataggio automatico: {store.path.resolve()}")
        if conversation.pending and conversation.pending.get("speaker") == "ollama":
            conversation.pending = None
            store.save(conversation)
        await ollama.prepare()
        await Coordinator(cfg, conversation, {"codex": codex, "ollama": ollama}, store, ui).run()
        return 0 if conversation.status == "completed" else 1
    except asyncio.CancelledError:
        if persist and conversation:
            conversation.status = "interrupted"
        raise
    except Exception as e:
        if persist and conversation:
            conversation.status = "stopped"
            conversation.error = str(e)
        raise
    finally:
        try:
            await asyncio.gather(codex.close(), ollama.close())
            if getattr(ollama, "memory_notice", None):
                ui.say(ollama.memory_notice)
        finally:
            if persist and store and conversation:
                store.save(conversation)
                store.export(conversation)


def interactive_menu(ui, preferences):
    while True:
        selecting = True
        try:
            choice = ui.main_menu()
            selecting = False
            if choice == "6":
                return 0
            if choice == "5":
                ui.settings(preferences, lambda cfg: asyncio.run(diagnose(cfg, ui)))
            elif choice == "3":
                cfg = preferences.load()
                entries, errors = scan_conversations(history_directories(cfg, preferences))
                for path, error in errors:
                    ui.say(f"Storico non leggibile: {path.name} — {error}. Il file resta intatto.")
                entry = ui.choose_history(entries, action="eliminare")
                if entry is not None:
                    label = entry.conversation.config.get("topic", "(senza argomento)")
                    if ui.confirm(f"Eliminare definitivamente '{label}' e i relativi file JSON, Markdown, TXT e HTML?"):
                        removed = Store(entry.path).delete(entry.conversation.id)
                        ui.say(f"Chat eliminata: {entry.path.name} (rimossi {len(removed)} file).")
                    else:
                        ui.say("Eliminazione annullata. Nessun file modificato.")
            elif choice == "4":
                cfg = preferences.load()
                entries, errors = scan_conversations(history_directories(cfg, preferences))
                for path, error in errors:
                    ui.say(f"Storico non leggibile: {path.name} — {error}. Il file resta intatto.")
                entry = ui.choose_history(entries, action="visualizzare in HTML")
                if entry is not None:
                    c = entry.conversation
                    ui.say(f"{c.config.get('topic', '(senza argomento)')} · {len(c.messages)} messaggi · {c.status}\n{participant_label(c.config, 'codex')}: {c.config.get('codex_model', 'Non disponibile')} · {participant_label(c.config, 'ollama')}: {c.config.get('ollama_model', 'Non disponibile')}\nFile JSON: {entry.path}")
                    html_path = Store(entry.path).export(c, formats=["html"])[0]
                    ui.say(f"HTML aggiornato: {html_path.resolve()}")
                    if webbrowser.open(html_path.resolve().as_uri()):
                        ui.say("Aperto nel browser.")
                    else:
                        ui.say("Il browser non si è aperto. Puoi aprire il file HTML manualmente.")
            elif choice == "1":
                args = parser().parse_args(["run"])
                asyncio.run(execute(args, ui, preferences))
            else:
                cfg = preferences.load()
                entries, errors = scan_conversations(history_directories(cfg, preferences))
                for path, error in errors:
                    ui.say(f"Storico non leggibile: {path.name} — {error}. Il file resta intatto.")
                entry = ui.choose_history(entries)
                if entry is None:
                    continue
                extra = ui.integer("Quanti messaggi aggiuntivi?", cfg.max_turns, minimum=1)
                args = parser().parse_args(["resume", str(entry.path), "--turns", str(len(entry.conversation.messages) + extra)])
                args.additional_turns, args.confirm = extra, True
                asyncio.run(execute(args, ui))
        except KeyboardInterrupt:
            if selecting:
                ui.say("Uscita da AlterEcho.")
                return 130
            ui.say("Operazione interrotta. I messaggi e i parziali già ricevuti durante il dialogo sono salvati. Ritorno al menu.")
        except EOFError:
            ui.say("Terminale chiuso. Uscita da AlterEcho.")
            return 0
        except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
            ui.error(str(e))


def main(argv=None):
    # Help exits before constructing Terminal, so Windows streams need UTF-8 here too.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = parser()
    args = p.parse_args(argv)
    if args.action == "help":
        (p.commands[args.command] if args.command else p).print_help()
        return 0
    ui = Terminal()
    ui.say("AlterEcho · dialogo autonomo fra modelli")
    try:
        preferences = UserSettings()
        if args.action is None:
            return interactive_menu(ui, preferences)
        return asyncio.run(execute(args, ui, preferences))
    except KeyboardInterrupt:
        ui.say("Interrotto con Ctrl+C. Le risposte già completate e i parziali ricevuti sono salvati.")
        return 130
    except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
        ui.error(str(e))
        return 1
