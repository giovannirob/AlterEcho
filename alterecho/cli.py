import argparse
import asyncio
from pathlib import Path
import sys
import webbrowser
from types import SimpleNamespace

from .config import Config, BridgeError
from .client import APIClient, Connection, RemotePreferences, configuration, to_config
from .history import Conversation, Message
from .ui import Terminal, safe_text


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
    p.add_argument("--server", help="Endpoint del server headless")
    sub = p.add_subparsers(dest="action", title="Comandi")
    commands = {}
    for name, help_text in [("run", "Nuovo dialogo: quattro scelte e conferma"), ("doctor", "Verifica connessioni e autenticazione, senza generare"), ("demo", "Simulazione sul server senza modelli né quote")]:
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
    resume.add_argument("path", help="ID conversazione o nome di uno storico sul server")
    resume.add_argument("--turns", type=int, required=True, help="Nuovo massimo TOTALE, inclusi i messaggi già salvati")
    resume.add_argument("--num-ctx", type=int, help="Contesto Ollama: preserva messaggi e sessione Codex")
    export = sub.add_parser("export", help="Esporta uno storico JSON in Markdown, TXT e HTML", description="Genera file autonomi accanto al JSON senza contattare i modelli.")
    commands["export"] = export
    export.add_argument("path", help="ID conversazione o nome di uno storico sul server")
    export.add_argument("--format", dest="formats", nargs="+", choices=["md", "txt", "html"], help="Genera soltanto i formati indicati; senza opzione genera tutti i formati")
    for name in ("status", "stop", "pause", "watch", "web", "connect", "serve", "down"):
        command = sub.add_parser(name, **({"help": "Avvia il server in background senza finestre (predefinito)",
                                          "description": "Avvia il server in background senza finestre. Non serve --detach; usa --foreground per diagnostica e servizi."} if name == "serve" else {}))
        commands[name] = command
        if name in {"stop", "pause", "watch"}:
            command.add_argument("id", help="ID conversazione sul server")
        if name == "serve":
            command.add_argument("--host")
            command.add_argument("--port", type=int)
            mode = command.add_mutually_exclusive_group()
            mode.add_argument("--detach", action="store_true", help="Avvio in background (predefinito)")
            mode.add_argument("--foreground", action="store_true", help="Primo piano per diagnostica, Docker e servizi")
        if name == "connect":
            command.add_argument("--token-file", help="File locale protetto contenente il token del servizio")
    for name in ("run", "resume"):
        commands[name].add_argument("--confirm-paid", action="store_true", help="Conferma esplicita dell'uso di API a consumo")
        commands[name].add_argument("--detach", action="store_true", help="Avvia sul server e torna al terminale")
    migration = sub.add_parser("migrate", help="Piano o copia verificata degli storici, senza spostare gli originali")
    commands["migrate"] = migration
    migration.add_argument("source")
    migration.add_argument("destination")
    migration.add_argument("--apply", action="store_true", help="Copia in una cartella nuova/vuota e verifica SHA-256")
    guide = sub.add_parser("help", help="Guida generale o di un comando")
    guide.add_argument("command", nargs="?", choices=list(commands), help="Comando da approfondire")
    p.commands = commands
    return p


def resolve_id(client, reference):
    from urllib.parse import quote
    entries = client.get("/conversations")
    matches = [c["id"] for c in entries if c["id"] == reference or c["id"] == Path(reference).stem or c.get("source_name") == Path(reference).name]
    if len(matches) != 1:
        raise BridgeError("Storico non trovato o ambiguo sul server. Usa l'ID da 'alterecho status' o dal browser; i percorsi locali del client non vengono caricati.")
    return quote(matches[0], safe="")


from .watching import watch


async def diagnose(cfg, ui, client=None):
    owned = client is None
    client = client or APIClient()
    try:
        result = client.post("/doctor")
        for p in result["providers"]:
            if p["available"]:
                ui.say(f"{p['name']}: connesso")
                for model in p["models"]:
                    ui.say("  " + (model["model"] if isinstance(model, dict) else model))
            else:
                ui.error(f"{p['name']}: {p.get('error', 'non disponibile')}")
        ui.say("Nessuna inferenza avviata. Le chiavi API restano nell'ambiente del server.")
        return int(any(not p["available"] for p in result["providers"]))
    finally:
        if owned:
            client.close()


async def execute(args, ui, preferences=None, client=None):
    owned = client is None
    client = client or APIClient(Connection(getattr(args, "server", None)))
    preferences = RemotePreferences(client)
    try:
        action = args.action
        if action == "doctor":
            return await diagnose(None, ui, client)
        if action == "status":
            state = client.get("/status")
            if state.get("managed"):
                from .managed import local_status
                local = local_status()
                if local and local["instance"] == state["managed"]["instance"]:
                    ui.say(f"Processo locale gestito: {local['pid']} · log: {local['log']}")
            ui.say(f"Server {state['status']} · AlterEcho {state['version']} · {state['history_count']} conversazioni")
            for p in state["providers"]:
                ui.say(f"{p['name']}: {'disponibile' if p['available'] else p.get('error', 'errore')}")
            for c in state["active"]:
                ui.say(f"{c['id']} · {c['status']} · {c['config']['topic']}")
            return 0
        if action in {"stop", "pause"}:
            ui.say(str(client.post(f"/conversations/{args.id}/{action}")))
            return 0
        if action == "watch":
            return await watch(client, resolve_id(client, args.id), ui)
        if action == "export":
            cid = resolve_id(client, args.path)
            for fmt in args.formats or ("md", "txt", "html"):
                response = client.request("GET", f"/conversations/{cid}/export/{fmt}")
                # Downloads are explicit exports, never operational histories.
                target = Path.cwd() / f"{cid}.{fmt}"
                if target.exists():
                    raise BridgeError(f"Esportazione già presente: {target}. Spostala prima di riprovare.")
                target.write_bytes(response.content)
                ui.say(f"Esportato: {target}")
            return 0
        if action == "resume":
            cid = resolve_id(client, args.path)
            # Validate overrides before any provider preflight.
            current = client.get(f"/conversations/{cid}")
            candidate = to_config(current["config"], client.get("/profiles"))
            candidate.max_turns = args.turns
            if args.num_ctx is not None:
                candidate.num_ctx = args.num_ctx
            candidate.validate()
            preflight = client.post(f"/conversations/{cid}/preflight")
            cfg = to_config(preflight["configuration"], client.get("/profiles"))
            completed = preflight["messages"]
            cfg.max_turns = completed + args.additional_turns if getattr(args, "additional_turns", None) is not None else args.turns
            cfg.num_ctx = args.num_ctx if args.num_ctx is not None else cfg.num_ctx
            cfg.validate()
            interactive = getattr(args, "confirm", False)
            if interactive and not ui.confirm_run(cfg, completed):
                ui.say("Ripresa annullata. Lo storico non è stato modificato.")
                return 0
            client.post(f"/conversations/{cid}/resume", {"max_turns": cfg.max_turns, "num_ctx": cfg.num_ctx,
                                                        "confirm_paid": interactive or getattr(args, "confirm_paid", False)})
        else:
            cfg = preferences.load()
            if getattr(args, "config", None):
                local = Config.load(args.config)
                # A local TOML supplies dialogue options, never server paths,
                # executable overrides, credentials or unregistered profiles.
                from .client import ClientConfig
                values = cfg.to_dict()
                patch = configuration(local)
                values.update({k: v for k, v in local.to_dict().items() if k in patch and k not in {"first", "roles", "positions", "participants"}})
                values.update(first=local.first, roles=local.roles, positions=local.positions)
                if local.adapter_pair:
                    values["adapter_pair"] = local.adapter_pair
                else:
                    for slot, model in (("codex", local.codex_model), ("ollama", local.ollama_model)):
                        if model:
                            values["adapter_pair"][slot]["model"] = model
                cfg = ClientConfig(**values)
            if getattr(args, "turns", None) is not None:
                cfg.max_turns = args.turns
            if getattr(args, "num_ctx", None) is not None:
                cfg.num_ctx = args.num_ctx
            interactive = action == "run" and not getattr(args, "non_interactive", False)
            if interactive:
                diagnostics = client.post("/doctor")["providers"]
                catalogs = {}
                for slot, p in cfg.adapter_pair.items():
                    d = next((d for d in diagnostics if d["profile_id"] == p["id"]), None)
                    if not d or not d["available"]:
                        raise BridgeError(f"{p['name']}: {d.get('error') if d else 'profilo non registrato'}")
                    catalogs[slot] = d["models"]
                if not ui.configure_profiles(cfg, catalogs):
                    ui.say("Avvio annullato. Nessun messaggio generato.")
                    return 0
                preferences.save(cfg)
            cfg.validate()
            result = client.post("/conversations", {"configuration": configuration(cfg), "demo": action == "demo",
                                                    "confirm_paid": interactive or getattr(args, "confirm_paid", False)})
            cid = result["id"]
        ui.say(f"Avviata sul server: {cid}")
        if getattr(args, "detach", False):
            return 0
        return await watch(client, cid, ui)
    finally:
        if owned:
            client.close()


def history_entries(client):
    entries = []
    profiles = client.get("/profiles")
    for c in client.get("/conversations"):
        cfg = to_config(c["config"], profiles)
        conversation = Conversation(cfg.to_dict(), id=c["id"], status=c["status"], created_at=c["created_at"])
        conversation.messages = [None] * c["message_count"]
        entries.append(SimpleNamespace(conversation=conversation, path=Path(c["id"]), modified=0))
    return entries


def interactive_menu(ui, preferences=None, client=None):
    owned = client is None
    client = client or APIClient()
    preferences = RemotePreferences(client)
    try:
        while True:
            selecting = True
            try:
                choice = ui.main_menu()
                selecting = False
                if choice == "6":
                    return 0
                if choice == "5":
                    ui.settings(preferences, lambda cfg: asyncio.run(diagnose(cfg, ui, client)))
                elif choice in {"2", "3", "4"}:
                    entry = ui.choose_history(history_entries(client))
                    if entry is None:
                        continue
                    cid = entry.conversation.id
                    if choice == "3":
                        if ui.confirm("Eliminare definitivamente la conversazione e gli export sul server?"):
                            client.request("DELETE", f"/conversations/{cid}")
                    elif choice == "4":
                        ui.say("La Web UI permette lettura ed esportazione HTML offline.")
                        webbrowser.open(client.connection.server + "/#conversation=" + cid)
                    else:
                        extra = ui.integer("Quanti messaggi aggiuntivi?", 10, minimum=1)
                        args = parser().parse_args(["resume", cid, "--turns", str(len(entry.conversation.messages) + extra)])
                        args.additional_turns, args.confirm = extra, True
                        asyncio.run(execute(args, ui, client=client))
                else:
                    asyncio.run(execute(parser().parse_args(["run"]), ui, client=client))
            except KeyboardInterrupt:
                if selecting:
                    return 130
                ui.say("Client scollegato. Le generazioni continuano sul server; usa stop per arrestarle.")
            except EOFError:
                return 0
            except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
                ui.error(str(e))
    finally:
        if owned:
            client.close()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = parser()
    args = p.parse_args(argv)
    if args.action == "help":
        (p.commands[args.command] if args.command else p).print_help()
        return 0
    ui = Terminal()
    try:
        if args.action == "serve":
            try:
                from .server import serve
            except ImportError as e:
                raise BridgeError("Installa il server con pip install 'alterecho[server]'.") from e
            if args.foreground:
                serve(args.host, args.port)
            else:
                from .managed import background
                from . import __version__
                result = background(args.host, args.port)
                ui.say(f"AlterEcho Server {__version__}\n✓ Server avviato\n  Indirizzo: {result['url']}\n  Processo: {result['pid']}\n  Modalità: background\n  Log: {result['log']}\n\nComandi: alterecho status · alterecho web · alterecho down")
            return 0
        if args.action == "down":
            if args.server:
                raise BridgeError("down gestisce solo il server locale di questo account e non accetta --server. Per servizi e Docker usa il relativo supervisore.")
            from .managed import down
            ui.say(f"Server locale arrestato (PID {down()}); checkpoint salvati.")
            return 0
        if args.action == "migrate":
            from .migration import migrate
            import json
            ui.say(json.dumps(migrate(args.source, args.destination, args.apply), ensure_ascii=False, indent=2))
            return 0
        connection = Connection(args.server)
        if args.action == "connect":
            connection.save(args.token_file)
            ui.say(f"Endpoint salvato: {connection.server}")
            return 0
        if args.action == "web":
            webbrowser.open(connection.server)
            ui.say(connection.server)
            return 0
        client = APIClient(connection)
        try:
            if args.action is None:
                return interactive_menu(ui, client=client)
            return asyncio.run(execute(args, ui, client=client))
        finally:
            client.close()
    except KeyboardInterrupt:
        ui.say("Server foreground arrestato; checkpoint conservati." if args.action == "serve" else "Client scollegato. Le conversazioni continuano sul server.")
        return 130
    except (BridgeError, OSError, ValueError, TypeError, KeyError) as e:
        ui.error(str(e))
        return 1
