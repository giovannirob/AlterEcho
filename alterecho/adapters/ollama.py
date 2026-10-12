import asyncio
import json
import time
import httpx

from .base import Reply
from ..config import Config, BridgeError
from ..history import ollama_history, now


class OllamaAdapter:
    def __init__(self, config: Config, transport=None):
        self.config = config
        self.client = httpx.AsyncClient(base_url=config.ollama_url.rstrip("/"), timeout=config.timeout, trust_env=False, transport=transport)

    async def request(self, method, path, **kwargs):
        try:
            response = await self.client.request(method, path, **kwargs)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise BridgeError(f"Ollama: {data['error']}")
            return data
        except (httpx.HTTPError, ValueError) as e:
            raise BridgeError(f"Connessione Ollama: {e}") from e

    async def models(self):
        return [m["name"] for m in (await self.request("GET", "/api/tags")).get("models", [])]

    async def prepare(self):
        if self.config.ollama_model not in await self.models():
            raise BridgeError(f"Modello Ollama non installato: {self.config.ollama_model}. Usa ollama pull esplicitamente.")
        data = await self.request("POST", "/api/show", json={"model": self.config.ollama_model})
        limits = [v for k, v in data.get("model_info", {}).items() if k.endswith(".context_length") and isinstance(v, int)]
        if limits and self.config.num_ctx > max(limits):
            raise BridgeError("num_ctx supera il contesto dichiarato dal modello Ollama.")
        # Unload any previously resident *other* model before generating the selected one.
        for m in (await self.request("GET", "/api/ps")).get("models", []):
            name = m.get("name", m.get("model"))
            if name and name != self.config.ollama_model:
                await self.request("POST", "/api/generate", json={"model": name, "keep_alive": 0})

    async def generate(self, conversation, checkpoint):
        cfg = self.config
        messages = ollama_history(cfg, conversation)
        payload = {"model": cfg.ollama_model, "messages": messages, "stream": True,
                   "think": False, "keep_alive": 0, "truncate": False, "shift": False,
                   "options": {**cfg.ollama_options, "temperature": cfg.temperature, "num_ctx": cfg.num_ctx, "num_predict": cfg.num_predict}}
        pieces = []
        last_checkpoint = 0.0
        final = None
        try:
            async with asyncio.timeout(cfg.timeout):
                async with self.client.stream("POST", "/api/chat", json=payload) as response:
                    if response.is_error:
                        await response.aread()
                        try:
                            detail = response.json().get("error", response.reason_phrase)
                        except (ValueError, AttributeError):
                            detail = response.reason_phrase
                        raise BridgeError(f"Ollama HTTP {response.status_code}: {detail}")
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        if data.get("error"):
                            raise BridgeError(f"Ollama: {data['error']}")
                        part = data.get("message", {}).get("content", "")
                        if part:
                            pieces.append(part)
                            conversation.partial = {"speaker": "ollama", "model": cfg.ollama_model, "text": "".join(pieces), "timestamp": now()}
                            if time.monotonic() - last_checkpoint > 0.5:
                                checkpoint()
                                last_checkpoint = time.monotonic()
                        if data.get("done"):
                            final = data
            if final is None:
                raise BridgeError("Stream Ollama interrotto senza evento done.")
            if final.get("done_reason") == "length" or final.get("eval_count", 0) >= cfg.num_predict:
                raise BridgeError("Limite di generazione Ollama raggiunto; risposta parziale conservata e non inoltrata.")
            text = "".join(pieces)
            if not text.strip():
                raise BridgeError("Risposta Ollama vuota.")
            usage = {"input_tokens": final.get("prompt_eval_count"), "output_tokens": final.get("eval_count")}
            if final.get("eval_duration") and final.get("eval_count") is not None:
                usage["tokens_per_second"] = final["eval_count"] / (final["eval_duration"] / 1e9)
            return Reply(text, final.get("model", cfg.ollama_model), usage)
        except (httpx.HTTPError, ValueError, TimeoutError) as e:
            raise BridgeError(f"Generazione Ollama interrotta: {e}") from e
        finally:
            if conversation.partial:
                checkpoint()

    async def close(self):
        await self.client.aclose()
