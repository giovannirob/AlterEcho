# AlterEcho architecture

**English** | [Italiano](ARCHITETTURA.md)

## One application process

![CLI and browser connect to the same headless server and its four providers.](docs/images/architecture.en.svg)

Only the headless server owns the conversation engine. Foreground, background, system service and container run the same program. `cli.py`/`client.py` do not import the coordinator or provider adapters; `serve` loads FastAPI on demand. `profile_runtime.py` is an adapter factory, not a second engine. Demo also runs through the server.

## Organization

`serve` launches in background and checks authenticated readiness and instance identity. `serve --foreground` directly runs Uvicorn for diagnostics/supervisors. `managed.py` serializes local control with a lease, private logs/metadata and a separate authenticated loopback TCP channel. `down` verifies the live instance rather than signaling a stored PID. There is no public shutdown API. A watchdog stops unconfirmed startup; both modes retain the same application leases and lifespan.

| Module | Responsibility |
| --- | --- |
| `cli.py`, `client.py`, `ui.py` | Argument parser, HTTP/SSE, Rich menus and remote preferences |
| `managed.py`, `watching.py` | Verified local process lifecycle and deduplicated incremental terminal rendering |
| `server.py`, `server_settings.py` | API, static resources, authentication, trusted origins/hosts, service lifecycle |
| `api_models.py` | Strict Pydantic contracts, A/B participants and input limits |
| `sessions.py` | Tasks, state, resume, diagnostics, checkpoints and snapshots |
| `coordinator.py`, `events.py` | Single turn loop without Rich; serializable ordered event replay |
| `profile_runtime.py`, `integrations.py`, `adapters/` | Extensible factory/catalog, snapshots, Codex stdio, Ollama NDJSON, OpenAI/OpenRouter SSE |
| `history.py`, `preferences.py`, `paths.py` | Canonical memory, compatible settings and paths |
| `storage.py`, `stats.py`, `exporters/` | Atomic persistence, statistics and offline MD/TXT/HTML |
| `security.py`, `migration.py` | Error redaction and explicit hash-verified copy migration |
| `i18n.py`, `locales/*.json`, `web/src/i18n/` | Independent client language, shared catalogs and presentation formatting |
| `web/src/`, `alterecho/static/` | Svelte/TypeScript source and Python-served build |
| `deploy/`, workflows, Dockerfile and Compose | Services, reverse proxy, packages, native standalone builds and containers |

## Lifecycle and consistency

SessionManager immediately registers a task independent of an HTTP request. Disconnecting does not cancel generation. A lock serializes create/resume and rejects concurrent starts for one conversation. OS leases protect data and the primary history directory from another process. Use one worker only; the initial limit is four active conversations. Duplicate IDs across histories are reported rather than selected arbitrarily.

Histories retain `schema_version=1`, messages, Codex session, `pending` and `partial`. Reads do not migrate existing files. Canonical JSON still uses legacy slots `codex`/`ollama`; public messages/events/API use A/B. Provider identity lives separately in profile snapshots. An API provider in slot A does not acquire Codex checkpoints.

New conversations select registered server profiles by ID/model, never arbitrary executable or filesystem paths. Resume uses saved profiles, not changed catalog entries. A pre-resume JSON backup is retained; Codex verifies its thread and can recover a remote completed response not yet committed locally. Messages are appended only after complete responses. Limits, tools and incomplete streams preserve partials without forwarding them.

The `pending.turn_id` checkpoint commits with the completed message. Existing Codex recovery prevents duplicated memory/responses and rejects external changes or unverifiable incomplete turns. HTTP providers reconstruct memory from complete messages; previous partials remain in backup. Crash recovery never automatically starts inference.

`pause` acts at a turn boundary; `stop` cancels a task and preserves partials. Shutdown cancels tasks, closes adapters and saves/exports through lifespan. Client closure never invokes that path. Task/thread reservations are released even when export fails.

## Events and streaming

Events include `conversation.created`, `conversation.started`, `conversation.stopped`, `conversation.completed`, `conversation.failed`, `conversation.paused`, `conversation.resumed`, `turn.started`, `message.delta`, `message.completed` and `stats.updated`. Each contains `epoch:sequence` ID, type, conversation ID, timestamp and JSON data. Credentials, environment variables, full stderr and internal RPC objects are not exposed.

Adapters call the checkpoint callback's `delta` method when receiving actual provider fragments. Completed responses are never split to imitate streaming. Existing cautious disk-checkpoint cadence remains; a final message is atomically saved before its completion event.

Each conversation has a bounded replay of 2048 events and an asyncio signal, not unbounded per-client queues. SSE honors `Last-Event-ID`. Missing/expired cursors or old epochs yield `state.snapshot` with current messages, partial and state. Snapshot and cursor are atomic within the event loop. Clients deduplicate completions by index. JSON checkpoints are durable; replay is not a disk event store.

## API v1

Authenticated OpenAPI: `/api/v1/docs` and `/api/v1/openapi.json`. Routes below are relative to `/api/v1`.

| Endpoint | Purpose |
| --- | --- |
| `GET /health`, `/version`, `/status` | Minimal liveness, version and active service state |
| `GET /providers`, `/profiles`, `/models` | Providers, profiles and previously checked catalogs |
| `POST /doctor` | Check catalogs without inference, prepare or unload |
| `GET/PUT /settings`, `GET/PUT /profiles` | Shared preferences/profiles without secret values |
| `GET /conversations`, `/history` | Search and status/provider filters |
| `POST /conversations` | Asynchronous start, 202 with ID |
| `GET /conversations/{id}` | Snapshot and statistics |
| `POST .../preflight`, `.../resume` | Read-only verification followed by explicit resume |
| `POST .../pause`, `.../stop` | Turn-boundary pause or immediate stop |
| `GET .../events`, `.../stats` | SSE and statistics |
| `GET .../export/{format}` | JSON/MD/TXT/HTML download |
| `DELETE /conversations/{id}` | Delete selected inactive conversation and its exports/backups |

Health is public and reveals no configuration; other endpoints require `Authorization: Bearer TOKEN`.

```sh
curl -H "Authorization: Bearer $ALTERECHO_TOKEN" http://127.0.0.1:8765/api/v1/status
curl -H "Authorization: Bearer $ALTERECHO_TOKEN" -H "Content-Type: application/json" -d '{"demo":true,"configuration":{"max_turns":2}}' http://127.0.0.1:8765/api/v1/conversations
```

Errors preserve the compatible `detail` field. Application errors additionally provide stable `code`/`params`; catalogs translate them on each client. Validation retains its existing detail list and adds a general localized code. Provider diagnostics are not machine-translated. Recognized error metadata in snapshots/events is additive; canonical histories are not rewritten. Parameters are redacted before exposure.

## Security and resources

Loopback is the default. Nonlocal binding requires a long token, exact origins and allowed hosts. Authentication also applies locally; no session cookies or SSE URL tokens. The browser token exists only in memory. Origin/Sec-Fetch-Site, restricted CORS and Host checks protect against cross-site control and DNS rebinding. Trusted forwarded IPs are explicit; TLS belongs to an external proxy.

Strict Pydantic models reject extra fields. Bodies are limited to 256 KiB and generation parameters are bounded. There is no arbitrary shell/file API. Executables and directories belong to the server owner. Downloads use indexed IDs and enumerated formats; symlinks outside configured roots are not exposed. Validation never reflects submitted inputs. Operational errors redact known keys/tokens. Uvicorn access logs are disabled; responses set CSP, nosniff, no-referrer and frame denial.

Per-IP limits: 30 writes/minute, 240 reads/minute and eight simultaneous SSE streams. The shared token grants administrative access; there are no individual users/roles. Protect service-account token files. Use HTTPS/VPN on untrusted transports.

Codex retains forced ChatGPT login, strict configuration, disabled tools/MCP/apps/plugins, RPC event checks and no prompt shell. Provider API keys/service tokens are stripped from the Codex child environment. HTTP adapters use official endpoints, disable redirects/environment proxies and reject tools. Ollama requires loopback or server allowlist; keep-alive and conservative unloading remain unchanged.

## Frontend, languages and packaging

`ConversationView`/`MessageBubble` retain stable message identity across deltas/completion. Markdown is recomputed only when that message text changes. `requestAnimationFrame`, `tick` and `ResizeObserver` coordinate scrolling; manual navigation disables follow. Scroll positions stay in session memory. SSE recovery applies atomic snapshots/cursors, never an uncursored active GET before replay.

`ModelSelector` uses saved profile catalogs and does not silently replace missing models. `ConfirmDialog` contains focus, initially focuses Cancel, supports Escape and restores focus. `Toast` is nonblocking. Metered-provider consent remains separate and is rechecked on the server.

One JSON catalog per language lives in `alterecho/locales/`. Python loads packaged resources; Vite eagerly discovers the same files and bundles translations. English is the fallback. Python context-local language and browser stores hold presentation state; no shared server language is introduced. CLI preferences use `client-language.json`; browser preferences use local storage. Changing language does not key/remount conversation components, reset forms or restart SSE. User data never enters translation functions except as escaped/plain interpolation values. [Details](docs/I18N.md).

Svelte 5/Vite/TypeScript build into `alterecho/static`. Markdown disables raw HTML and uses DOMPurify without remote images or active URL schemes. No Electron/Tauri or graphical server environment is required. Offline HTML uses the existing Python renderer and embedded resources/hash CSP; its existing wrapper and original conversation content remain independent of client language.

Wheel/sdist/standalone/Docker include JSON catalogs and static assets. The server extra is optional for a CLI-only installation; PyInstaller shares the entrypoint. Docker compiles UI in a Node stage, packages Python and runs nonroot, with separate Codex state. Supervisors use the same foreground server and explicit persistent home.

Actual results and limits: [i18n verification](docs/VERIFICATION-I18N.md), [release verification](docs/VERIFICATION-RELEASE.md). Historical architecture is preserved in `docs/legacy/`.
