import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx
from rich.console import Console
from rich.prompt import Prompt

from alterecho.config import Config, BridgeError
from alterecho.history import Conversation, Message
from alterecho.integrations import AdapterCatalog, new_profile
from alterecho.preferences import UserSettings
from alterecho.adapters.chat_api import ChatAPIAdapter
from alterecho.cli import execute, parser
from alterecho.storage import Store
from alterecho.ui import Terminal
from alterecho.adapters.base import Reply


def pair_config(**values):
    a, b = new_profile("openai", "API A"), new_profile("openrouter", "API B")
    a.update(model="actual-a", api_key_env="TEST_API_A")
    b.update(model="actual-b", api_key_env="TEST_API_B")
    return Config(adapter_pair={"codex": a, "ollama": b}, **values)


def response_events(content="risposta", finish="stop", done=True, model="actual-a"):
    events = [{"model": model, "choices": [{"delta": {"content": content}, "finish_reason": None}]},
              {"choices": [{"delta": {}, "finish_reason": finish}]},
              {"choices": [], "usage": {"prompt_tokens": 40, "completion_tokens": 3}}]
    text = "\n\n".join("data: " + json.dumps(e) for e in events) + "\n\n"
    return text + ("data: [DONE]\n\n" if done else "")


class ProfileSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"ALTERECHO_HOME": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def terminal(self):
        ui = Terminal()
        ui.console = Console(file=io.StringIO(), width=120, color_system=None)
        return ui

    def test_grouped_menu_keeps_new_first_and_archive_actions_separate(self):
        for inputs, expected in ((["1"], "1"), (["2", "1"], "2"), (["2", "2"], "3"),
                                 (["2", "3"], "4"), (["2", "0", "3"], "5"), (["0"], "6")):
            with self.subTest(inputs=inputs), patch.object(Prompt, "get_input", side_effect=inputs):
                self.assertEqual(self.terminal().main_menu(), expected)

    def test_add_api_profile_and_select_pair_without_connecting(self):
        settings = UserSettings()
        ui = self.terminal()
        with patch.object(Prompt, "get_input", side_effect=["2", "3", "API test", "TEST_OPENAI_KEY", "actual-a", "5", "3", "1", "0"]), patch("httpx.AsyncClient") as network:
            ui.adapter_settings(settings)
            network.assert_not_called()
        cfg = settings.load()
        self.assertEqual(cfg.adapter_pair["codex"]["provider"], "openai")
        self.assertEqual(cfg.adapter_pair["ollama"]["provider"], "ollama")
        self.assertEqual(len(AdapterCatalog().load()), 3)
        self.assertIn("TEST_OPENAI_KEY", AdapterCatalog().path.read_text(encoding="utf-8"))

    def test_invalid_profiles_and_incompatible_pairs_are_rejected(self):
        for changes in ({"api_key_env": "sk-actual-secret"}, {"url": "https://evil.example/v1"}, {"api_key": "secret"}):
            p = new_profile("openai", "API")
            p.update(changes)
            with self.assertRaises(BridgeError):
                AdapterCatalog().save([p])
        cfg = pair_config()
        cfg.adapter_pair = {"codex": new_profile("ollama", "A"), "ollama": new_profile("ollama", "B")}
        with self.assertRaises(BridgeError):
            cfg.validate()
        cfg.adapter_pair["ollama"] = new_profile("codex", "B")
        with self.assertRaises(BridgeError):
            cfg.validate()

    def test_legacy_profiles_remain_optional_and_catalog_changes_do_not_rewrite_history(self):
        cfg = Config()
        self.assertFalse(cfg.adapter_pair)
        profiles = AdapterCatalog().load(cfg)
        c = Conversation(pair_config().to_dict())
        before = c.to_dict()
        AdapterCatalog().save(profiles)
        profiles[0]["name"] = "Modificato"
        AdapterCatalog().save(profiles)
        self.assertEqual(c.to_dict(), before)


class APIAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_profile_pair_uses_selected_topic_and_codex_session(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ALTERECHO_HOME": tmp}):
            a, b = new_profile("codex", "Codex personale"), new_profile("ollama", "Locale")
            a['model'], b['model'] = 'actual-a', 'actual-local'
            cfg = Config(adapter_pair={'codex': a, 'ollama': b}, max_turns=2)
            settings = UserSettings()
            settings.save(cfg)
            topics = []

            class Native:
                def __init__(self, config): self.config = config
                async def start(self): return [{'model': 'actual-a'}]
                async def attach(self, c, checkpoint):
                    c.codex_thread_id = 'profile-thread'
                    topics.append(self.config.topic)
                    checkpoint()
                async def generate(self, c, checkpoint): return Reply('prima', 'actual-a')
                async def close(self): pass

            class Local:
                def __init__(self, config, speaker): self.config, self.speaker = config, speaker
                async def models(self): return ['actual-local']
                async def prepare(self): topics.append(self.config.topic)
                async def generate(self, c, checkpoint): return Reply('seconda', 'actual-local')
                async def close(self): pass

            ui = Terminal()
            ui.console = Console(file=io.StringIO(), width=120)
            with patch('alterecho.profile_runtime.CodexAdapter', Native), patch('alterecho.profile_runtime.OllamaAdapter', Local), patch('alterecho.profile_runtime.ChatAPIAdapter') as api, patch.object(Prompt, 'get_input', side_effect=['1', '1', 'Nuovo tema', '2', 's']):
                self.assertEqual(await execute(parser().parse_args(['run']), ui, settings), 0)
                api.assert_not_called()
            store = Store(next(Path(cfg.output_dir).rglob('*.json')))
            self.assertEqual(store.load().codex_thread_id, 'profile-thread')
            self.assertEqual(topics, ['Nuovo tema', 'Nuovo tema'])

    async def test_cancel_api_setup_makes_no_generation_or_saved_conversation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'ALTERECHO_HOME': tmp, 'TEST_API_A': 'fixture', 'TEST_API_B': 'fixture'}):
            cfg = pair_config()
            settings = UserSettings()
            settings.save(cfg)
            original = settings.path.read_bytes()
            methods = []

            def factory(config):
                result = {}
                for slot, profile in config.adapter_pair.items():
                    def handle(request, profile=profile):
                        methods.append(request.method)
                        return httpx.Response(200, json={'data': [{'id': profile['model']}]})
                    result[slot] = ChatAPIAdapter(config, profile, slot, httpx.MockTransport(handle))
                return result

            ui = MagicMock()
            ui.configure_profiles.return_value = False
            with patch('alterecho.profile_runtime.build_adapters', side_effect=factory):
                self.assertEqual(await execute(parser().parse_args(['run']), ui, settings), 0)
            self.assertEqual(methods, ['GET', 'GET'])
            self.assertEqual(settings.path.read_bytes(), original)
            self.assertFalse(list(Path(cfg.output_dir).rglob('*.json')))

    async def test_streaming_roles_usage_and_correct_endpoint(self):
        for slot, provider, suffix in (("codex", "openai", "/v1/chat/completions"), ("ollama", "openrouter", "/api/v1/chat/completions")):
            cfg = pair_config()
            profile = cfg.adapter_pair[slot]
            seen = []

            def handle(request):
                seen.append(request)
                return httpx.Response(200, text=response_events(model=profile["model"]))

            a = ChatAPIAdapter(cfg, profile, slot, httpx.MockTransport(handle))
            c = Conversation(cfg.to_dict(), messages=[Message("codex", "a", "primo", 1), Message("ollama", "b", "secondo", 1)])
            with patch.dict(os.environ, {profile["api_key_env"]: "fixture-key"}):
                try:
                    reply = await a.generate(c, lambda: None)
                finally:
                    await a.close()
            payload = json.loads(seen[0].content)
            self.assertEqual(seen[0].url.path, suffix)
            first = next(m for m in payload["messages"] if m["content"] == "primo")
            self.assertEqual(first["role"], "assistant" if slot == "codex" else "user")
            self.assertEqual(reply.usage, {"input_tokens": 40, "output_tokens": 3})
            self.assertNotIn("tools", payload)
            self.assertNotIn("reasoning_effort", payload)

    async def test_missing_key_makes_no_http_request(self):
        cfg = pair_config()
        calls = []
        a = ChatAPIAdapter(cfg, cfg.adapter_pair["codex"], "codex", httpx.MockTransport(lambda r: calls.append(r)))
        with patch.dict(os.environ, {"TEST_API_A": ""}):
            with self.assertRaisesRegex(BridgeError, "TEST_API_A"):
                await a.models()
        await a.close()
        self.assertFalse(calls)

    async def test_errors_never_echo_api_key_and_partial_is_preserved(self):
        cfg = pair_config()
        for body, status in (("fixture-key", 401), (response_events(done=False), 200), (response_events(finish="length"), 200)):
            a = ChatAPIAdapter(cfg, cfg.adapter_pair["codex"], "codex", httpx.MockTransport(lambda r: httpx.Response(status, text=body)))
            c = Conversation(cfg.to_dict())
            with patch.dict(os.environ, {"TEST_API_A": "fixture-key"}):
                with self.assertRaises(BridgeError) as error:
                    await a.generate(c, lambda: None)
                self.assertNotIn("fixture-key", str(error.exception))
                if status == 200:
                    self.assertEqual(c.partial["text"], "risposta")
            await a.close()

    async def test_tool_calls_are_rejected(self):
        cfg = pair_config()
        event = {"choices": [{"delta": {"tool_calls": [{"function": {"name": "execute"}}]}}]}
        a = ChatAPIAdapter(cfg, cfg.adapter_pair["codex"], "codex", httpx.MockTransport(lambda r: httpx.Response(200, text="data: " + json.dumps(event))))
        with patch.dict(os.environ, {"TEST_API_A": "fixture-key"}):
            with self.assertRaisesRegex(BridgeError, "strumenti"):
                await a.generate(Conversation(cfg.to_dict()), lambda: None)
        await a.close()

    async def test_profile_dialogue_and_resume_keep_full_memory_and_saved_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ALTERECHO_HOME": tmp, "TEST_API_A": "secret-fixture-A", "TEST_API_B": "secret-fixture-B"}):
            cfg = pair_config(max_turns=4)
            settings = UserSettings()
            settings.save(cfg)
            seen = []

            def factory(config):
                adapters = {}
                for slot, profile in config.adapter_pair.items():
                    def handle(request, slot=slot, profile=profile):
                        if request.url.path.endswith("/models"):
                            return httpx.Response(200, json={"data": [{"id": profile["model"]}]})
                        payload = json.loads(request.content)
                        seen.append((slot, payload["messages"]))
                        return httpx.Response(200, text=response_events(content="risposta " + str(len(seen)), model=profile["model"]))
                    adapters[slot] = ChatAPIAdapter(config, profile, slot, httpx.MockTransport(handle))
                return adapters

            ui = MagicMock()
            with patch("alterecho.profile_runtime.build_adapters", side_effect=factory):
                self.assertEqual(await execute(parser().parse_args(["run", "--non-interactive"]), ui, settings), 0)
                files = list(Path(cfg.output_dir).rglob("*.json"))
                self.assertEqual(len(files), 1)
                store = Store(files[0])
                before = store.load().to_dict()["messages"]
                self.assertEqual(await execute(parser().parse_args(["resume", str(store.path), "--turns", "6"]), ui), 0)
                saved = store.load()
            self.assertEqual(len(saved.messages), 6)
            self.assertEqual(saved.to_dict()["messages"][:4], before)
            self.assertEqual([len(messages) for _, messages in seen], [2, 2, 4, 4, 6, 6])
            for suffix in (".json", ".md", ".txt", ".html"):
                text = store.path.with_suffix(suffix).read_text(encoding="utf-8")
                self.assertNotIn("secret-fixture", text)
            rendered = store.path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("API A", rendered)
            self.assertIn("API B", rendered)
