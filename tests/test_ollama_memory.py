import asyncio
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from alterecho.adapters.ollama import OllamaAdapter
from alterecho.adapters.base import Reply
from alterecho.config import Config, BridgeError
from alterecho.history import Conversation, Message
from alterecho.coordinator import Coordinator
from alterecho.storage import Store


class MemoryConfigTests(unittest.TestCase):
    def test_supported_values_and_rejected_types(self):
        for value in (-1, 0, "5m", "10m"):
            Config(ollama_keep_alive=value).validate()
        for value in (True, False, -1.0, None, [], {}, "-1", "0", "5minutes", "forever", "1d", 300):
            with self.subTest(value=value), self.assertRaises(BridgeError):
                Config(ollama_keep_alive=value).validate()
        for value in (0, 1, "true", None):
            with self.assertRaises(BridgeError):
                Config(ollama_unload_on_exit=value).validate()

    def test_legacy_history_and_toml_use_new_defaults_without_rewriting(self):
        data = Conversation(Config().to_dict()).to_dict()
        data["config"].pop("ollama_keep_alive")
        data["config"].pop("ollama_unload_on_exit")
        loaded = Conversation.from_dict(data)
        cfg = Config(**loaded.config)
        self.assertEqual((cfg.ollama_keep_alive, cfg.ollama_unload_on_exit), (-1, True))
        self.assertNotIn("ollama_keep_alive", loaded.config)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.toml"
            for content in ('topic="Vecchio"', 'ollama_keep_alive="5m"\nollama_unload_on_exit=false'):
                file.write_text(content, encoding="utf-8")
                cfg = Config.load(file)
                self.assertEqual(file.read_text(encoding="utf-8"), content)
            self.assertEqual((cfg.ollama_keep_alive, cfg.ollama_unload_on_exit), ("5m", False))


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    def server(self, cfg, preloaded=False, fail_close=False):
        calls = []
        state = {"resident": preloaded, "turns": 0, "ps": 0}

        def handle(request):
            payload = json.loads(request.content) if request.content else None
            calls.append((request.url.path, payload))
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": cfg.ollama_model}]})
            if request.url.path == "/api/show":
                return httpx.Response(200, json={})
            if request.url.path == "/api/ps":
                state["ps"] += 1
                if fail_close and state["ps"] > 1:
                    raise httpx.ReadTimeout("fixture")
                models = [{"name": "external-model"}]
                if state["resident"]:
                    models.append({"name": cfg.ollama_model})
                return httpx.Response(200, json={"models": models})
            if request.url.path == "/api/chat":
                load = 9_000_000_000 if not state["resident"] else 1_000_000
                state["resident"] = payload["keep_alive"] != 0
                state["turns"] += 1
                return httpx.Response(200, json={"message": {"content": "risposta"}, "done": True,
                    "load_duration": load, "eval_duration": 2_000_000_000,
                    "prompt_eval_count": 20, "eval_count": 10})
            raise AssertionError(f"Richiesta distruttiva o inattesa: {request.url.path}")

        return httpx.MockTransport(handle), calls, state

    async def test_two_ollama_turns_reuse_model_across_codex_turn(self):
        cfg = Config()
        transport, calls, state = self.server(cfg)
        adapter = OllamaAdapter(cfg, transport)
        c = Conversation(cfg.to_dict())
        await adapter.prepare()
        first = await adapter.generate(c, lambda: None)
        c.messages.extend([Message("codex", "mock", "domanda", 1), Message("ollama", "mock", first.text, 1), Message("codex", "mock", "continua", 1)])
        # A Codex turn issues no Ollama request and does not expire an infinite keep_alive.
        self.assertTrue(state["resident"])
        self.assertEqual(state["ps"], 1)
        second = await adapter.generate(c, lambda: None)
        self.assertEqual(first.usage["load_seconds"], 9)
        self.assertEqual(second.usage["load_seconds"], .001)
        self.assertEqual(second.usage["generation_seconds"], 2)
        self.assertEqual([p["keep_alive"] for path, p in calls if path == "/api/chat"], [-1, -1])
        await adapter.close()
        await adapter.close()
        self.assertEqual(state["ps"], 2)
        self.assertTrue(adapter.client.is_closed)
        self.assertIn("non eseguito", adapter.memory_notice)
        self.assertTrue(state["resident"])

    async def test_native_keep_alive_values_are_sent_unchanged(self):
        for value in (-1, "5m", "10m", 0):
            cfg = Config(ollama_keep_alive=value)
            transport, calls, state = self.server(cfg)
            a = OllamaAdapter(cfg, transport)
            await a.prepare()
            await a.generate(Conversation(cfg.to_dict()), lambda: None)
            await a.close()
            self.assertEqual(next(p["keep_alive"] for path, p in calls if path == "/api/chat"), value)
            self.assertEqual(state["resident"], value != 0)

    async def test_preloaded_model_is_preserved_without_close_poll(self):
        cfg = Config()
        transport, calls, state = self.server(cfg, preloaded=True)
        a = OllamaAdapter(cfg, transport)
        await a.prepare()
        await a.generate(Conversation(cfg.to_dict()), lambda: None)
        await a.close()
        self.assertEqual(state["ps"], 1)
        self.assertIn("già residente", a.memory_notice)
        self.assertTrue(state["resident"])

    async def test_unload_disabled_and_diagnostics_do_not_run_cleanup(self):
        for generated in (True, False):
            cfg = Config(ollama_unload_on_exit=False)
            transport, calls, state = self.server(cfg)
            a = OllamaAdapter(cfg, transport)
            await a.prepare()
            if generated:
                await a.generate(Conversation(cfg.to_dict()), lambda: None)
            await a.close()
            self.assertEqual(state["ps"], 1)
            self.assertIsNone(a.memory_notice)

    async def test_close_network_failure_does_not_mask_saved_reply(self):
        cfg = Config()
        transport, calls, state = self.server(cfg, fail_close=True)
        a = OllamaAdapter(cfg, transport)
        await a.prepare()
        reply = await a.generate(Conversation(cfg.to_dict()), lambda: None)
        await a.close()
        self.assertEqual(reply.text, "risposta")
        self.assertTrue(a.client.is_closed)
        self.assertIn("non riuscito", a.memory_notice)

    async def test_ctrl_c_preserves_partial_and_closes_without_unload(self):
        cfg = Config(first="ollama")
        base, calls, state = self.server(cfg)

        class InterruptedStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"message":{"content":"parziale"}}\n'
                raise asyncio.CancelledError()

        def handle(request):
            if request.url.path == "/api/chat":
                state["resident"] = True
                return httpx.Response(200, stream=InterruptedStream())
            return base.handle_request(request)

        class UI:
            def waiting(self, *a): pass
            def message(self, *a): pass
            def error(self, *a): pass
            def summary(self, *a): pass

        a = OllamaAdapter(cfg, httpx.MockTransport(handle))
        await a.prepare()
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "chat.json")
            c = Conversation(cfg.to_dict())
            with self.assertRaises(asyncio.CancelledError):
                try:
                    await Coordinator(cfg, c, {"ollama": a}, store, UI()).run()
                finally:
                    await a.close()
            self.assertEqual(store.load().status, "interrupted")
            self.assertEqual(store.load().partial["text"], "parziale")
        self.assertTrue(a.client.is_closed)
        self.assertTrue(state["resident"])
