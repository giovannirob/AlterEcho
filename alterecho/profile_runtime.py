"""Server-side provider factory; no UI or independent conversation loop."""
import asyncio

from .config import Config
from .integrations import new_profile
from copy import deepcopy
from .adapters.codex import CodexAdapter
from .adapters.ollama import OllamaAdapter
from .adapters.chat_api import ChatAPIAdapter


def build_adapters(cfg):
    adapters = {}
    for slot, profile in effective_pair(cfg).items():
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


async def close_adapters(adapters):
    return await asyncio.gather(*(a.close() for a in adapters.values()), return_exceptions=True)


SLOTS = {"A": "codex", "B": "ollama"}


def effective_pair(cfg):
    if cfg.adapter_pair:
        return deepcopy(cfg.adapter_pair)
    a, b = new_profile("codex", "Codex"), new_profile("ollama", "Ollama")
    a.update(id="codex-default", model=cfg.codex_model, binary=cfg.codex_binary)
    b.update(id="ollama-default", model=cfg.ollama_model, url=cfg.ollama_url)
    return {"codex": a, "ollama": b}


def normalize_config(cfg):
    cfg = Config(**cfg.to_dict())
    cfg.adapter_pair = effective_pair(cfg)
    cfg.codex_model, cfg.ollama_model = (cfg.adapter_pair[s]["model"] for s in ("codex", "ollama"))
    cfg.validate()
    return cfg


class DemoAdapter:
    """Server-only explicit simulation; never a connection fallback."""
    def __init__(self, speaker):
        self.speaker = speaker

    async def generate(self, conversation, checkpoint):
        from .adapters.base import Reply
        await asyncio.sleep(.03)
        n = len(conversation.messages) + 1
        return Reply(f"Messaggio simulato {n}. Ho ricevuto {n - 1} messaggi di storico. Argomento: {conversation.config['topic']}", f"mock-{self.speaker}")

    async def close(self):
        pass
