import contextlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from alterecho import i18n
from alterecho.cli import main, parser
from alterecho.config import Config, BridgeError
from alterecho.ui import Terminal


class I18nTests(unittest.TestCase):
    def setUp(self):
        self.previous = i18n.language()
        self.addCleanup(i18n.set_language, self.previous)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {'ALTERECHO_HOME': str(self.root), 'ALTERECHO_LANG': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_catalogs_have_unique_keys_equal_fields_and_parameters(self):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result)
                result[key] = value
            return result
        catalogs = {}
        for path in (Path(__file__).parents[1] / 'alterecho/locales').glob('*.json'):
            catalogs[path.stem] = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)
        en, it = catalogs['en'], catalogs['it']
        self.assertEqual(set(en), set(it))
        def fields(value):
            return set(re.findall(r'\{([A-Za-z_]\w*)\}', str(value)))
        for key in en:
            if key != '_meta':
                self.assertEqual(fields(en[key]), fields(it[key]), key)
                self.assertEqual(type(en[key]), type(it[key]), key)

    def test_system_language_normalizes_regions_and_falls_back(self):
        for raw, expected in [('it_IT.UTF-8', 'it'), ('it-CH', 'it'), ('en_GB', 'en'), ('de_DE', 'en'), ('C', 'en')]:
            with self.subTest(raw=raw), patch.dict(os.environ, {'LC_ALL': raw}, clear=True):
                self.assertEqual(i18n.detect_system(), expected)

    def test_linux_macos_and_absent_locale(self):
        for system in ('linux', 'darwin'):
            with patch.dict(os.environ, {}, clear=True), patch('alterecho.i18n.sys.platform', system), patch('alterecho.i18n.locale.getlocale', return_value=('it_IT', 'UTF-8')):
                self.assertEqual(i18n.detect_system(), 'it')
        with patch.dict(os.environ, {}, clear=True), patch('alterecho.i18n.sys.platform', 'linux'), patch('alterecho.i18n.locale.getlocale', return_value=(None, None)):
            self.assertEqual(i18n.detect_system(), 'en')

    def test_windows_user_locale_without_a_desktop_session(self):
        def locale_name(buffer, size):
            buffer.value = 'it-IT'
            return 6
        with patch.dict(os.environ, {}, clear=True), patch('alterecho.i18n.sys.platform', 'win32'), patch('ctypes.windll', SimpleNamespace(kernel32=SimpleNamespace(GetUserDefaultLocaleName=locale_name)), create=True):
            self.assertEqual(i18n.detect_system(), 'it')

    def test_precedence_auto_and_temporary_override(self):
        with patch('alterecho.i18n.detect_system', return_value='it'):
            i18n.save_preference('en')
            self.assertEqual(i18n.configure(), 'en')
            with patch.dict(os.environ, {'ALTERECHO_LANG': 'it'}):
                self.assertEqual(i18n.configure(), 'it')
                self.assertEqual(i18n.configure('en'), 'en')
            self.assertEqual(i18n.preference(), 'en')
            self.assertEqual(i18n.configure('auto'), 'it')
            self.assertEqual(i18n.preference(), 'en')
        self.assertFalse((self.root / 'config/config.json').exists())
        self.assertFalse((self.root / 'config/adapters.json').exists())

    def test_fallback_plural_number_date_and_missing_key(self):
        i18n.set_language('it')
        saved = i18n.catalogs()['it'].pop('web.history')
        try:
            self.assertEqual(i18n.t('web.history'), 'History')
        finally:
            i18n.catalogs()['it']['web.history'] = saved
        self.assertEqual(i18n.t('web.messages', count=1), '1 messaggio')
        self.assertEqual(i18n.t('web.messages', count=2), '2 messaggi')
        self.assertEqual(i18n.number(1234.5, 1), '1.234,5')
        self.assertIn('2026', i18n.date('2026-10-26T10:00:00+00:00'))
        self.assertEqual(i18n.t('missing.fixture.key'), 'Message unavailable.')

    def test_help_both_languages_and_stable_commands(self):
        for language, heading in [('en', 'Usage:'), ('it', 'Uso:')]:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(['--lang', language, 'help']), 0)
            self.assertIn(heading, out.getvalue())
            for command in ('serve', 'run', 'resume', 'watch', 'down'):
                self.assertIn(command, out.getvalue())
        self.assertFalse(i18n.preference_path().exists())

    def test_menu_and_watch_localize_presentation_only(self):
        from rich.console import Console
        from alterecho.watching import watch
        import asyncio
        from unittest.mock import Mock
        state = {'active': False, 'status': 'completed', 'messages': [], 'partial': None,
                 'config': {'max_turns': 2, 'participants': {}}, 'stats': {'seconds': 1.5}}
        for language, expected in [('en', 'Status:'), ('it', 'Stato:')]:
            i18n.set_language(language)
            ui = Terminal(); ui.console = Console(file=io.StringIO())
            client = Mock(); client.get.return_value = state
            self.assertEqual(asyncio.run(watch(client, 'fixture', ui)), 0)
            self.assertIn(expected, ui.console.file.getvalue())
        cfg = Config(topic='Argomento originale 日本語', roles={'codex': 'Critico', 'ollama': 'Writer'})
        before = cfg.to_dict()
        i18n.set_language('en'); i18n.set_language('it')
        self.assertEqual(before, cfg.to_dict())

    def test_server_errors_are_english_and_client_localizable(self):
        from alterecho.client import APIClient
        import httpx
        i18n.set_language('it')
        message = i18n.message('server.conversation_not_found')
        self.assertEqual(message, 'Conversation not found.')
        payload = i18n.error_payload(BridgeError(message))
        self.assertEqual(payload['code'], 'server.conversation_not_found')
        with self.assertRaisesRegex(BridgeError, 'Conversazione non trovata'):
            APIClient.check(httpx.Response(404, json=payload))
        self.assertEqual(i18n.localize('external provider diagnostic 日本語'), 'external provider diagnostic 日本語')
        self.assertEqual(i18n.localize('Invalid upstream token.'), 'Invalid upstream token.')
        persisted = str(i18n.message('errors.codex.startup_home_access', error='RPC timeout'))
        self.assertEqual(i18n.error_info(persisted)['code'], 'errors.codex.startup_home_access')

    def test_translated_text_survives_copy_and_event_serialization(self):
        import copy
        value = i18n.message('errors.save_failed')
        cloned = copy.deepcopy({'error': value})
        self.assertEqual(cloned['error'].code, value.code)
        self.assertEqual(json.loads(json.dumps(cloned))['error'], str(value))

    def test_settings_language_does_not_save_shared_configuration(self):
        from unittest.mock import Mock
        from rich.prompt import Prompt
        from rich.console import Console
        preferences = Mock(); preferences.load.return_value = Config(); preferences.path = 'server settings'
        i18n.configure(None); i18n.set_language('it')
        ui = Terminal(); ui.console = Console(file=io.StringIO())
        with patch.object(Prompt, 'get_input', side_effect=['L', 'en', '0']):
            ui.settings(preferences, Mock())
        self.assertEqual(i18n.preference(), 'en')
        self.assertEqual(i18n.language(), 'en')
        preferences.save.assert_not_called()
        self.assertIn('SETTINGS', ui.console.file.getvalue())
