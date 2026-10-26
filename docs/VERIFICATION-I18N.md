# Internationalization verification

**English** | [Italiano](VERIFICA-I18N.md)

Local revision dated **26 October 2026**, after the local 1.1.0 tag. These checks preceded the subsequently authorized 1.2.0 commit/tag. No push, remote release, service installation or registry publication was performed. AI providers were mocked; no real inference or quota usage was involved.

## Implemented architecture

- One English reference JSON and one Italian JSON in `alterecho/locales/`, shared by Python and Svelte. Automatic discovery, English fallback, parameters, plural forms and local number/date formatting.
- Browser detection from ordered language preferences, persistent local override and reactive updates, including modal/toast/error text. No SSE remount or conversation-data translation.
- CLI system/environment detection, `--lang`, `ALTERECHO_LANG`, local settings preference in `client-language.json`, translated help/menus/diagnostics/watch/management errors.
- English server details plus additive error codes/parameters; existing routes, enum values and `detail` contracts remain. Parameters are redacted; unknown external provider diagnostics are preserved.
- English-first README, user/architecture/deployment/release/translation guides, changelog and image provenance, with Italian counterparts. Original historical documents/screenshots remain accessible.
- Packaged JSON resources for wheel/sdist/standalone and Docker; Vite embeds the same catalogs without online translation or a Node production server.

## Actual checks

| Check | Result |
| --- | --- |
| Python suite on Windows/Python 3.12 | **161 tests passed** |
| Catalog/locale/CLI tests | 11 tests included above: duplicate/key/parameter checks, fallback, Windows/Linux/macOS mocked detection, precedence, persisted/local settings, help, watch, data invariance, serialization and compatible errors |
| Frontend Vitest | **18 tests passed**, including a component text/catalog-reference audit |
| Svelte/TypeScript and Vite | Zero errors/warnings; production build passed with both catalogs |
| Browser through Vite dev | **16 tests passed** on desktop/emulated phone: detection, unsupported-locale fallback, persistence, independent contexts, live dialogs/drafts/SSE, reading-position preservation and unchanged original topic/text |
| Windows standalone | Rebuilt and checked outside checkout: EN/IT help, foreground/background, no visible detached console, down, HTTP CLI/Web, demo, persistence and graceful shutdown passed |
| Docker Linux AMD64 | Built and run locally: EN/IT CLI, packaged catalogs, Codex binary/help, nonroot/OCI/foreground/health/API/Web/demo, SIGTERM and restart persistence passed |
| Wheel/sdist | Built, inspected and separately installed into fresh virtualenvs; EN/IT help, catalogs, HTTP CLI, Web resources, demo and restart persistence passed outside the checkout |

English desktop/mobile test captures were visually inspected. Original documentation screenshots remain unchanged. Both current catalogs are included in the rebuilt Windows executable and Linux AMD64 image; their final smoke checks passed again after alignment with the compiled frontend.

Regression fixes included preserving translation metadata across `deepcopy`/JSON event paths and placing the language selector outside the mobile navigation overlay. The scroll test waits for the browser to apply the wheel event before comparing positions; it does not relax the position-preservation requirement.

A repeated run during parallel builds hit a managed-server HTTP timeout; the owned demo instance was shut down through its private control channel and the isolated case passed. A separate cold-start race in the Codex fixture was corrected by applying its 0.5-second generation deadline only after protocol setup. The generation deadline/assertions and production timeouts were not increased. The subsequent complete serial run passed all 161 tests; no tests were disabled.

The complete Python suite retains legacy history/configuration, all four provider mocks, Codex resume/checkpoints, conservative Ollama memory, security, lifecycle, export and release tests. Conversation prompts/defaults and export wrappers remain unchanged; only presentation and application-owned error messages were localized. Development bootstrap scripts and future maintainer release notes use English.

## Limits and pending checks

- Windows locale API and Linux/macOS system-locale detection have unit coverage; no new native Linux/macOS desktop/service installation was performed.
- Docker AMD64 is the Linux runtime check. Current i18n ARM64 Docker and native Linux/macOS standalone builds have not been repeated; earlier release checks do not certify these newer artifacts.
- Mobile is Chromium viewport emulation, not a physical smartphone/tablet or Safari test.
- Existing screenshots retain Italian text; English documentation identifies their original provenance. Historical 0.3 documents remain in their original Italian as archival records, rather than current user guides.
- Browser persistence depends on available local storage; blocked storage permits a session-only choice. It is never a shared server setting.
- No real Codex/API/Ollama inference, provider authentication, TLS Internet deployment or GitHub/GHCR publication was tested.
- The 1.2.0 commit/tag preparation is subsequent to these runtime checks. The former local `v1.1.0` is archived outside the tag namespace so a selected release push does not publish it.

[Implementation/contribution guide](I18N.md) · [User guide](GUIDE.md) · [Release verification](VERIFICATION-RELEASE.md).
