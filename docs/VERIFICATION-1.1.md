# AlterEcho 1.1 application verification

**English** | [Italiano](VERIFICA-1.1.md)

Local checks from **26 October 2026**, preceding the subsequently authorized local 1.1.0 commit/tag. Packages/images were built locally only. No push or remote release was performed. [Historical 1.0 report](VERIFICATION-1.0.md) is preserved; [release](VERIFICATION-RELEASE.md) and [i18n](VERIFICATION-I18N.md) reports record later checks.

## Architecture and behavior

One FastAPI/Uvicorn engine remains, with Rich/Svelte clients sharing API/SSE. All four providers, server-held credentials, origin/host security, profiles, schema-1 histories and Codex checkpoints remain compatible.

Verified changes include background startup/readiness/identity/logging/watchdog; private nonce-authenticated local `down` without stored-PID signals or remote shutdown API; foreground supervisor mode; deduplicated Rich streaming and pipe output; compact responsive chat with sanitized Markdown, copy/details and manual-scroll preservation; verified model/reasoning selectors; explicit metered-cost dialogs with Cancel focus, Escape and focus restoration.

Windows startup was corrected to use `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` and `SW_HIDE`, without `DETACHED_PROCESS`, which would cause Windows to ignore the no-window flag. Tests checked the actual process console, survival after launcher exit and graceful shutdown.

## Executed results at that revision

| Check | Result |
| --- | --- |
| Initial baseline | 119 Python tests passed |
| Windows/Python 3.12 application suite | 136 passed; subsequent CLI/watch checks: 35 passed |
| Focused process/CLI after Windows fix | 11 process and 29 CLI tests passed |
| Process/watch in Linux Docker runtime | 17 tests passed, including detached/down/crash/stale metadata/host/watchdog/SSE |
| Frontend | 11 Vitest tests; Svelte zero errors/warnings; Vite build passed |
| Browser | 12 Playwright tests on Windows, desktop and emulated phone |
| Wheel/sdist | Build/resources and outside-checkout installed CLI checks passed |
| Windows standalone | Foreground/background/down/HTTP/static/demo/persistence passed |
| Linux Docker | Multistage build, UID 10001, foreground/health/API/Web/demo/SIGTERM/restart persistence passed |
| Services | Templates updated; no automatic installation/activation |

Browser fixtures exercised long streaming, reconnect, reading position, bottom arrow, PageUp/Home, synthetic touch/rotation, 50/100-message histories, tables/code, both themes, absent models, dialogs and fresh metered consent. They used real HTTP/SSE with mock providers, not real inference. User histories/configuration were not moved or rewritten.

The old 1.0 CI had Ubuntu/Docker success but Windows/macOS path-comparison failures (`RUNNER~1`/`runneradmin`, `/var`/`/private/var`). Fixture roots now resolve canonically; no tests were deleted/disabled. No new remote CI success is claimed. Later ordinary CI uses Vite dev without release artifact uploads; [distribution checks](VERIFICATION-RELEASE.md) supersede earlier pipeline details.

Source changes cover `managed.py`, `watching.py`, CLI/server/settings, chat/model/dialog/toast components, API recovery, process/watch/browser fixtures, deployment templates and documentation. Real test screenshots live in `images/1.1/`; original author-supplied images are preserved. [Image provenance](images/README.md).

Reproduction commands, token/log paths, provider setup and supervisor differences are in the [user guide](GUIDE.md) and [deployment guide](../deploy/README.md). Native Linux/macOS installations/services and real smartphone/tablet visual QA were not certified. There are no individual user roles, automatic crash inference restart, cloud dependency or separate desktop engine.
