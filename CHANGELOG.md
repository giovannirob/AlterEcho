# Changelog

**English** | [Italiano](CHANGELOG.it.md)

Changes are grouped by version. This log starts at 1.0.0.

## 1.2.0 — 2026-10-26

### Added

- Shared extensible JSON catalogs for English and Italian, with English fallback, interpolation, plural forms and locale-aware formatting.
- Browser language detection, persistent local selection and immediate updates, including open dialogs and live conversations.
- CLI system-locale detection, temporary `--lang` and `ALTERECHO_LANG` overrides, and a persistent local language setting.
- Compatible API error codes/parameters for client-side localization, independent of server locale.
- English-first README, architecture, user/deployment/release guides and changelog with Italian counterparts; translation contribution guide.
- Automated catalog, locale, preference and live-switching tests; packaging checks for translations in installed wheels, source packages, standalone executables and containers.

### Preserved

- Headless architecture, all four providers, API routes and technical IDs.
- Original conversation topics, prompts, roles, positions, model output, histories, exports and Codex checkpoints/sessions. Interface language never translates conversation data.

## 1.1.0 — 2026-10-26

### Added

- Verified background server startup with persistent logs and instance identity; `alterecho down` for graceful local shutdown.
- Web chat with distinct participants, sanitized progressive Markdown, copy, search, details and navigation to the last message.
- Catalog-backed model selectors, filtering and unavailable-model handling; summary/confirmation dialogs for start, resume and deletion.
- Release workflow triggered only by a new valid version tag: validation, tests, frontend, Python packages, native standalone builds, Docker, GHCR and automatic GitHub Release.
- Prepared native build matrix for Windows x64, Linux x64/ARM64 and macOS ARM64/Intel, with checks outside the checkout.
- AMD64/ARM64 Docker builds with pinned Codex, OCI labels and a multiarch manifest gated on both image checks.
- Versioned archives, SHA-256 checksums and release manifest; safeguards against inconsistent versions, duplicates, moved tags and overwrites.
- `compose.registry.yaml` for published private GHCR images and a maintainer release guide.

### Changed

- `alterecho serve` starts in background by default; `--detach` is an alias and `--foreground` serves diagnostics, containers and supervisors.
- CLI streaming updates one active message and prints complete output to pipes/files, with backend cursor recovery.
- Web auto-scroll respects reading position, restores navigation state and uses compact controls.
- Normal CI runs Python, frontend and development-mode browser tests, without distribution builds or publication.
- Project/runtime/frontend versions are validated against tags, including prerelease mappings; the Web UI uses the npm version.
- Wheel/sdist are separately checked in clean installations with Web resources outside the checkout.
- Documentation covers managed startup, CLI/chat, services, downloads, GHCR and failed-release recovery.

### Fixed

- Separate visible Python console on Windows background startup; closing a client no longer stops the server.
- Message/delta duplication during SSE reconnection and `watch` recovery; consistent conversation-ID resolution.
- Windows/macOS temporary-root comparisons across equivalent short paths and `/var`/`/private/var` links.

### Verification

The local release-pipeline revision passed 150 Python, 11 frontend and 12 browser tests, without real AI inference. Windows/Linux x64 standalone and Docker images were checked locally; Docker ARM64 used emulation. Native macOS/Linux ARM64 standalone runners and actual GitHub/GHCR publication remained pending. macOS builds are unsigned/not notarized. [Application checks](docs/VERIFICATION-1.1.md) · [Distribution checks](docs/VERIFICATION-RELEASE.md).

## 1.0.0 — 2026-10-24

### Added and changed

- One headless FastAPI/Uvicorn server owns conversation tasks and persistence; Rich CLI and Svelte/TypeScript Web UI share versioned API/SSE.
- Central start, stop, pause, resume, streaming, statistics, history and export; generation survives client disconnection.
- Codex CLI with ChatGPT, Ollama, OpenAI API and OpenRouter profiles, with metered-API confirmations.
- Existing JSON, Codex sessions/checkpoints, atomic writes and offline Markdown/TXT/HTML export compatibility.
- Authentication, local binding, origin/host checks, input validation and rate limiting.
- Python packaging, Windows standalone build, multistage Docker and Windows/systemd/launchd service templates.

[Historical verification](docs/VERIFICATION-1.0.md) records local checks and limits before the Git tag. It does not certify remote CI success.
