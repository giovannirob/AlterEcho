# Historical AlterEcho 1.0 verification

**English** | [Italiano](VERIFICA-1.0.md)

Recorded on **24 October 2026**, starting from `main` commit `5ffcb601`. This report describes local verification before the later Git tag; it does not certify remote CI, native services or real provider inference. Original technical details remain preserved in the linked Italian historical report.

One FastAPI/Uvicorn server owns SessionManager tasks and the single Coordinator. Rich CLI and Svelte/TypeScript Web clients use `/api/v1` and SSE. Four providers remain: ChatGPT-authenticated Codex CLI, Ollama and ChatAPIAdapter for OpenAI/OpenRouter. A/B is public presentation while schema-1 JSON retains legacy slots. Profile snapshots, native Codex checkpoints, partials, keep-alive `-1`, cautious unload and offline HTML exports are preserved.

| Check | Recorded result |
| --- | --- |
| Original Python baseline | 100 tests passed |
| Post-migration Python suite | 119 tests passed with mocks |
| Frontend | Six tests passed; zero Svelte/TypeScript errors/warnings; build passed |
| Real HTTP/SSE socket | Disconnection leaves generation active; cursor/snapshot recovery checked |
| Four providers through server | Mock Codex app-server, Ollama NDJSON and OpenAI/OpenRouter SSE |
| Pause/resume/shutdown | Turn-boundary pause, partial persistence on stop |
| Concurrency/export failures | Duplicate start rejected; tasks/resources released |
| Security | Authentication, origins, Host, CSRF boundaries, input and rate-limit cases |
| Legacy persistence/migration | Read without rewrite, pre-resume backup, hash-verified copy and overwrite refusal |
| Wheel/sdist | Built and inspected; Web assets included and personal files excluded |
| Installed wheel CLI | Outside-checkout import/help checked |
| Windows standalone | Build and HTTP/server/CLI/Web/demo/persistence/shutdown smoke passed |
| Docker Linux runtime | Build and isolated mock/demo persistence/shutdown checks |

No service was installed/activated by the original checks; personal histories/configuration were not migrated. Native Linux/macOS installations, their supervisors, remote TLS deployment and physical-device visual checks remained pending. A single process and shared admin token were supported, without multiuser roles. Provider real-account authentication/access and AI inference were not tested.

The later remote 1.0 CI reported Windows/macOS path normalization failures; these are documented with fixes in [1.1 verification](VERIFICATION-1.1.md). Current architecture and procedures are in [ARCHITECTURE.md](../ARCHITECTURE.md) and [GUIDE.md](GUIDE.md), rather than the historical 0.3 documents in `legacy/`.
