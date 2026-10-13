import hashlib
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import MagicMock, patch

from alterecho.config import Config
from alterecho.history import Conversation, Message
from alterecho.exporters.html import render_html
from alterecho.storage import Store, scan_conversations
from alterecho.cli import parser, interactive_menu
from alterecho.coordinator import Coordinator
from alterecho.adapters.base import Reply


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.links = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(name.lower() for name, _ in attrs)
        if tag == "a":
            self.links.append(dict(attrs))


class SilentUI:
    def waiting(self, *args): pass
    def message(self, *args): pass
    def error(self, *args): pass
    def summary(self, *args): pass


class HtmlExportTests(unittest.TestCase):
    def conversation(self, texts=None):
        cfg = Config(topic="Tema <script>alert(1)</script>", codex_model="model <x>", ollama_model="locale", max_turns=20)
        texts = texts or [
            "# Titolo\n\nTesto **grassetto** e *corsivo*, `inline`.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n> Citazione\n\n[buon link](https://example.com) [cattivo](javascript:alert(1))\n\n![remota](https://example.com/image.png)",
            "Esempio:\n\n```python\ndef saluta():\n    return '<script>alert(1)</script>'\n```\n",
        ]
        messages = []
        for index, text in enumerate(texts):
            speaker = "codex" if index % 2 == 0 else "ollama"
            usage = {"input_tokens": 0, "output_tokens": index + 2, "tokens_per_second": 4.5} if index == 0 else {}
            messages.append(Message(speaker, f"modello-{speaker}", text, .5 + index, f"2026-10-12T12:{index % 60:02d}:00+00:00", usage))
        return Conversation(cfg.to_dict(), messages=messages, status="completed")

    def test_markdown_features_and_code_fence(self):
        html = render_html(self.conversation())
        for expected in ('<h1>Titolo</h1>', '<strong>grassetto</strong>', '<em>corsivo</em>', '<table>', '<blockquote>', 'class="code-block"', 'Copia codice', 'class="tok-'):
            self.assertIn(expected, html)
        self.assertIn('aria-label="Copia messaggio 1"', html)

    def test_messages_keep_history_order_and_all_content(self):
        texts = [f"Messaggio unico {i}" for i in range(20)]
        html = render_html(self.conversation(texts))
        positions = [html.index(text) for text in texts]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("20 messaggi", html)

    def test_untrusted_html_and_script_are_escaped(self):
        html = render_html(self.conversation(["<script>alert('x')</script><img src=x onerror=alert(1)>" ]))
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        parser = StructureParser()
        parser.feed(html)
        self.assertNotIn("onerror", parser.attributes)
        self.assertNotIn("img", parser.tags)

    def test_dangerous_links_and_remote_images_do_not_become_resources(self):
        html = render_html(self.conversation(["[unsafe](javascript:alert(1)) ![remote](https://example.com/a.png) [safe](https://example.com)"]))
        self.assertNotRegex(html, r'href="javascript:')
        self.assertNotIn('src="https://example.com/a.png"', html)
        parser = StructureParser()
        parser.feed(html)
        self.assertTrue(all(link.get("href", "").startswith(("#", "https://", "http://", "mailto:")) for link in parser.links))

    def test_missing_usage_is_reported_as_unavailable(self):
        conversation = self.conversation(["Senza dati"])
        conversation.messages[0].usage = {}
        html = render_html(conversation)
        self.assertIn("Token input: Non disponibile", html)
        self.assertIn("Token output: Non disponibile", html)
        self.assertIn("Totale misurato: Non disponibile", html)
        self.assertIn("Velocità media misurabile: Non disponibile", html)

    def test_zero_tokens_are_measurements_not_missing(self):
        html = render_html(self.conversation(["Zero"]))
        self.assertIn("Token input: 0", html)

    def test_standalone_csp_hashes_match_embedded_assets(self):
        html = render_html(self.conversation())
        css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
        js = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        csp = re.search(r'Content-Security-Policy" content="([^"]+)', html).group(1)
        css_hash = __import__("base64").b64encode(hashlib.sha256(css.encode()).digest()).decode()
        js_hash = __import__("base64").b64encode(hashlib.sha256(js.encode()).digest()).decode()
        self.assertIn(f"style-src 'sha256-{css_hash}'", csp)
        self.assertIn(f"script-src 'sha256-{js_hash}'", csp)
        self.assertIn("connect-src 'none'", csp)
        self.assertIn("img-src 'none'", csp)
        parser = StructureParser()
        parser.feed(html)

    def test_interactive_controls_are_embedded_without_remote_dependencies(self):
        html = render_html(self.conversation())
        for control in ('id="search"', 'id="theme-toggle"', 'id="to-top"', 'id="to-bottom"', 'navigator.clipboard'):
            self.assertIn(control, html)
        self.assertNotRegex(html, r'<(?:script|link)[^>]+(?:src|href)="https?://')

    def test_long_conversation_renders(self):
        html = render_html(self.conversation([f"Lungo storico {i}" for i in range(600)]))
        self.assertIn("Lungo storico 0", html)
        self.assertIn("Lungo storico 599", html)
        self.assertIn("600 messaggi", html)

    def test_store_exports_html_and_preserves_json(self):
        conversation = self.conversation()
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "chat.json")
            store.save(conversation)
            original = store.path.read_bytes()
            written = store.export(conversation)
            self.assertEqual(store.path.read_bytes(), original)
            self.assertEqual({path.suffix for path in written}, {".md", ".txt", ".html"})
            self.assertIn("<title>Tema &lt;script&gt;", store.path.with_suffix(".html").read_text(encoding="utf-8"))

    def test_export_specific_format_keeps_existing_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "chat.json")
            conversation = self.conversation()
            store.save(conversation)
            old_md = store.path.with_suffix(".md")
            old_md.write_text("existing markdown", encoding="utf-8")
            self.assertEqual(store.export(conversation, ["html"]), [store.path.with_suffix(".html")])
            self.assertEqual(old_md.read_text(encoding="utf-8"), "existing markdown")

    def test_export_cli_accepts_html_format(self):
        args = parser().parse_args(["export", "chat.json", "--format", "html"])
        self.assertEqual(args.formats, ["html"])

    def test_view_html_refreshes_then_opens_without_extra_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "chat.json")
            conversation = self.conversation()
            store.save(conversation)
            original = store.path.read_bytes()
            store.path.with_suffix(".html").write_text("outdated", encoding="utf-8")
            ui, preferences = MagicMock(), MagicMock()
            preferences.load.return_value = Config()
            ui.main_menu.side_effect = ["4", "6"]
            ui.choose_history.side_effect = lambda entries, **kwargs: entries[0]
            with patch("alterecho.cli.history_directories", return_value=[tmp]), patch("alterecho.cli.webbrowser.open", return_value=True) as browser:
                self.assertEqual(interactive_menu(ui, preferences), 0)
                browser.assert_called_once_with(store.path.with_suffix(".html").resolve().as_uri())
            ui.confirm.assert_not_called()
            self.assertNotEqual(store.path.with_suffix(".html").read_text(encoding="utf-8"), "outdated")
            self.assertEqual(store.path.read_bytes(), original)

    def test_syntax_styles_do_not_override_message_backgrounds(self):
        html = render_html(self.conversation())
        css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
        self.assertNotRegex(css, r"\.message-content\s*\{[^}]*background")
        self.assertIn('body[data-theme="dark"] .code-block pre', css)
        self.assertIn('body[data-theme="light"] .code-block pre', css)
        self.assertNotRegex(css, r'body\[data-theme="dark"\] \.code-block pre\s*\{[^}]*background:')


class HtmlAutoExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_coordinator_refreshes_html_in_dedicated_conversation_folder(self):
        cfg = Config(max_turns=2)
        conversation = Conversation(cfg.to_dict())

        class SimulatedAdapter:
            def __init__(self, speaker):
                self.speaker = speaker

            async def generate(self, conversation, checkpoint):
                return Reply(f"Risposta {self.speaker}", f"mock-{self.speaker}")

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / conversation.id
            store = Store(folder / f"{conversation.id}.json")
            await Coordinator(cfg, conversation, {s: SimulatedAdapter(s) for s in ("codex", "ollama")}, store, SilentUI()).run()
            html_path = store.path.with_suffix(".html")
            self.assertTrue(html_path.exists())
            rendered = html_path.read_text(encoding="utf-8")
            self.assertIn("Risposta codex", rendered)
            self.assertIn("Risposta ollama", rendered)
            entries, errors = scan_conversations([tmp])
            self.assertFalse(errors)
            self.assertEqual([entry.path for entry in entries], [store.path.resolve()])
            original_messages = store.load().to_dict()["messages"]
            previous_html = html_path.read_bytes()
            cfg.max_turns = 4
            continued = store.load()
            continued.config = cfg.to_dict()
            await Coordinator(cfg, continued, {s: SimulatedAdapter(s) for s in ("codex", "ollama")}, store, SilentUI()).run()
            saved = store.load()
            self.assertEqual(len(saved.messages), 4)
            self.assertEqual(saved.status, "completed")
            self.assertEqual(saved.to_dict()["messages"][:2], original_messages)
            self.assertNotEqual(html_path.read_bytes(), previous_html)
            self.assertIn("4 messaggi", html_path.read_text(encoding="utf-8"))
            for extension in ("md", "txt"):
                self.assertIn("4. ollama", store.path.with_suffix("." + extension).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
