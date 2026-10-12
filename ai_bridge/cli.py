import argparse
import asyncio
from pathlib import Path
import sys

from .config import Config, BridgeError
from .history import Conversation
from .storage import Store
from .coordinator import Coordinator
from .adapters.codex import CodexAdapter
from .adapters.ollama import OllamaAdapter
from .adapters.base import Reply
from .ui import Terminal


def parser():
    p = argparse.ArgumentParser(description="AI Bridge — dialogo automatico Codex ↔ Ollama")
    sub = p.add_subparsers(dest="action")
    for name, help_text in [("run", "Avvia configurazione interattiva o dialogo da file"), ("doctor", "Verifica connessioni e autenticazione, senza generare risposte"), ("demo", "Simulazione locale senza modelli né quote")]:
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--config", help="File TOML")
        if name != "doctor":
            command.add_argument("--turns", type=int, help="Massimo messaggi totali, non coppie")
        if name == "run":
            command.add_argument("--non-interactive", action="store_true", help="Usa la configurazione senza domande; avvia inferenza reale")
    resume = sub.add_parser("resume", help="Riprendi sessione e storico JSON verificati")
    resume.add_argument("path")
    resume.add_argument("--turns", type=int, required=True, help="Nuovo massimo TOTALE, inclusi messaggi già salvati")
    export = sub.add_parser("export", help="Esporta uno storico JSON in Markdown/TXT")
    export.add_argument("path")
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


async def execute(args, ui):
    action = args.action or "run"
    if action == "export":
        store = Store(args.path)
        conversation = store.load()
        store.export(conversation)
        ui.summary(conversation, store.path)
        return 0
    if action == "resume":
        store = Store(args.path)
        conversation = store.load()
        cfg = Config(**conversation.config)
        cfg.max_turns = args.turns
        if cfg.max_turns <= len(conversation.messages):
            raise BridgeError("--turns deve superare i messaggi già completati.")
        if conversation.messages and all(m.model.startswith("mock-") for m in conversation.messages):
            raise BridgeError("Gli storici demo non possono essere ripresi con modelli reali.")
        cfg.validate()
        conversation.config = cfg.to_dict()
    else:
        cfg = Config.load(args.config) if getattr(args, "config", None) else Config()
        if getattr(args, "turns", None) is not None:
            cfg.max_turns = args.turns
        cfg.validate()
        conversation = None
        store = None
    if action == "demo":
        ui.mock = True
        cfg.codex_model = "mock-codex"
        conversation = Conversation(cfg.to_dict())
        store = Store(Path(cfg.output_dir) / f"demo-{conversation.id}.json")
        await Coordinator(cfg, conversation, {s: DemoAdapter(s) for s in ("codex", "ollama")}, store, ui).run()
        return 0
    codex, ollama = CodexAdapter(cfg), OllamaAdapter(cfg)
    try:
        ui.say("Connessioni: verifica Codex/ChatGPT e Ollama… (nessuna generazione)")
        codex_models = await codex.start()
        ollama_models = await ollama.models()
        ui.say("Codex: connesso, autenticazione ChatGPT · Ollama: connesso")
        if action == "doctor":
            ui.say("Catalogo Codex (la presenza non garantisce la quota/accesso per una futura richiesta):")
            for m in codex_models:
                ui.say(f"  {m['model']} · {m.get('displayName', '')}")
            ui.say("Ollama installati:\n  " + "\n  ".join(ollama_models))
            ui.say("Nessuna inferenza avviata, nessun modello locale caricato.")
            return 0
        if action == "run":
            if not getattr(args, "non_interactive", False):
                ui.configure(cfg, codex_models, ollama_models)
            elif not cfg.codex_model:
                raise BridgeError("Imposta codex_model nel TOML; i valori accettati sono mostrati da doctor.")
            cfg.validate()
            conversation = Conversation(cfg.to_dict())
            store = Store(Path(cfg.output_dir) / f"{conversation.id}.json")
        ui.say(f"Salvataggio automatico: {store.path.resolve()}")
        store.save(conversation)
        await codex.attach(conversation, lambda: store.save(conversation))
        if conversation.pending and conversation.pending.get("speaker") == "ollama":
            # Ollama has no remote persistent session: retry from the saved canonical history.
            conversation.pending = None
            store.save(conversation)
        await ollama.prepare()
        await Coordinator(cfg, conversation, {"codex": codex, "ollama": ollama}, store, ui).run()
        return 0 if conversation.status == "completed" else 1
    except asyncio.CancelledError:
        if conversation:
            conversation.status = "interrupted"
        raise
    except Exception as e:
        if conversation:
            conversation.status = "stopped"
            conversation.error = str(e)
        raise
    finally:
        await codex.close()
        await ollama.close()
        if store and conversation:
            store.save(conversation)
            store.export(conversation)


def main():
    ui = Terminal()
    args = parser().parse_args()
    ui.say("AI Bridge · Codex ↔ Ollama")
    try:
        code = asyncio.run(execute(args, ui))
    except KeyboardInterrupt:
        ui.say("Interrotto con Ctrl+C. Le risposte già completate e i parziali ricevuti sono salvati.")
        code = 130
    except (BridgeError, OSError, ValueError, TypeError) as e:
        ui.error(str(e))
        code = 1
    sys.exit(code)
