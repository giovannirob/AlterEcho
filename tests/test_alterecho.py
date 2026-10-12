import asyncio
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import httpx

from alterecho.config import Config, BridgeError
from alterecho.history import Conversation, Message, instructions, ollama_history
from alterecho.storage import Store
from alterecho.coordinator import Coordinator
from alterecho.adapters.base import Reply
from alterecho.adapters.ollama import OllamaAdapter
from alterecho.adapters.codex import CodexAdapter, child_environment, command, SAFE_CONFIG, resolve_codex
from alterecho.ui import safe_text
from alterecho.cli import parser, execute


class SilentUI:
    def say(self, *args): pass
    def waiting(self, *args): pass
    def message(self, *args): pass
    def error(self, *args): pass
    def summary(self, *args): pass


class MockAdapter:
    def __init__(self, name):
        self.name = name
        self.histories = []

    async def generate(self, conversation, checkpoint):
        self.histories.append([m.text for m in conversation.messages])
        return Reply(f"{self.name}-{len(conversation.messages)}", self.name)


class LogicTests(unittest.TestCase):
    def test_new_and_legacy_cli_names_share_the_same_help(self):
        outputs = []
        for module in ("alterecho", "ai_bridge"):
            result = subprocess.run([sys.executable, "-m", module, "--help"],
                                    cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage: alterecho", result.stdout)
            self.assertIn("AlterEcho", result.stdout)
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_desktop_codex_without_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp)/"OpenAI"/"Codex"/"bin"/"installed-version"/"codex.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"fixture")
            with patch("alterecho.adapters.codex.shutil.which", return_value=None), patch("alterecho.adapters.codex.sys.platform", "win32"):
                self.assertEqual(resolve_codex(Config(), {"LOCALAPPDATA": tmp, "PATH": ""}), str(exe))

    def test_desktop_codex_uses_profile_if_localappdata_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp)/"AppData"/"Local"/"OpenAI"/"Codex"/"bin"/"installed-version"/"codex.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"fixture")
            with patch("alterecho.adapters.codex.shutil.which", return_value=None), patch("alterecho.adapters.codex.sys.platform", "win32"):
                self.assertEqual(resolve_codex(Config(), {"USERPROFILE": tmp, "PATH": ""}), str(exe))

    def test_explicit_codex_override_is_respected(self):
        with patch("alterecho.adapters.codex.shutil.which", return_value=None), patch("alterecho.adapters.codex.desktop_codex_candidates") as discover:
            with self.assertRaisesRegex(BridgeError, "codex_binary"):
                resolve_codex(Config(codex_binary="missing-custom-codex"), {})
            discover.assert_not_called()

    def test_local_only(self):
        for url in ["http://127.0.0.1:11434", "http://[::1]:11434", "http://localhost:11434"]:
            Config(ollama_url=url).validate()
        for url in ["http://example.com", "http://127.0.0.1.evil", "https://localhost", "http://x:y@localhost", "http://localhost/api"]:
            with self.assertRaises(BridgeError):
                Config(ollama_url=url).validate()

    def test_validation(self):
        for values in [{"max_turns": 0}, {"delay": -1}, {"timeout": 0}, {"num_ctx": 600}, {"ollama_options": {"num_ctx": 500}}, {"temperature": float("nan")}]:
            with self.assertRaises(BridgeError):
                Config(**values).validate()

    def test_roles_no_duplicates(self):
        cfg = Config()
        c = Conversation(cfg.to_dict(), messages=[Message("codex", "a", "ciao", 1), Message("ollama", "b", "salve", 1), Message("codex", "a", "domanda", 1)])
        h = ollama_history(cfg, c)
        self.assertEqual([m["role"] for m in h], ["system", "user", "assistant", "user"])
        self.assertEqual([m["content"] for m in h[1:]], ["ciao", "salve", "domanda"])
        cfg.first = "ollama"
        c.messages = [Message("ollama", "b", "ciao", 1), Message("codex", "a", "salve", 1)]
        self.assertEqual([m["role"] for m in ollama_history(cfg, c)], ["system", "user", "assistant", "user"])

    def test_blind_and_debate(self):
        cfg = Config(mode="blind", codex_model="secret-A", ollama_model="secret-B")
        for speaker in ("codex", "ollama"):
            text = instructions(cfg, speaker).lower()
            self.assertNotIn("secret", text)
            self.assertNotIn("ollama", text)
            self.assertNotIn("codex", text)
            self.assertNotIn("intelligenza artificiale", text)
        cfg.mode = "debate"
        self.assertIn(cfg.positions["codex"], instructions(cfg, "codex"))

    def test_storage_unicode_exports_and_partial(self):
        cfg = Config()
        c = Conversation(cfg.to_dict(), messages=[Message("codex", "model", "è una prova\n**ciao**", 0.4)])
        c.partial = {"text": "risposta incompleta"}
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp)/"conv.json")
            s.save(c)
            s.export(c)
            loaded = s.load()
            self.assertEqual(loaded.to_dict(), c.to_dict())
            for ext in ["md", "txt"]:
                text = s.path.with_suffix("."+ext).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("# AlterEcho" if ext == "md" else "AlterEcho"))
                self.assertIn(c.messages[0].text, text)
                self.assertIn("risposta incompleta", text)
            self.assertFalse(s.path.with_name("conv.json.tmp").exists())

    def test_corrupt_history_rejected(self):
        c = Conversation(Config().to_dict(), messages=[Message("ollama", "x", "bad role", 1)])
        with self.assertRaises(BridgeError): Conversation.from_dict(c.to_dict())

    def test_terminal_controls_not_executed(self):
        self.assertEqual(safe_text("hello\x1b[31mred\x1b[0m\x07"), "hellored")

    def test_no_paid_environment(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "do-not-use", "CODEX_API_KEY": "do-not-use"}):
            env = child_environment(Config())
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("CODEX_API_KEY", env)
        self.assertFalse(SAFE_CONFIG["features.shell_tool"])
        self.assertFalse(SAFE_CONFIG["features.unified_exec"])


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_resume_larger_context_preserves_thread_and_messages(self):
        cfg = Config(first="ollama", codex_model="test-codex")
        c = Conversation(cfg.to_dict(), messages=[
            Message("ollama" if i % 2 == 0 else "codex", "real-model", "x" * 1100, 0.1)
            for i in range(4)
        ], codex_thread_id="existing-thread", codex_turn_id="last-turn", codex_synced_messages=4,
            status="stopped", pending={"speaker": "ollama"})
        original = c.to_dict()
        instances = {}

        class FakeCodex(MockAdapter):
            def __init__(self, config):
                super().__init__("codex")
                instances["codex"] = self
            async def start(self): return []
            async def attach(self, conversation, checkpoint):
                self.thread = conversation.codex_thread_id
                self.turn = conversation.codex_turn_id
            async def close(self): pass

        class FakeOllama(MockAdapter):
            def __init__(self, config):
                super().__init__("ollama")
                self.config = config
                instances["ollama"] = self
            async def models(self): return [self.config.ollama_model]
            async def prepare(self): pass
            async def generate(self, conversation, checkpoint):
                return await super().generate(conversation, checkpoint)
            async def close(self): pass

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/"c.json")
            store.save(c)
            args = parser().parse_args(["resume", str(store.path), "--turns", "5", "--num-ctx", "8192"])
            with patch("alterecho.cli.CodexAdapter", FakeCodex), patch("alterecho.cli.OllamaAdapter", FakeOllama):
                self.assertEqual(await execute(args, SilentUI()), 0)
            saved = store.load().to_dict()
            self.assertEqual(saved["messages"][:4], original["messages"])
            self.assertEqual(saved["config"]["num_ctx"], 8192)
            self.assertEqual(saved["codex_thread_id"], "existing-thread")
            self.assertEqual(saved["codex_turn_id"], "last-turn")
            self.assertEqual(instances["codex"].histories, [])
            self.assertEqual(instances["ollama"].histories, [[m["text"] for m in original["messages"]]])
            self.assertEqual(saved["messages"][4]["speaker"], "ollama")

    async def test_invalid_resume_context_does_not_modify_saved_history(self):
        c = Conversation(Config(codex_model="test-codex").to_dict())
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/"c.json")
            store.save(c)
            before = store.path.read_bytes()
            args = parser().parse_args(["resume", str(store.path), "--turns", "5", "--num-ctx", "600"])
            with patch("alterecho.cli.CodexAdapter") as codex, patch("alterecho.cli.OllamaAdapter") as ollama:
                with self.assertRaises(BridgeError):
                    await execute(args, SilentUI())
                codex.assert_not_called()
                ollama.assert_not_called()
            self.assertEqual(store.path.read_bytes(), before)

    async def test_roundtrip_multi_turn_and_resume(self):
        cfg = Config(max_turns=6)
        c = Conversation(cfg.to_dict())
        a, b = MockAdapter("codex"), MockAdapter("ollama")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/"c.json")
            await Coordinator(cfg, c, {"codex": a, "ollama": b}, store, SilentUI()).run()
            self.assertEqual(len(c.messages), 6)
            self.assertEqual([len(x) for x in a.histories], [0, 2, 4])
            self.assertEqual([len(x) for x in b.histories], [1, 3, 5])
            cfg.max_turns = 8
            loaded = store.load()
            loaded.config = cfg.to_dict()
            await Coordinator(cfg, loaded, {"codex": a, "ollama": b}, store, SilentUI()).run()
            self.assertEqual(len(loaded.messages), 8)
            self.assertEqual(loaded.messages[:6], c.messages)

    async def test_interrupt_preserves_completed(self):
        cfg = Config(max_turns=4)
        c = Conversation(cfg.to_dict())
        class Interrupt:
            async def generate(self, conversation, checkpoint):
                conversation.partial = {"text": "parziale"}
                raise asyncio.CancelledError()
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp)/"c.json")
            with self.assertRaises(asyncio.CancelledError):
                await Coordinator(cfg, c, {"codex": MockAdapter("codex"), "ollama": Interrupt()}, s, SilentUI()).run()
            self.assertEqual(len(s.load().messages), 1)
            self.assertEqual(s.load().status, "interrupted")
            self.assertEqual(s.load().partial["text"], "parziale")

    async def test_error_stops_without_retry(self):
        cfg = Config()
        c = Conversation(cfg.to_dict())
        class Failure:
            calls = 0
            async def generate(self, conversation, checkpoint):
                self.calls += 1
                raise BridgeError("quota esaurita")
        fail = Failure()
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(Path(tmp)/"c.json")
            await Coordinator(cfg, c, {"codex": fail}, s, SilentUI()).run()
            self.assertEqual(fail.calls, 1)
            self.assertEqual(s.load().error, "quota esaurita")

    async def test_ollama_payload_usage_and_memory(self):
        cfg = Config()
        c = Conversation(cfg.to_dict(), messages=[Message("codex", "x", "testo esatto", 0.1)])
        seen = []
        def handle(request):
            data = json.loads(request.content)
            seen.append(data)
            chunks = [{"message": {"content": "ciao "}}, {"message": {"content": "è"}}, {"done": True, "done_reason": "stop", "prompt_eval_count": 50, "eval_count": 4, "eval_duration": 1000000000}]
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in chunks))
        adapter = OllamaAdapter(cfg, httpx.MockTransport(handle))
        try:
            reply = await adapter.generate(c, lambda: None)
            self.assertEqual(reply.text, "ciao è")
            self.assertEqual(reply.usage["tokens_per_second"], 4)
            self.assertEqual(seen[0]["messages"][-1], {"role": "user", "content": "testo esatto"})
            self.assertEqual(seen[0]["keep_alive"], 0)
            self.assertFalse(seen[0]["truncate"])
            self.assertFalse(seen[0]["shift"])
            self.assertNotIn("tools", seen[0])
        finally: await adapter.close()

    async def test_large_history_reaches_ollama_without_byte_guard(self):
        cfg = Config(first="ollama", num_ctx=4096)
        c = Conversation(cfg.to_dict(), messages=[
            Message("ollama" if i % 2 == 0 else "codex", "real-model", "è" * 3000, 0.1)
            for i in range(4)
        ])
        expected = ollama_history(cfg, c)
        before = c.to_dict()["messages"]
        seen = []
        def handle(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, text=json.dumps({"message": {"content": "continuo"}, "done": True, "done_reason": "stop"}))
        a = OllamaAdapter(cfg, httpx.MockTransport(handle))
        try:
            reply = await a.generate(c, lambda: None)
            self.assertEqual(reply.text, "continuo")
            self.assertEqual(seen[0]["messages"], expected)
            self.assertEqual(seen[0]["options"]["num_ctx"], 4096)
            self.assertFalse(seen[0]["truncate"])
            self.assertFalse(seen[0]["shift"])
            self.assertEqual(c.to_dict()["messages"], before)
        finally: await a.close()

    async def test_real_ollama_context_error_preserves_history(self):
        cfg = Config(first="ollama", max_turns=5)
        c = Conversation(cfg.to_dict(), messages=[
            Message("ollama" if i % 2 == 0 else "codex", "real-model", "x" * 3000, 0.1)
            for i in range(4)
        ])
        before = c.to_dict()["messages"]
        a = OllamaAdapter(cfg, httpx.MockTransport(lambda req: httpx.Response(400, json={"error": "the prompt exceeds the context length"})))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = Store(Path(tmp)/"c.json")
                await Coordinator(cfg, c, {"ollama": a}, store, SilentUI()).run()
                saved = store.load()
                self.assertEqual(saved.to_dict()["messages"], before)
                self.assertEqual(saved.status, "stopped")
                self.assertIn("the prompt exceeds the context length", saved.error)
        finally: await a.close()

    async def test_ollama_disconnect_and_generation_limit(self):
        for chunks in [[{"message": {"content": "parziale"}}], [{"message": {"content": "parziale"}}, {"done": True, "done_reason": "length"}]]:
            adapter = OllamaAdapter(Config(), httpx.MockTransport(lambda req: httpx.Response(200, text="\n".join(json.dumps(x) for x in chunks))))
            c = Conversation(Config().to_dict(), messages=[Message("codex", "x", "ciao", 1)])
            try:
                with self.assertRaises(BridgeError): await adapter.generate(c, lambda: None)
                self.assertEqual(c.partial["text"], "parziale")
            finally: await adapter.close()

    async def test_unload_other_models(self):
        cfg = Config()
        seen = []
        def handle(req):
            seen.append((req.url.path, json.loads(req.content) if req.content else None))
            if req.url.path == "/api/tags": return httpx.Response(200, json={"models": [{"name": cfg.ollama_model}]})
            if req.url.path == "/api/ps": return httpx.Response(200, json={"models": [{"name": "other-model"}]})
            return httpx.Response(200, json={})
        a = OllamaAdapter(cfg, httpx.MockTransport(handle))
        try:
            await a.prepare()
            self.assertIn(("/api/generate", {"model": "other-model", "keep_alive": 0}), seen)
        finally: await a.close()

    async def test_codex_stdio_persistent_json_protocol(self):
        # Legacy byte-budget values must not stop a persistent Codex turn.
        cfg = Config(codex_model="test-codex", timeout=10, codex_context_budget=1)
        a = CodexAdapter(cfg)
        c = Conversation(cfg.to_dict())
        cmd = [sys.executable, str(Path(__file__).with_name("fake_server.py").resolve())]
        with patch("alterecho.adapters.codex.command", return_value=cmd):
            try:
                catalog = await a.start()
                self.assertEqual(catalog[0]["model"], "test-codex")
                await a.attach(c, lambda: None)
                first = await a.generate(c, lambda: None)
                self.assertEqual(first.text, "Risposta persistente 1")
                self.assertEqual(first.usage["output_tokens"], 5)
                c.messages.append(Message("codex", first.model, first.text, 0.1))
                c.codex_turn_id = c.pending["turn_id"]
                c.codex_synced_messages = 1
                c.pending = c.partial = None
                c.messages.append(Message("ollama", "b", "Risposta da inoltrare esattamente", 0.1))
                second = await a.generate(c, lambda: None)
                self.assertEqual(second.text, "Risposta persistente 2")
                self.assertEqual(c.codex_thread_id, "thread-test")
                self.assertEqual(c.pending["input"], c.messages[-1].text)
            finally: await a.close()

    async def test_resume_refuses_external_changes_and_incomplete(self):
        cfg = Config(codex_model="test-codex")
        a = CodexAdapter(cfg)
        c = Conversation(cfg.to_dict(), codex_thread_id="thread", codex_turn_id="old")
        with self.assertRaises(BridgeError):
            await a._verify_resume(c, lambda: None, {"turns": [{"id": "new", "status": "completed"}]})
        c.pending = {"speaker": "codex", "input": "ciao", "turn_id": "new"}
        with self.assertRaises(BridgeError):
            await a._verify_resume(c, lambda: None, {"turns": [{"id": "new", "status": "interrupted", "items": [{"type": "userMessage", "content": [{"type": "text", "text": "ciao"}]}]}]})

    async def test_recover_completed_pending_codex(self):
        cfg = Config(codex_model="test-codex")
        c = Conversation(cfg.to_dict(), pending={"speaker": "codex", "input": "ciao", "turn_id": "t1"})
        turn = {"id": "t1", "status": "completed", "items": [{"type": "userMessage", "content": [{"type": "text", "text": "ciao"}]}, {"type": "agentMessage", "text": "salve"}]}
        await CodexAdapter(cfg)._verify_resume(c, lambda: None, {"turns": [turn]})
        self.assertEqual(c.messages[0].text, "salve")
        self.assertEqual(c.codex_synced_messages, 1)
        self.assertIsNone(c.pending)

    async def test_pending_is_committed_only_with_message(self):
        cfg = Config(codex_model="test-codex", max_turns=1, timeout=10)
        a = CodexAdapter(cfg)
        c = Conversation(cfg.to_dict())
        cmd = [sys.executable, str(Path(__file__).with_name("fake_server.py").resolve())]
        with tempfile.TemporaryDirectory() as tmp, patch("alterecho.adapters.codex.command", return_value=cmd):
            s = Store(Path(tmp)/"c.json")
            try:
                await a.start()
                await a.attach(c, lambda: s.save(c))
                await Coordinator(cfg, c, {"codex": a}, s, SilentUI()).run()
                self.assertEqual(s.load().codex_turn_id, "t1")
                self.assertEqual(s.load().codex_synced_messages, 1)
                self.assertIsNone(s.load().pending)
                await a.attach(c, lambda: s.save(c))
            finally: await a.close()

    async def test_api_key_account_rejected(self):
        a = CodexAdapter(Config())
        cmd = [sys.executable, str(Path(__file__).with_name("fake_server.py").resolve())]
        original = a.rpc
        async def rpc(method, params):
            if method == "account/read": return {"account": {"type": "apiKey"}}
            return await original(method, params)
        with patch("alterecho.adapters.codex.command", return_value=cmd), patch.object(a, "rpc", side_effect=rpc):
            try:
                with self.assertRaisesRegex(BridgeError, "ChatGPT"):
                    await a.start()
            finally: await a.close()

    async def test_network_and_http_errors_stop(self):
        def timeout(req): raise httpx.ReadTimeout("mock timeout")
        for handler in [timeout, lambda req: httpx.Response(500, text="server error")]:
            a = OllamaAdapter(Config(), httpx.MockTransport(handler))
            try:
                with self.assertRaises(BridgeError): await a.models()
            finally: await a.close()

    async def test_empty_thread_is_recreated_without_duplicating_context(self):
        cfg = Config(codex_model="test-codex")
        a = CodexAdapter(cfg)
        a.catalog = [{"model": "test-codex"}]
        c = Conversation(cfg.to_dict(), codex_thread_id="empty-old")
        methods = []
        async def rpc(method, params):
            methods.append(method)
            return {"thread": {"id": "empty-new"}}
        with patch.object(a, "rpc", side_effect=rpc):
            await a.attach(c, lambda: None)
        self.assertEqual(methods, ["thread/start"])
        self.assertEqual(c.codex_thread_id, "empty-new")

    async def test_codex_tools_quota_timeout_stop(self):
        cmd = [sys.executable, str(Path(__file__).with_name("fake_server.py").resolve())]
        for incoming, expected in [("REQUEST_TOOL", "rifiutata"), ("FAIL_QUOTA", "failed"), ("STALL", "Timeout")]:
            cfg = Config(codex_model="test-codex", first="ollama", timeout=0.5)
            c = Conversation(cfg.to_dict(), messages=[Message("ollama", "b", incoming, 0)])
            a = CodexAdapter(cfg)
            with patch("alterecho.adapters.codex.command", return_value=cmd):
                try:
                    await a.start()
                    await a.attach(c, lambda: None)
                    with self.assertRaisesRegex(BridgeError, expected):
                        await a.generate(c, lambda: None)
                    self.assertEqual(len(c.messages), 1)
                finally: await a.close()

    async def test_pending_id_missing_from_rollout_refused(self):
        cfg = Config()
        c = Conversation(cfg.to_dict(), codex_turn_id="old", pending={"speaker": "codex", "turn_id": "new", "input": "ciao"})
        with self.assertRaises(BridgeError):
            await CodexAdapter(cfg)._verify_resume(c, lambda: None, {"turns": [{"id": "old"}]})


if __name__ == "__main__": unittest.main()
