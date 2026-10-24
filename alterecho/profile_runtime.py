"""Conversation lifecycle for explicitly selected adapter profiles."""
import asyncio
from pathlib import Path

from .config import Config, BridgeError
from .history import Conversation
from .storage import Store
from .preferences import resumed_config
from .coordinator import Coordinator
from .adapters.codex import CodexAdapter
from .adapters.ollama import OllamaAdapter
from .adapters.chat_api import ChatAPIAdapter


def build_adapters(cfg):
    adapters = {}
    for slot, profile in cfg.adapter_pair.items():
        local = Config(**cfg.to_dict())
        if profile["provider"] == "codex":
            local.codex_binary, local.codex_model = profile["binary"], profile["model"]
            adapters[slot] = CodexAdapter(local)
        elif profile["provider"] == "ollama":
            local.ollama_url, local.ollama_model = profile["url"], profile["model"]
            adapters[slot] = OllamaAdapter(local, speaker=slot)
        else:
            adapters[slot] = ChatAPIAdapter(local, profile, slot)
    return adapters


async def catalog(adapter, profile):
    return await adapter.start() if profile["provider"] == "codex" else await adapter.models()


async def close_adapters(adapters, ui):
    results = await asyncio.gather(*(a.close() for a in adapters.values()), return_exceptions=True)
    for adapter, result in zip(adapters.values(), results):
        if isinstance(result, BaseException):
            ui.say(f"Chiusura adapter: {type(result).__name__}.")
        if getattr(adapter, "memory_notice", None):
            ui.say(adapter.memory_notice)


async def diagnose_profiles(cfg, ui):
    cfg.validate()
    adapters = build_adapters(cfg)
    try:
        results = await asyncio.gather(*(catalog(adapters[s], p) for s, p in cfg.adapter_pair.items()), return_exceptions=True)
        for profile, result in zip(cfg.adapter_pair.values(), results):
            if isinstance(result, BaseException):
                ui.error(f"{profile['name']}: {result}")
            else:
                ui.say(f"{profile['name']}: connesso · {len(result)} modelli nel catalogo")
        ui.say("Nessuna generazione avviata.")
        return int(any(isinstance(r, BaseException) for r in results))
    finally:
        await close_adapters(adapters, ui)


async def execute_profiles(args, ui, preferences=None, cfg=None, conversation=None, store=None):
    if cfg is None:
        cfg = resumed_config(conversation, store.path)
    if args.action == "resume":
        cfg.max_turns = args.turns
        if getattr(args, "num_ctx", None) is not None:
            cfg.num_ctx = args.num_ctx
    cfg.validate()
    adapters = build_adapters(cfg)
    persist = False
    try:
        ui.say("Verifica degli adapter selezionati (nessuna generazione)…")
        catalogs = {}
        for slot, profile in cfg.adapter_pair.items():
            catalogs[slot] = await catalog(adapters[slot], profile)
        if args.action == "run":
            if not getattr(args, "non_interactive", False) and not ui.configure_profiles(cfg, catalogs):
                ui.say("Avvio annullato. Nessun messaggio generato.")
                return 0
        for slot, profile in cfg.adapter_pair.items():
            values = [m["model"] for m in catalogs[slot]] if profile["provider"] == "codex" else catalogs[slot]
            if not profile["model"] or profile["model"] not in values:
                raise BridgeError(f"{profile['name']}: scegli un modello disponibile nel catalogo.")
            adapter = adapters[slot]
            adapter.config = Config(**cfg.to_dict())
            if profile["provider"] == "codex":
                adapter.config.codex_model = profile["model"]
                adapter.config.codex_binary = profile["binary"]
            elif profile["provider"] == "ollama":
                adapter.config.ollama_model = profile["model"]
                adapter.config.ollama_url = profile["url"]
            else:
                adapter.profile = dict(profile)
        cfg.codex_model, cfg.ollama_model = cfg.adapter_pair["codex"]["model"], cfg.adapter_pair["ollama"]["model"]
        cfg.validate()
        if args.action == "run":
            if preferences and not getattr(args, "config", None):
                preferences.save(cfg)
            conversation = Conversation(cfg.to_dict())
            store = Store(Path(cfg.output_dir) / conversation.id / f"{conversation.id}.json")
            persist = True
            store.save(conversation)
        for slot, adapter in adapters.items():
            if cfg.adapter_pair[slot]["provider"] == "codex":
                await adapter.attach(conversation, (lambda: store.save(conversation)) if persist else (lambda: None))
        if args.action == "resume":
            if getattr(args, "additional_turns", None) is not None:
                cfg.max_turns = len(conversation.messages) + args.additional_turns
            if getattr(args, "confirm", False) and not ui.confirm_run(cfg, len(conversation.messages)):
                ui.say("Ripresa annullata. Lo storico non è stato modificato.")
                return 0
            if cfg.max_turns <= len(conversation.messages):
                raise BridgeError("Il massimo totale deve superare i messaggi salvati.")
        conversation.config = cfg.to_dict()
        persist = True
        store.save(conversation)
        # Stateless HTTP providers rebuild memory from canonical messages. An
        # incomplete turn can be retried only after native Codex verification.
        conversation.pending = None
        for slot, adapter in adapters.items():
            if cfg.adapter_pair[slot]["provider"] == "ollama":
                await adapter.prepare()
        ui.say(f"Salvataggio automatico: {store.path.resolve()}")
        ui.labels = {s: p["name"] for s, p in cfg.adapter_pair.items()}
        await Coordinator(cfg, conversation, adapters, store, ui).run()
        return 0 if conversation.status == "completed" else 1
    except asyncio.CancelledError:
        if persist:
            conversation.status = "interrupted"
        raise
    except Exception as e:
        if persist:
            conversation.status, conversation.error = "stopped", str(e)
        raise
    finally:
        try:
            await close_adapters(adapters, ui)
        finally:
            if persist:
                store.save(conversation)
                store.export(conversation)
