from base64 import b64encode
from hashlib import sha256
from html import escape
from importlib.resources import files
import math
import re
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from ..stats import summarize
from ..history import participant_label


_MARKDOWN = MarkdownIt("default", {"html": False, "linkify": False, "typographer": False})
_CODE_FORMATTER = HtmlFormatter(nowrap=True, classprefix="tok-")


def _link_open(renderer, tokens, index, options, env):
    """Render only explicitly safe, user-clickable URL schemes."""
    token = tokens[index]
    href = token.attrGet("href") or ""
    normalized = _MARKDOWN.normalizeLink(href)
    scheme = urlsplit(normalized).scheme.lower()
    if scheme not in {"http", "https", "mailto"}:
        return '<a class="blocked-link" aria-label="Link non apribile">'
    return f'<a href="{escape(normalized, quote=True)}" rel="noopener noreferrer">'


def _image(renderer, tokens, index, options, env):
    # Never embed or fetch remote/local images from untrusted conversation text.
    alt = tokens[index].attrGet("alt") or ""
    return f'<span class="image-alt">[Immagine: {escape(alt)}]</span>'


def _fence(renderer, tokens, index, options, env):
    token = tokens[index]
    language = (token.info or "").strip().split(maxsplit=1)[0] if token.info else ""
    label = language or "Codice"
    try:
        lexer = get_lexer_by_name(language, stripall=False) if language else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    code = highlight(token.content, lexer, _CODE_FORMATTER)
    return (
        '<section class="code-block"><div class="code-toolbar">'
        f'<span>{escape(label)}</span><button class="copy-code" type="button">Copia codice</button></div>'
        f'<pre><code>{code}</code></pre></section>\n'
    )


_MARKDOWN.add_render_rule("link_open", _link_open)
_MARKDOWN.add_render_rule("image", _image)
_MARKDOWN.add_render_rule("fence", _fence)


def _format_number(value):
    return f"{value:,}".replace(",", ".")


def _tokens(message, key):
    value = message.usage.get(key) if isinstance(message.usage, dict) else None
    return _format_number(value) if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None


def _date(value, include_time=True):
    if not isinstance(value, str) or not value:
        return "Non disponibile"
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d/%m/%Y %H:%M" if include_time else "%d/%m/%Y")
    except (ValueError, OverflowError):
        return escape(value)


def _duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "Non disponibile"
    return f"{seconds:.2f} s"


def _message_markup(message, index, config=None):
    speaker = str(getattr(message, "speaker", ""))
    model = str(getattr(message, "model", "Modello"))
    content = _MARKDOWN.render(str(getattr(message, "text", "")))
    time = _date(getattr(message, "timestamp", ""))
    seconds = _duration(getattr(message, "seconds", None))
    input_tokens = _tokens(message, "input_tokens")
    output_tokens = _tokens(message, "output_tokens")
    speed = message.usage.get("tokens_per_second") if isinstance(message.usage, dict) else None
    details = []
    if input_tokens is not None:
        details.append(f"Input {input_tokens} token")
    if output_tokens is not None:
        details.append(f"Output {output_tokens} token")
    if isinstance(speed, (int, float)) and math.isfinite(speed) and speed > 0:
        details.append(f"{speed:.1f} token/s")
    tech = " · ".join([time, seconds, *details])
    side = "codex" if speaker == "codex" else "ollama"
    return (
        f'<article class="message {side}" data-speaker="{escape(speaker, quote=True)}">'
        '<div class="message-heading">'
        f'<div><span class="speaker-label">{escape(participant_label(config or {}, speaker))}</span>'
        f'<span class="model-name">{escape(model)}</span></div>'
        f'<button class="copy-message" type="button" aria-label="Copia messaggio {index}">Copia</button>'
        '</div>'
        f'<div class="message-content">{content}</div>'
        f'<details class="message-meta"><summary>{escape(time)} · {escape(seconds)}</summary>'
        f'<p>Generazione: {escape(seconds)}</p>'
        f'<p>Token input: {input_tokens if input_tokens is not None else "Non disponibile"}</p>'
        f'<p>Token output: {output_tokens if output_tokens is not None else "Non disponibile"}</p>'
        f'<p>Velocità: {f"{speed:.1f} token/s" if isinstance(speed, (int, float)) and math.isfinite(speed) and speed > 0 else "Non disponibile"}</p>'
        '</details><span class="sr-only message-search-meta">'
        f'{escape(tech)}</span></article>'
    )


def _summary(conversation):
    stats = summarize(conversation)
    rows = []
    measured_outputs = measured_seconds = 0
    all_input = [int(m.usage["input_tokens"]) for m in conversation.messages if isinstance(m.usage, dict) and isinstance(m.usage.get("input_tokens"), (int, float)) and math.isfinite(m.usage["input_tokens"]) and m.usage["input_tokens"] >= 0]
    all_output = [int(m.usage["output_tokens"]) for m in conversation.messages if isinstance(m.usage, dict) and isinstance(m.usage.get("output_tokens"), (int, float)) and math.isfinite(m.usage["output_tokens"]) and m.usage["output_tokens"] >= 0]
    for speaker in ("codex", "ollama"):
        messages = [m for m in conversation.messages if m.speaker == speaker]
        input_measured = [int(m.usage["input_tokens"]) for m in messages if isinstance(m.usage, dict) and isinstance(m.usage.get("input_tokens"), (int, float)) and math.isfinite(m.usage["input_tokens"]) and m.usage["input_tokens"] >= 0]
        output_measured = [int(m.usage["output_tokens"]) for m in messages if isinstance(m.usage, dict) and isinstance(m.usage.get("output_tokens"), (int, float)) and math.isfinite(m.usage["output_tokens"]) and m.usage["output_tokens"] >= 0]
        paired = [(m.usage["output_tokens"], m.seconds) for m in messages if isinstance(m.usage, dict) and isinstance(m.usage.get("output_tokens"), (int, float)) and math.isfinite(m.usage["output_tokens"]) and m.usage["output_tokens"] >= 0 and isinstance(m.seconds, (int, float)) and math.isfinite(m.seconds) and m.seconds > 0]
        in_total = sum(input_measured) if input_measured else None
        out_total = sum(output_measured) if output_measured else None
        measured_outputs += sum(tokens for tokens, _ in paired)
        measured_seconds += sum(seconds for _, seconds in paired)
        token_sum = in_total + out_total if in_total is not None and out_total is not None else None
        rows.append(
            '<tr><th scope="row">' + escape(participant_label(conversation.config, speaker)) + '</th>'
            f'<td>{len(messages)}</td><td>{_format_number(in_total) if in_total is not None else "Non disponibile"}</td>'
            f'<td>{_format_number(out_total) if out_total is not None else "Non disponibile"}</td>'
            f'<td>{_format_number(token_sum) if token_sum is not None else "Non disponibile"}</td></tr>'
        )
    average_speed = f"{measured_outputs / measured_seconds:.1f} token/s" if measured_seconds > 0 else "Non disponibile"
    status = {"ready": "Pronta", "running": "In corso", "completed": "Completata", "stopped": "Arrestata", "interrupted": "Interrotta", "failed": "Errore"}.get(conversation.status, conversation.status)
    measured_total = sum(all_input) + sum(all_output) if all_input or all_output else None
    return (
        f'<section class="summary" id="summary"><h2>Riepilogo</h2>'
        f'<p class="summary-lead">{stats["messages"]} messaggi · {escape(status)} · {stats["seconds"]:.2f} s di generazione</p>'
        '<div class="table-wrap"><table><thead><tr><th>Interlocutore</th><th>Messaggi</th><th>Token input</th><th>Token output</th><th>Totale rilevato</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        f'<p>Token input rilevati: {_format_number(sum(all_input)) if all_input else "Non disponibile"} · Token output rilevati: {_format_number(sum(all_output)) if all_output else "Non disponibile"} · Totale misurato: {_format_number(measured_total) if measured_total is not None else "Non disponibile"}</p>'
        f'<p>Velocità media misurabile: {average_speed}</p>'
        f'<p>Inizio: {_date(conversation.created_at)} · Fine: {_date(conversation.messages[-1].timestamp) if conversation.messages else "Non disponibile"}</p>'
        '</section>'
    )


def render_html(conversation):
    """Render a self-contained, offline HTML page from canonical history data."""
    cfg = conversation.config
    messages = "\n".join(_message_markup(message, index, cfg) for index, message in enumerate(conversation.messages, 1))
    if conversation.partial:
        partial = _MARKDOWN.render(str(conversation.partial.get("text", "")))
        messages += f'<article class="message partial"><div class="speaker-label">Risposta parziale · non inoltrata</div><div class="message-content">{partial}</div></article>'
    roles = {"free": "Conversazione libera", "debate": "Dibattito", "blind": "Esperimento cieco"}
    body = files("alterecho.exporters").joinpath("templates/conversation.html").read_text(encoding="utf-8")
    css = files("alterecho.exporters").joinpath("templates/style.css").read_text(encoding="utf-8")
    javascript = files("alterecho.exporters").joinpath("templates/script.js").read_text(encoding="utf-8")
    # Syntax styles belong only to code, never to the message bubble. Keep
    # backgrounds in the theme stylesheet and use a matching token palette.
    for theme, palette in (("dark", "monokai"), ("light", "default")):
        formatter = HtmlFormatter(style=palette, nobackground=True, classprefix="tok-")
        css += "\n" + formatter.get_style_defs(f'body[data-theme="{theme}"] .code-block pre')
    css_hash = b64encode(sha256(css.encode("utf-8")).digest()).decode("ascii")
    js_hash = b64encode(sha256(javascript.encode("utf-8")).digest()).decode("ascii")
    status_names = {"ready": "Pronta", "running": "In corso", "completed": "Completata", "stopped": "Arrestata", "interrupted": "Interrotta", "failed": "Errore"}
    replacements = {
        "{{CSP}}": f"default-src 'none'; style-src 'sha256-{css_hash}'; script-src 'sha256-{js_hash}'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'",
        "{{CSS}}": css,
        "{{JS}}": javascript,
        "{{TOPIC}}": escape(str(cfg.get("topic", "Senza argomento"))),
        "{{CODEX_MODEL}}": escape(str(cfg.get("codex_model", "Non disponibile"))),
        "{{OLLAMA_MODEL}}": escape(str(cfg.get("ollama_model", "Non disponibile"))),
        "{{PARTICIPANT_A}}": escape(participant_label(cfg, "codex")),
        "{{PARTICIPANT_B}}": escape(participant_label(cfg, "ollama")),
        "{{CREATED}}": escape(_date(conversation.created_at)),
        "{{MODE}}": escape(roles.get(cfg.get("mode"), str(cfg.get("mode", "Non disponibile")))),
        "{{MESSAGE_COUNT}}": str(len(conversation.messages)),
        "{{STATUS}}": escape(status_names.get(conversation.status, conversation.status)),
        "{{MESSAGES}}": messages,
        "{{SUMMARY}}": _summary(conversation),
    }
    # Replace only placeholders in the trusted template. Model text has already
    # been parsed with raw HTML disabled and escaped by Markdown/Pygments.
    return re.sub(r"\{\{[A-Z_]+\}\}", lambda match: replacements.get(match.group(0), match.group(0)), body)
