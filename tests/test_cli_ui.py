import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from rich.console import Console
from rich.prompt import Prompt

from alterecho.cli import main, parser, interactive_menu
from tests.server_harness import execute, diagnose
from alterecho.config import BridgeError, Config
from alterecho.history import Conversation, Message
from alterecho.paths import config_dir, data_dir
from alterecho.preferences import UserSettings, history_directories, resumed_config
from alterecho.storage import Store, scan_conversations
from alterecho.ui import Terminal
from alterecho.i18n import set_language, language
from alterecho.adapters.base import Reply


ROOT = Path(__file__).resolve().parents[1]
CATALOG = [{"model": "actual-codex", "defaultReasoningEffort": "medium",
            "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}]


class IsolatedSettings:
    def setUp(self):
        previous_language = language()
        set_language("it")
        self.addCleanup(set_language, previous_language)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, {"ALTERECHO_HOME": str(self.root / "personal"), "ALTERECHO_LANG": "it"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def ui(self):
        terminal = Terminal()
        terminal.console = Console(file=io.StringIO(), width=120, color_system=None)
        return terminal


class ParserTests(IsolatedSettings, unittest.TestCase):
    def test_general_and_contextual_help_use_same_parser_without_providers(self):
        with patch("alterecho.profile_runtime.CodexAdapter") as codex, patch("alterecho.profile_runtime.OllamaAdapter") as ollama:
            for command in [None, "run", "doctor", "demo", "resume", "export"]:
                outputs = []
                for argv in (["help"] + ([command] if command else []), ([command] if command else []) + ["--help"]):
                    with contextlib.redirect_stdout(io.StringIO()) as stream:
                        try:
                            code = main(argv)
                        except SystemExit as e:
                            code = e.code
                        self.assertEqual(code, 0)
                        outputs.append(stream.getvalue())
                self.assertEqual(outputs[0], outputs[1])
            codex.assert_not_called()
            ollama.assert_not_called()
        self.assertFalse(config_dir().exists())

    def test_no_args_opens_menu_and_exit_needs_no_settings_or_connections(self):
        ui = self.ui()
        with patch("alterecho.cli.Terminal", return_value=ui), patch.object(Prompt, "get_input", return_value="0"), patch("alterecho.profile_runtime.CodexAdapter") as codex:
            self.assertEqual(main([]), 0)
        codex.assert_not_called()
        self.assertIn("Nuova conversazione", ui.console.file.getvalue())
        self.assertFalse(config_dir().exists())

    def test_old_brand_entrypoints_removed(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(set(metadata["project"]["scripts"]), {"alterecho"})
        for file in ("__init__.py", "__main__.py", "cli.py"):
            self.assertFalse((ROOT / "ai_bridge" / file).exists())

    def test_invalid_user_home_reports_error_without_traceback_or_provider(self):
        ui = self.ui()
        with patch.dict(os.environ, {"ALTERECHO_HOME": "relative"}), patch("alterecho.cli.Terminal", return_value=ui), patch("alterecho.profile_runtime.CodexAdapter") as provider:
            self.assertEqual(main([]), 1)
        self.assertIn("percorso assoluto", ui.console.file.getvalue())
        provider.assert_not_called()

    def test_advanced_options_keep_semantics(self):
        p = parser()
        args = p.parse_args(["run", "--config", "custom.toml", "--non-interactive", "--turns", "8", "--num-ctx", "8192"])
        self.assertEqual((args.config, args.non_interactive, args.turns, args.num_ctx), ("custom.toml", True, 8, 8192))
        args = p.parse_args(["resume", "chat.json", "--turns", "12"])
        self.assertEqual((args.path, args.turns), ("chat.json", 12))

    def test_resume_menu_converts_additional_to_total(self):
        cfg = Config(codex_model="actual-codex")
        c = Conversation(cfg.to_dict(), messages=[Message("codex", "actual-codex", "test", 1)])
        store = Store(Path(cfg.output_dir) / "chat.json")
        store.save(c)
        ui = MagicMock()
        ui.main_menu.side_effect = ["2", "6"]
        ui.choose_history.side_effect = lambda entries: entries[0]
        ui.integer.return_value = 3
        runner = AsyncMock(return_value=0)
        with patch("alterecho.cli.history_entries", return_value=[type("Entry", (), {"conversation": c})()]), patch("alterecho.cli.execute", runner):
            self.assertEqual(interactive_menu(ui, UserSettings()), 0)
        args = runner.call_args.args[0]
        self.assertEqual((args.turns, args.additional_turns, args.confirm), (4, 3, True))

    def test_menu_error_returns_to_menu_and_ctrl_c_exits_cleanly(self):
        ui = MagicMock()
        ui.main_menu.side_effect = ["1", "6"]
        with patch("alterecho.cli.execute", AsyncMock(side_effect=BridgeError("Ollama offline"))):
            self.assertEqual(interactive_menu(ui, UserSettings()), 0)
        ui.error.assert_called_once_with("Ollama offline")
        ui.main_menu.side_effect = KeyboardInterrupt
        self.assertEqual(interactive_menu(ui, UserSettings()), 130)

    def test_ctrl_c_during_operation_returns_to_menu(self):
        ui = MagicMock()
        ui.main_menu.side_effect = ["1", "6"]
        with patch("alterecho.cli.execute", new=MagicMock(side_effect=KeyboardInterrupt)):
            self.assertEqual(interactive_menu(ui, UserSettings()), 0)


class PreferencesTests(IsolatedSettings, unittest.TestCase):
    def test_settings_persist_without_modifying_example(self):
        original = (ROOT / "config.example.toml").read_bytes()
        settings = UserSettings()
        cfg = Config(codex_model="remembered", ollama_model="local", mode="blind", delay=2)
        settings.save(cfg)
        loaded = UserSettings().load()
        self.assertEqual(loaded.to_dict(), cfg.to_dict())
        self.assertEqual((ROOT / "config.example.toml").read_bytes(), original)
        self.assertFalse(settings.path.with_name("config.json.tmp").exists())

    def test_legacy_toml_migration_non_destructive_and_only_when_no_profile(self):
        legacy = self.root / "config.toml"
        legacy.write_text('topic = "Vecchio tema"\noutput_dir = "old/chats"', encoding="utf-8")
        original = legacy.read_bytes()
        settings = UserSettings()
        with patch("alterecho.preferences.project_root", return_value=self.root):
            cfg = settings.load()
            self.assertEqual(settings.migrated_from, legacy)
            self.assertEqual(cfg.output_dir, str(self.root / "old/chats"))
            self.assertFalse(settings.path.exists())
            cfg.topic = "Nuovo tema"
            settings.save(cfg)
            self.assertEqual(settings.load().topic, "Nuovo tema")
        self.assertEqual(legacy.read_bytes(), original)

    def test_invalid_profile_preserved(self):
        settings = UserSettings()
        settings.path.parent.mkdir(parents=True)
        settings.path.write_text('{"schema_version":9}', encoding="utf-8")
        original = settings.path.read_bytes()
        with self.assertRaisesRegex(BridgeError, "was not modified"):
            settings.load()
        self.assertEqual(settings.path.read_bytes(), original)

    def test_previous_output_directories_remain_in_history_menu_after_change_and_reset(self):
        settings = UserSettings()
        cfg = Config(output_dir=str(self.root / "first"))
        settings.save(cfg)
        cfg.output_dir = str(self.root / "second")
        settings.save(cfg)
        settings.save(Config())
        roots = history_directories(settings.load(), settings)
        self.assertIn(self.root / "first", roots)
        self.assertIn(self.root / "second", roots)

    def test_absolute_defaults_do_not_depend_on_cwd_and_toml_uses_own_base(self):
        before = Config().to_dict()
        old = Path.cwd()
        try:
            os.chdir(self.root)
            self.assertEqual(Config().to_dict(), before)
            toml = self.root / "custom.toml"
            toml.write_text('output_dir="chats"\ncodex_work_dir="isolated"', encoding="utf-8")
            cfg = Config.load(toml)
        finally:
            os.chdir(old)
        self.assertEqual(cfg.output_dir, str(self.root / "chats"))
        self.assertEqual(cfg.codex_work_dir, str(self.root / "isolated"))

    def test_relative_portable_home_rejected(self):
        with patch.dict(os.environ, {"ALTERECHO_HOME": "relative"}):
            with self.assertRaisesRegex(ValueError, "absolute"):
                Config()

    def test_legacy_resume_keeps_old_codex_cwd_and_actual_history_location(self):
        cfg = Config().to_dict()
        del cfg["codex_work_dir"]
        cfg["output_dir"] = "outputs/conversations"
        c = Conversation(cfg)
        file = self.root / "outputs/conversations/old.json"
        actual = resumed_config(c, file)
        self.assertEqual(actual.codex_work_dir, str(self.root / "work/codex-dialogue"))
        self.assertEqual(actual.output_dir, str(file.parent))
        self.assertNotIn("codex_work_dir", c.config)

    def test_history_scan_sorted_deduped_and_corrupt_files_kept(self):
        directory = self.root / "chats"
        cfg = Config(codex_model="actual-codex")
        for name, timestamp in [("new", 20), ("old", 10)]:
            store = Store(directory / f"{name}.json")
            store.save(Conversation(cfg.to_dict()))
            os.utime(store.path, (timestamp, timestamp))
        bad = directory / "invalid.json"
        bad.write_text("broken", encoding="utf-8")
        entries, errors = scan_conversations([directory, directory, self.root / "missing"])
        self.assertEqual([entry.path.stem for entry in entries], ["new", "old"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(bad.read_text(), "broken")
        with patch("alterecho.preferences.project_root", return_value=self.root):
            self.assertIn(self.root / "outputs/conversations", history_directories(cfg))


class MenuTests(IsolatedSettings, unittest.TestCase):
    def test_new_conversation_only_four_choices_then_confirm(self):
        ui = self.ui()
        cfg = Config()
        with patch.object(Prompt, "get_input", side_effect=["1", "1", "Un tema", "6", "S"]) as inputs:
            self.assertTrue(ui.configure(cfg, CATALOG, ["installed-model"]))
        self.assertEqual(inputs.call_count, 5)
        self.assertEqual((cfg.ollama_model, cfg.codex_model, cfg.topic, cfg.max_turns), ("installed-model", "actual-codex", "Un tema", 6))
        self.assertEqual(cfg.codex_effort, "medium")
        self.assertIn("Nuova conversazione", ui.console.file.getvalue())

    def test_defaults_models_remembered_and_invalid_numeric_input_reprompts(self):
        ui = self.ui()
        cfg = Config(ollama_model="second", codex_model="actual-codex", codex_effort="medium")
        with patch.object(Prompt, "get_input", side_effect=["", "", "", "zero", "0", "5", "n"]):
            self.assertFalse(ui.configure(cfg, CATALOG, ["first", "second"]))
        self.assertEqual(cfg.ollama_model, "second")
        self.assertIn("numero intero", ui.console.file.getvalue())

    def test_all_settings_groups_persist_and_diagnostics_generate_nothing(self):
        ui = self.ui()
        settings = UserSettings()
        diagnostics = MagicMock()
        inputs = ["1", "1", "2", "Favorevole", "Contrario", "2", "Curioso", "Prudente", "3", "2", "0",
                  "2", "2", "4", "codex", "-", "3", "http://127.0.0.1:11434", "8192", "600", "0,8", '{"top_p":0.9}', "10m", "n", "0",
                  "3", "1", "14", "240", "1,5", "2", str(self.root / "salvataggi"), "0", "4", "1", "0", "0"]
        with patch.object(Prompt, "get_input", side_effect=inputs):
            ui.settings(settings, diagnostics)
        cfg = settings.load()
        self.assertEqual((cfg.mode, cfg.roles["codex"], cfg.positions["ollama"], cfg.codex_effort), ("debate", "Curioso", "Contrario", "medium"))
        self.assertEqual((cfg.num_ctx, cfg.num_predict, cfg.temperature, cfg.delay, cfg.timeout, cfg.max_turns, cfg.first), (8192, 600, 0.8, 1.5, 240, 14, "ollama"))
        self.assertEqual(cfg.ollama_options, {"top_p": 0.9})
        self.assertEqual((cfg.ollama_keep_alive, cfg.ollama_unload_on_exit), ("10m", False))
        self.assertEqual(cfg.output_dir, str(self.root / "salvataggi"))
        diagnostics.assert_called_once()

    def test_settings_submenus_go_back_without_saving_or_connecting(self):
        ui = self.ui()
        settings = UserSettings()
        diagnostics = MagicMock()
        inputs = ["1", "0", "2", "1", "0", "0", "3", "0", "4", "0", "0"]
        with patch.object(Prompt, "get_input", side_effect=inputs):
            ui.settings(settings, diagnostics)
        self.assertFalse(settings.path.exists())
        diagnostics.assert_not_called()
        output = ui.console.file.getvalue()
        for title in ("Conversazione", "Modelli e adapter", "Esecuzione e salvataggi", "Diagnostica e manutenzione", "ADAPTER E INTEGRAZIONI"):
            self.assertIn(title, output)

    def test_invalid_settings_are_not_persisted_and_reset_keeps_history(self):
        ui = self.ui()
        settings = UserSettings()
        cfg = Config(mode="blind", delay=3)
        settings.save(cfg)
        original = settings.path.read_bytes()
        with patch.object(Prompt, "get_input", side_effect=["2", "3", "http://evil.example", "4096", "512", "0.7", "{}", "-1", "s", "0", "0"]):
            ui.settings(settings, MagicMock())
        self.assertEqual(settings.path.read_bytes(), original)
        store = Store(Path(cfg.output_dir) / "chat.json")
        store.save(Conversation(cfg.to_dict()))
        saved = store.path.read_bytes()
        with patch.object(Prompt, "get_input", side_effect=["4", "2", "s", "0", "0"]):
            ui.settings(settings, MagicMock())
        self.assertEqual(settings.load().to_dict(), Config().to_dict())
        self.assertEqual(store.path.read_bytes(), saved)

    def test_resume_listing_contains_metadata_and_can_go_back(self):
        cfg = Config(codex_model="actual-codex")
        store = Store(self.root / "chat.json")
        store.save(Conversation(cfg.to_dict(), messages=[Message("codex", "actual-codex", "test", 1)], status="completed"))
        entries, _ = scan_conversations([self.root])
        ui = self.ui()
        with patch.object(Prompt, "get_input", return_value="0"):
            self.assertIsNone(ui.choose_history(entries))
        for text in (cfg.topic, cfg.codex_model, cfg.ollama_model, "1 messaggio", "Completata"):
            self.assertIn(text, ui.console.file.getvalue())


class FlowTests(IsolatedSettings, unittest.IsolatedAsyncioTestCase):
    def adapters(self, events, *, recover=False, broken=False):
        class Codex:
            def __init__(self, cfg): self.cfg = cfg
            async def start(self): events.append("codex-connect"); return CATALOG
            async def attach(self, c, checkpoint):
                events.append("verify-thread")
                if broken: raise BridgeError("Sessione Codex mancante")
                if recover:
                    c.messages.append(Message("codex", "actual-codex", "Recuperato", 0))
                    c.codex_synced_messages = len(c.messages)
                    c.pending = None
                    checkpoint()
                c.codex_thread_id = "same-thread"
            async def generate(self, c, checkpoint):
                events.append("codex-generate")
                return Reply("Codex risponde", "actual-codex")
            async def close(self): events.append("codex-close")
        class Ollama:
            def __init__(self, cfg, speaker="ollama"): self.cfg = cfg
            async def models(self): events.append("ollama-connect"); return [self.cfg.ollama_model]
            async def prepare(self): events.append("prepare")
            async def generate(self, c, checkpoint):
                events.append("ollama-generate")
                return Reply("Ollama risponde", self.cfg.ollama_model)
            async def close(self): events.append("ollama-close")
        return Codex, Ollama

    def resume(self, cfg=None):
        cfg = cfg or Config(codex_model="actual-codex", codex_effort="medium")
        c = Conversation(cfg.to_dict(), messages=[Message("codex", "actual-codex", "Prima risposta", 1)], codex_thread_id="same-thread", codex_turn_id="last-turn", codex_synced_messages=1)
        store = Store(self.root / "existing.json")
        store.save(c)
        args = parser().parse_args(["resume", str(store.path), "--turns", "3"])
        args.confirm, args.additional_turns = True, 2
        return store, args

    async def test_cancel_new_closes_both_and_creates_no_history_or_settings(self):
        events = []
        codex, ollama = self.adapters(events)
        ui = self.ui()
        with patch("alterecho.profile_runtime.CodexAdapter", codex), patch("alterecho.profile_runtime.OllamaAdapter", ollama), patch.object(Prompt, "get_input", side_effect=["1", "1", "Tema", "4", "n"]):
            self.assertEqual(await execute(parser().parse_args(["run"]), ui, UserSettings()), 0)
        self.assertNotIn("prepare", events)
        self.assertNotIn("verify-thread", events)
        self.assertFalse(list(data_dir().rglob("*.json")))
        self.assertFalse(config_dir().exists())
        self.assertIn("codex-close", events)
        self.assertIn("ollama-close", events)

    async def test_confirm_new_generates_requested_count_and_remembers_models(self):
        events = []
        codex, ollama = self.adapters(events)
        ui = self.ui()
        settings = UserSettings()
        with patch("alterecho.profile_runtime.CodexAdapter", codex), patch("alterecho.profile_runtime.OllamaAdapter", ollama), patch.object(Prompt, "get_input", side_effect=["1", "1", "Tema", "4", "s"]):
            self.assertEqual(await execute(parser().parse_args(["run"]), ui, settings), 0)
        cfg = settings.load()
        self.assertEqual(cfg.codex_model, "actual-codex")
        entries, errors = scan_conversations([cfg.output_dir])
        self.assertFalse(errors)
        self.assertEqual([m.speaker for m in entries[0].conversation.messages], ["codex", "ollama", "codex", "ollama"])
        self.assertEqual(entries[0].conversation.status, "completed")
        self.assertTrue(entries[0].path.with_suffix(".md").exists())

    async def test_resume_preflight_then_confirmation_then_added_messages(self):
        store, args = self.resume()
        events = []
        codex, ollama = self.adapters(events)
        ui = self.ui()
        def confirm(cfg, completed):
            events.append("confirm")
            self.assertEqual((completed, cfg.max_turns), (1, 3))
            return True
        with patch("alterecho.profile_runtime.CodexAdapter", codex), patch("alterecho.profile_runtime.OllamaAdapter", ollama), patch.object(ui, "confirm_run", side_effect=confirm):
            self.assertEqual(await execute(args, ui), 0)
        self.assertLess(events.index("verify-thread"), events.index("confirm"))
        self.assertLess(events.index("confirm"), events.index("prepare"))
        loaded = store.load()
        self.assertEqual(len(loaded.messages), 3)
        self.assertEqual(loaded.messages[0].text, "Prima risposta")
        self.assertEqual(loaded.codex_thread_id, "same-thread")

    async def test_resume_cancel_or_missing_thread_does_not_change_file(self):
        for broken in (False, True):
            store, args = self.resume()
            original = store.path.read_bytes()
            events = []
            codex, ollama = self.adapters(events, broken=broken)
            ui = self.ui()
            with patch("alterecho.profile_runtime.CodexAdapter", codex), patch("alterecho.profile_runtime.OllamaAdapter", ollama), patch.object(ui, "confirm_run", return_value=False) as confirm:
                if broken:
                    with self.assertRaisesRegex(BridgeError, "Sessione"):
                        await execute(args, ui)
                    confirm.assert_not_called()
                else:
                    self.assertEqual(await execute(args, ui), 0)
            self.assertEqual(store.path.read_bytes(), original)
            self.assertNotIn("prepare", events)
            self.assertFalse(store.path.with_suffix(".md").exists())

    async def test_additional_limit_accounts_for_remote_recovery(self):
        cfg = Config(first="ollama", codex_model="actual-codex", codex_effort="medium")
        store, args = self.resume(cfg)
        c = Conversation(cfg.to_dict(), messages=[Message("ollama", cfg.ollama_model, "Domanda", 1)], pending={"speaker": "codex"}, codex_thread_id="same-thread")
        store.save(c)
        events = []
        codex, ollama = self.adapters(events, recover=True)
        ui = self.ui()
        def confirm(config, completed):
            self.assertEqual((completed, config.max_turns), (2, 4))
            return True
        with patch("alterecho.profile_runtime.CodexAdapter", codex), patch("alterecho.profile_runtime.OllamaAdapter", ollama), patch.object(ui, "confirm_run", side_effect=confirm):
            self.assertEqual(await execute(args, ui), 0)
        self.assertEqual(len(store.load().messages), 4)

    async def test_diagnostics_reports_ollama_even_when_codex_fails(self):
        codex = MagicMock()
        codex.start = AsyncMock(side_effect=BridgeError("Accesso ChatGPT mancante"))
        codex.close = AsyncMock()
        ollama = MagicMock()
        ollama.models = AsyncMock(return_value=["qwen-installed"])
        ollama.close = AsyncMock()
        ui = self.ui()
        with patch("alterecho.profile_runtime.CodexAdapter", return_value=codex), patch("alterecho.profile_runtime.OllamaAdapter", return_value=ollama):
            self.assertEqual(await diagnose(Config(), ui), 1)
        output = ui.console.file.getvalue()
        self.assertIn("ChatGPT mancante", output)
        self.assertIn("Ollama: connesso", output)
        self.assertIn("qwen-installed", output)
        codex.close.assert_awaited_once()
        ollama.close.assert_awaited_once()
        ollama.prepare.assert_not_called()
        codex.generate.assert_not_called()


class LauncherTests(IsolatedSettings, unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Launcher Windows")
    def test_launcher_and_fresh_powershell_from_unrelated_directory_without_user_path_changes(self):
        bin_dir = self.root / "launcher with spaces"
        install = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install-user.ps1"), "-InstallDir", str(bin_dir), "-Yes", "-NoPath"], capture_output=True, timeout=30)
        self.assertEqual(install.returncode, 0, install.stderr.decode(errors="replace"))
        other = self.root / "unrelated"
        other.mkdir()
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
        # This process has no activated virtualenv and invokes only the global-style command.
        result = subprocess.run(["powershell", "-NoProfile", "-Command", "alterecho help; exit $LASTEXITCODE"], cwd=other, env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertIn(b"Uso: alterecho", result.stdout)
        result = subprocess.run([str(bin_dir / "alterecho.exe")], input=b"4\n", cwd=other, env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"Nuova conversazione", result.stdout)
        # A launcher installed on another machine must never fall back to a local engine.
        result = subprocess.run([str(bin_dir / "alterecho.exe"), "--server", "http://127.0.0.1:1", "demo", "--turns", "3"], cwd=other, env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"alterecho serve", result.stdout)
        self.assertFalse(list(data_dir().rglob("*.json")))
        self.assertEqual(list(other.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
