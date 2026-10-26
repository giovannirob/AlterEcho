# AlterEcho user guide

**English** | [Italiano](GUIDA.md)

[Overview](../README.md) · [Services and containers](../deploy/README.md) · [Architecture](../ARCHITECTURE.md)

## Local installation

Use Python 3.11+. Building the frontend requires Node.js 22.12+; wheels and standalone executables already include static assets. Node is unnecessary for serving the Web UI in production. Codex may need its own runtime when installed through npm.

```sh
cd web
npm ci
npm run build
cd ..
python -m pip install ".[server]"
```

A virtual environment is recommended. On Windows, create it with `python -m venv .venv` and install with `.\.venv\Scripts\python.exe -m pip install ".[server]"`. On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python -m pip install ".[server]"`.

With uv: `uv tool install ".[server]"`. A CLI-only computer can use `pip install .` or `uv tool install .`: FastAPI/Uvicorn remain optional. The package contains the server code, but `serve` requires the `server` extra. A non-editable installation does not depend on the checkout location. Legacy `start.*`/`install-user.*` development launchers still reference the checkout virtualenv and are unnecessary for normal installation.

## Local startup and shutdown

`alterecho serve` and `alterecho serve --detach` start the same server in background, without opening windows or a browser. Startup waits up to 30 seconds for an authenticated response from the expected instance, then reports URL, actual PID and log path. The process survives terminal closure; this does not configure startup at boot.

Windows uses `CREATE_NO_WINDOW` and `SW_HIDE`, including with virtualenv Python redirectors. Combining `DETACHED_PROCESS` would cause Windows to ignore the no-window flag. Only `--foreground` keeps the server in the terminal.

```sh
alterecho serve
alterecho status
alterecho web
alterecho down
# Foreground diagnostics; Ctrl+C shuts down the server:
alterecho serve --foreground --host 127.0.0.1 --port 8765
```

`down` manages only the CLI-created local instance for the same account and `ALTERECHO_HOME`. It rejects `--server` and never shuts down a remote server. A separate private loopback channel verifies a random instance identity and secret; a stored PID never authorizes termination. Shutdown waits up to 45 seconds for checkpoints and process exit, without forced kills. Stale metadata is removed only after acquiring the data lease. Unconfirmed launches are stopped by a watchdog.

Detached logs append to `<data directory>/logs/server.log`: with `ALTERECHO_HOME`, `<ALTERECHO_HOME>/data/logs/server.log`; Windows default, `%LOCALAPPDATA%/AlterEcho/logs/server.log`; Linux/macOS, `${XDG_DATA_HOME:-~/.local/share}/alterecho/logs/server.log`. Private control metadata lives under `data/run/managed-server.json`. Protect the whole directory with account permissions/ACLs, do not edit it while running or publish it. Logs are not automatically rotated; archive them while stopped.

Docker, systemd, launchd and WinSW use `serve --foreground` and their supervisor's stop command. `down` does not take ownership of their instances. Do not remove active lease files.

### CLI streaming and Web chat

`watch ID` accepts the same indexed history names/IDs as `resume` and `export`. Completed conversations print and exit. Interactive Rich terminals update the current message and print each completion once; pipes/files receive complete messages without ANSI redraws. Ctrl+C disconnects only the client. SSE resumes from cursors and atomic snapshots without doubling partial text.

The chat has its own scroll region: follow new content at the bottom or read above using wheel, touch or keyboard. The circular arrow returns to the last message. Positions survive navigation in the same browser session, not a full reload. Messages support sanitized progressive Markdown, copy and expandable details; there is no manual chat composer.

Model selectors use verified profile catalogs obtained by `doctor` without inference. Editing a form reuses the catalog until **Refresh models**. Offline providers, empty catalogs, removed models and unsupported reasoning block generation until explicitly corrected. Historical responses keep their original models. Save a new profile's provider/endpoint first, verify its catalog, then choose a preferred model. Start/resume/delete dialogs summarize actions; metered API consent is required for each operation.

## Language

English is the reference language and fallback; Italian is included. Browser Automatic selects the first supported entry from `navigator.languages`, including regional variants. Manual choices are saved in local storage as `alterecho-language`. Selectors are available at login, in settings, in the sidebar and in confirmation dialogs. Switching updates presentation without reloading, resetting drafts or replacing the SSE connection.

CLI precedence is `--lang` → `ALTERECHO_LANG` → saved CLI preference → system locale → English. `auto` at any selected level requests system detection. A command-line override is temporary; **Settings → Language / Lingua** saves `client-language.json` beside `client.json`. The choice does not change server configuration or other clients.

```sh
alterecho --lang en help
alterecho --lang it help
alterecho --lang auto status
```

Conversation topics, prompts, roles, positions, model output, histories and checkpoints are never translated. External provider diagnostic text remains unchanged. [Catalog format and translation guide](I18N.md).

## Server token

The AlterEcho service token differs from ChatGPT login and OpenAI/OpenRouter API keys. The browser keeps it only in memory. Never put it in URLs or screenshots.

First local startup creates `server-token` unless an explicit token is supplied:

| System | Default file |
| --- | --- |
| Windows | `%APPDATA%/AlterEcho/server-token` |
| Linux/macOS | `~/.config/alterecho/server-token`, or under `$XDG_CONFIG_HOME` |
| Explicit `ALTERECHO_HOME` | `<ALTERECHO_HOME>/config/server-token` |

Read it in your file manager, with `Get-Content "$env:APPDATA/AlterEcho/server-token"` in PowerShell, or `cat ~/.config/alterecho/server-token` on Linux/macOS. Paste it into Web login. The local CLI under the same account reads it automatically. `ALTERECHO_TOKEN`/`ALTERECHO_TOKEN_FILE` override it, and the generated file may not exist. Protect tokens with account ACLs/permissions.

### Prepare the Docker token

Create `secrets/service-token.txt` before starting Compose. This command also works in PowerShell and refuses to overwrite an existing file:

```sh
python -c "from pathlib import Path; import secrets; p=Path('secrets'); p.mkdir(exist_ok=True); f=(p/'service-token.txt').open('x', encoding='utf-8'); f.write(secrets.token_urlsafe(32)); f.close()"
```

Without host Python, generate a value with `docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_urlsafe(32))"`, then save it to the file. Never use an example token. Container UID 10001 must be able to read it while other accounts are restricted. On Linux Docker Engine without user remapping:

```sh
chmod 700 secrets
sudo chown 10001:10001 secrets/service-token.txt
sudo chmod 400 secrets/service-token.txt
```

Afterward use `sudo cat secrets/service-token.txt` to read it on the host. Adapt ownership for rootless/user-remapped Docker. With Docker Desktop, verify container access and protect host ACLs. Do not expose the port or weaken authentication to work around file permissions.

## Server, CLI and browser

Start the server with the provider environment configured:

```sh
alterecho serve
```

The default is **http://127.0.0.1:8765**, without network exposure or inference. The token value is never printed in startup logs. Operations are authenticated even on localhost.

```sh
alterecho
alterecho doctor
alterecho status
alterecho run
alterecho demo --turns 4
alterecho run --non-interactive --detach
alterecho watch ID
alterecho pause ID
alterecho stop ID
alterecho resume ID --turns 20 --detach
alterecho export ID --format html
alterecho web
alterecho help
```

`doctor` checks catalogs without inference or unloading. Demo uses server-owned simulated adapters. The menu provides new conversations, archive, resume, deletion, viewing and settings, all through the API.

Limits count **total messages**, not pairs. Resuming to 20 includes saved messages. `pause` finishes the current turn; `stop` interrupts and preserves partials. Ctrl+C in a client does neither. `export` writes explicit offline downloads into the current directory and refuses overwrites; these are not an independent operational history. API/browser additionally offer canonical JSON. Standalone HTML exports remain separate from the Web UI.

`watch`, `resume` and `export` accept IDs and indexed server JSON names. Local client paths never upload files. `run --config FILE.toml` supplies dialogue options only: paths, executable choices and profiles belong to the server. Shared settings are available in both clients; storage/Codex installation and credential paths are configured directly on the server.

## Providers and profiles

Profiles separate A/B from the actual provider. Currently Codex CLI can occupy only A, and only one Ollama participant is allowed. OpenAI/OpenRouter are metered; a catalog entry does not guarantee chat compatibility or account access. Claude Code is not implemented.

Use Web settings or **Settings → Models and adapters → Adapters and integrations**. Verify catalogs and choose a Codex reasoning level supported by the model. HTTP adapters use native streaming, usage and complete history without executing tools.

Codex uses the official app-server, ChatGPT login, persistent threads and verified resume. It is not replaced by OpenAI API. On the server under its own account:

```sh
codex login
# Headless device login, if enabled for the account:
codex login --device-auth
codex login status
```

Device authentication depends on account/workspace policy. [Official authentication documentation](https://learn.chatgpt.com/docs/auth). AlterEcho does not return `auth.json` or log in automatically. Services use explicit protected `CODEX_HOME` or `codex_home`. Do not share a live thread with other applications.

Install Ollama and pull the chosen model explicitly. `ollama_keep_alive=-1` remains the default; final unload is skipped without verifiable exclusive usage. For Docker/LAN, authorize exact trusted hostnames on the server:

```sh
export ALTERECHO_OLLAMA_HOSTS=ollama,host.docker.internal,192.168.1.20
```

Set the profile URL, e.g. `http://ollama:11434`. Loopback HTTP remains the default. Credentials in URLs, redirects, paths, query strings and unauthorized hosts are rejected. Use TLS/VPN when appropriate.

Set `OPENAI_API_KEY`/`OPENROUTER_API_KEY`, or a profile's registered variable, only in the **server environment**. Never put values in CLI requests, Web forms, TOML, `adapters.json` or URLs.

```sh
alterecho run --non-interactive --confirm-paid
alterecho resume ID --turns 20 --confirm-paid
```

Interactive CLI asks for confirmation; Web requires explicit checkbox consent; API requires `confirm_paid: true`. Resume always requires fresh confirmation.

## CLI on another computer

```sh
alterecho --server https://echo.example.org connect --token-file /protected/path/service-token
alterecho status
alterecho run
```

`client.json` saves only endpoint and a local token-file reference. `ALTERECHO_SERVER`, `ALTERECHO_TOKEN` and `ALTERECHO_TOKEN_FILE` are also supported. Global `--server` precedes the command. An unavailable server produces guidance, never a fallback generation engine.

## LAN and remote access

Network binding requires a token of at least 32 characters, exact origins and allowed hosts. PowerShell example:

```powershell
$env:ALTERECHO_TOKEN_FILE = 'C:\ProgramData\AlterEcho\service-token'
$env:ALTERECHO_ORIGINS = 'http://192.168.1.20:8765'
$env:ALTERECHO_ALLOWED_HOSTS = '192.168.1.20,127.0.0.1,localhost'
alterecho serve --host 0.0.0.0 --port 8765
```

Generate a random token with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and protect its file. Linux/macOS use `export` and permissions such as `0600`. Plain HTTP carries the token in cleartext; use a trusted LAN, VPN or preferably an HTTPS reverse proxy.

For Internet access keep the backend on loopback and publish only a TLS proxy. Adapt [Caddyfile](../deploy/Caddyfile) to real DNS/domain:

```sh
export ALTERECHO_TOKEN_FILE=/etc/alterecho/service-token
export ALTERECHO_ORIGINS=https://echo.example.org
export ALTERECHO_ALLOWED_HOSTS=echo.example.org,127.0.0.1,localhost
export ALTERECHO_PROXY_IPS=127.0.0.1
alterecho serve
```

SSE needs immediate forwarding: Caddy `flush_interval -1`, or Nginx `proxy_buffering off` with adequate timeouts. No wildcard origins or trusted proxies. VPNs/private tunnels work too; AlterEcho neither manages certificates nor requires a cloud service.

### Nginx example

Adapt the domain and existing certificates. This example has not been deployed to a real domain:

```nginx
server {
    listen 443 ssl;
    server_name echo.example.org;
    ssl_certificate /etc/letsencrypt/live/echo.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/echo.example.org/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

Keep the token, exact origin/hosts and `ALTERECHO_PROXY_IPS=127.0.0.1` as above; do not expose the backend port. [Nginx proxy reference](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

## Paths, backup and migration

Existing `config.json`, `adapters.json`, schema-1 histories, exports and Codex checkpoints remain readable. Legacy `codex`/`ollama` slots map to A/B in API presentation; they are not provider IDs. Saved profiles remain authoritative for resume even when the catalog changes.

| Data | Default |
| --- | --- |
| Windows configuration | `%APPDATA%/AlterEcho` |
| Linux/macOS configuration | `$XDG_CONFIG_HOME/alterecho` or `~/.config/alterecho` |
| Histories | Native Documents directory, `AlterEcho/conversations` |
| Absolute `ALTERECHO_HOME` | `config/` and `data/conversations/` below that directory |

Custom paths, legacy directories and old checkout `outputs/conversations` are still searched. Reading never rewrites history. A crash-left `running` state is shown as `interrupted`; resume is explicit. Deletion removes only that conversation and its backups/exports. Before resume, `.backups/*.bak` preserves the JSON and Codex verifies the thread. Partial/incomplete turns never become complete messages.

Before changing account or machine, stop gracefully and back up configuration, histories and Codex state separately.

```sh
alterecho migrate /old/histories /new/histories
alterecho migrate /old/histories /new/histories --apply
```

The first command produces a read-only SHA-256 plan. `--apply` copies only to a new/empty destination, verifies hashes and retains originals; symlinks and unknown JSON are rejected. Authentication/client files are not automatically copied. Internal paths are not rewritten: review `output_dir`, `codex_work_dir`, `codex_home`, executable paths and `history_directories` in the new server configuration, preserving the previous backup. Transfer Codex state only through official procedures with restricted permissions. Histories remain byte-for-byte unchanged during copying.

Services/containers must use an absolute persistent `ALTERECHO_HOME`, independent of desktop Documents folders.

## System services and Docker

Templates are not installed automatically. [Deployment guide](../deploy/README.md) covers systemd, system launchd and WinSW, all running `serve --foreground` under an appropriate restricted account with its own provider state.

Docker builds Svelte, packages Python and includes Codex CLI. Ollama stays external. No model weights or credentials enter the image. Runtime UID/GID is 10001, with healthcheck, SIGTERM and separate persistent data/config and Codex volumes.

```sh
docker compose build
docker compose up -d
docker compose exec alterecho codex login --device-auth
docker compose logs -f alterecho
```

Compose binds only `127.0.0.1:8765` and uses `restart: unless-stopped`. Login is manual, never an automated test. Configure Ollama as `http://host.docker.internal:11434`, a separate container on a shared network, or a trusted LAN host. Inside Docker, localhost is the container itself. Volumes `alterecho_data` and `codex_state` survive `compose down`; **never use `down -v` to update**. Codex state must be writable for refresh/checkpoints. Never mount an entire personal home. `CODEX_VERSION` defaults to the explicitly pinned version in the Dockerfile, not `latest`.

## Build and verification

```sh
python -m pip install -e '.[dev]'
python -m unittest discover -v
cd web
npm ci
npm run check
npm test
npm run build
npx playwright install chromium
npm run test:e2e
cd ..
python -m build
python deploy/check-package.py --clean-install
```

Standard tests use mock providers and simulated Codex app-server, never AI quotas. Playwright starts a temporary backend on `127.0.0.1:18876`; results go to `web/test-results/`. Set `ALTERECHO_BROWSER_DEV=1` for Vite development mode without a production frontend build. Normal CI checks Windows/Linux/macOS on Python 3.11–3.13 and frontend/browser tests. Only the [tag-triggered release workflow](RELEASE.md) builds distributable packages/containers.

Standalone: install `.[standalone]`, then run `python -m PyInstaller deploy/alterecho.spec` after frontend build. Each target needs its own native build; no Codex, Ollama, weights or user home is bundled. JSON catalogs are included in Python, standalone and Docker; the Web UI bundles them at build time and needs no translation service.

For updates, stop, back up, install the new non-editable wheel/image and restart. Never start multiple Uvicorn workers or two servers on the same data. When upgrading from 1.0, stop the old process using its original supervisor/Ctrl+C; `down` only recognizes new managed 1.1 instances. Nondefault ports require client `--server URL` or `connect`.

## Troubleshooting and limitations

- **Server unreachable:** check startup, endpoint and port. A CLI does not start a fallback engine.
- **401:** missing/wrong service token, distinct from provider keys or ChatGPT login.
- **403 / invalid host:** check exact origins, hosts, proxy/domain and browser URL.
- **Codex missing/login absent in a service:** configure server PATH, `codex_binary`/`codex_home`, account and permissions.
- **Resume rejected:** preserve files; inspect thread, limits, incomplete turns and concurrent dialogues. Demo histories cannot resume with real models.
- **Frontend 503:** build `web/` or install a package containing static resources.
- **Unexpected language:** check explicit `--lang`, `ALTERECHO_LANG`, local preference and system/browser language order. Choose Automatic to redetect.
- **Ollama memory:** other applications' models are never automatically unloaded; choose timed keep-alive if desired.

The server uses one process and a shared administrative token, without separate users/roles. Checkpoints are durable; SSE replay is bounded and in memory, with a canonical snapshot after restart/expired cursor. Crashed inference is not restarted automatically. There is no distributed database or standalone desktop engine.

Current verification: [i18n](VERIFICATION-I18N.md), [release pipeline](VERIFICATION-RELEASE.md), [1.1 application](VERIFICATION-1.1.md). Historical 0.3 documents remain in `legacy/`.
