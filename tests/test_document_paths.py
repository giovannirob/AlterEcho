import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from alterecho.paths import documents_dir, conversations_dir
from alterecho.config import Config
from alterecho.preferences import UserSettings, history_directories
from alterecho.storage import Store
from alterecho.cli import parser
from tests.server_harness import execute


class DocumentPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"ALTERECHO_HOME": "", "XDG_CONFIG_HOME": str(self.root / "config")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_windows_uses_redirected_native_documents(self):
        redirected = self.root / "OneDrive" / "Documenti"
        with patch("alterecho.paths.sys.platform", "win32"), patch("alterecho.paths._windows_documents", return_value=redirected):
            self.assertEqual(Config().output_dir, str(redirected / "AlterEcho/conversations"))

    def test_linux_reads_xdg_documents_without_shell_execution(self):
        directory = self.root / "config"
        directory.mkdir()
        file = directory / "user-dirs.dirs"
        file.write_text('XDG_DOCUMENTS_DIR="$HOME/Documenti personali"\n', encoding="utf-8")
        with patch("alterecho.paths.sys.platform", "linux"), patch("pathlib.Path.home", return_value=self.root):
            self.assertEqual(documents_dir(), self.root / "Documenti personali")
            file.write_text('XDG_DOCUMENTS_DIR="$(touch bad)/docs"\n', encoding="utf-8")
            self.assertEqual(documents_dir(), self.root / "Documents")

    def test_macos_and_fallback_use_documents(self):
        with patch("pathlib.Path.home", return_value=self.root):
            with patch("alterecho.paths.sys.platform", "darwin"):
                self.assertEqual(documents_dir(), self.root / "Documents")
            with patch("alterecho.paths.sys.platform", "win32"), patch("alterecho.paths._windows_documents", side_effect=OSError):
                self.assertEqual(documents_dir(), self.root / "Documents")

    def test_portable_home_still_isolates_test_data(self):
        with patch.dict(os.environ, {"ALTERECHO_HOME": str(self.root / "portable")}):
            self.assertEqual(conversations_dir(), self.root / "portable/data/conversations")

    def test_former_default_profile_migrates_in_memory_and_remains_discoverable(self):
        old = self.root / "data/conversations"
        new = self.root / "Documents/AlterEcho/conversations"
        settings = UserSettings(self.root / "profile.json")
        settings.save(Config(output_dir=str(old)))
        original = settings.path.read_bytes()
        with patch("alterecho.preferences.data_dir", return_value=old.parent), patch("alterecho.preferences.conversations_dir", return_value=new):
            cfg = settings.load()
            self.assertEqual(cfg.output_dir, str(new))
            self.assertIn(old, history_directories(cfg, settings))
            self.assertEqual(settings.path.read_bytes(), original)
            cfg.output_dir = str(self.root / "custom")
            settings.save(cfg)
            self.assertEqual(settings.load().output_dir, str(self.root / "custom"))

    def test_demo_saves_all_formats_in_documents_without_real_providers(self):
        class UI:
            def say(self, *a): pass
            def waiting(self, *a): pass
            def message(self, *a): pass
            def error(self, *a): pass
            def summary(self, *a): pass

        with patch("alterecho.paths.documents_dir", return_value=self.root / "Documents"):
            cfg = Config()
        settings = MagicMock()
        settings.load.return_value = cfg
        with patch("alterecho.profile_runtime.CodexAdapter") as codex, patch("alterecho.profile_runtime.OllamaAdapter") as ollama:
            self.assertEqual(asyncio.run(execute(parser().parse_args(["demo", "--turns", "2"]), UI(), settings)), 0)
            codex.assert_not_called()
            ollama.assert_not_called()
        files = list((self.root / "Documents/AlterEcho/conversations").rglob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(Store(files[0]).load().messages), 2)
        for extension in ("md", "txt", "html"):
            self.assertTrue(files[0].with_suffix("." + extension).is_file())
