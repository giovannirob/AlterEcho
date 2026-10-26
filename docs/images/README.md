# Project images

**English** | [Italiano](README.it.md)

All documentation image paths are repository-relative. Original captures retain the Italian interface; they were not edited to imply an English capture.

| File | Content | Provenance |
| --- | --- | --- |
| `dashboard.png` | Dashboard, providers, measured usage/history | Authentic author-supplied screenshot |
| `nuova-conversazione.png` | Participant selection and setup | Authentic author-supplied screenshot |
| `profili.png` | Codex/Ollama profile settings | Authentic author-supplied screenshot |
| `alterecho-hero.svg` | Alternative two-perspective cover | Original vector illustration, not an app screenshot |
| `architettura.svg` / `architecture.en.svg` | CLI/browser → one server → four providers | Diagram of implemented architecture, Italian/English text |

Colors follow `web/src/style.css`: background `#101319`, panels `#181d25`, A accent `#80ddcf`, B accent `#aaa0ef`. SVGs contain no scripts, remote fonts, embedded images or personal data.

## Author-supplied captures

Computer Use could not confidently verify the Chrome URL on Windows during the original capture task, so the author supplied three PNGs. They were inspected and renamed without changing pixels. No fictional interface was created or unperformed capture claimed.

The dashboard's conversation titles and counters belong to the author's instance; this is neither a mock-provider capture nor a benchmark. The other captures are configuration forms. No tokens, API keys or identifying personal data are visible. No AI inference was performed to produce these documentation assets.

## Version 1.1 captures, 26 October 2026

The `1.1/` directory contains real Playwright/Chromium captures on Windows using the isolated `tests/browser_server.py` backend. Providers and text are simulated test fixtures, not real Codex/Ollama/API answers or performance measurements. Captures were inspected without retouching.

| File | View |
| --- | --- |
| `1.1/chat-desktop.png` | Dark desktop chat with three simulated messages |
| `1.1/chat-mobile-light.png` | Light chat in an emulated smartphone viewport |
| `1.1/conferma.png` | Start dialog and explicit metered-cost consent |
| `1.1/nuova-conversazione.png` | Models from test catalogs |

The author's original PNGs are preserved. Mobile emulation is not a physical-device test. New i18n work keeps these historical captures and explains their language rather than fabricating new screenshots.

For future captures use only mock providers or demo; omit login tokens, keys, private conversations, personal addresses and notifications. Record provenance and make simulated content clear. Prefer optimized PNG/WebP, relative paths, meaningful alt text and readable small-screen layouts. No real inference is needed.
