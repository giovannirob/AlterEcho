# Persistent installation

**English** | [Italiano](README.it.md)

These are procedures to review on the target system, not automatic installation actions. Services run the same `alterecho serve --foreground` with absolute persistent directories and a restricted account. Test foreground startup, back up and configure providers under that account first. [Complete user guide](../docs/GUIDE.md).

## Installation from GitHub Releases and GHCR

The release workflow is prepared for new `vMAJOR.MINOR.PATCH` tags. Actual remote publication still needs verification. Once available, use an authorized account to obtain [release assets](https://github.com/giovannirob/AlterEcho/releases) and verify checksums. Only built and tested platforms are listed in a completed release.

```sh
python -m pip install "alterecho-1.2.0-py3-none-any.whl[server]"
alterecho serve
```

Extract standalone archives into a stable directory. Use `./alterecho serve` on Linux/macOS or `./alterecho.exe serve` on Windows. The binary includes CLI, server, Web assets and language catalogs; Codex/Ollama remain external. Linux release builds require glibc 2.35+. macOS binaries are unsigned/not notarized; verify provenance and make an explicit Gatekeeper decision without disabling system protection globally.

For private GHCR, [authenticate](../docs/RELEASE.md#docker--ghcr), prepare `secrets/service-token.txt`, then use the image-only Compose file:

```sh
export ALTERECHO_VERSION=1.2.0
docker compose -f compose.registry.yaml pull
docker compose -f compose.registry.yaml up -d --no-build
docker compose -f compose.registry.yaml logs -f
docker compose -f compose.registry.yaml stop
```

PowerShell uses `$env:ALTERECHO_VERSION='1.2.0'`. Select an actually published version; only stable releases update `latest`. The image-only Compose file keeps localhost, persistent volumes, a separate token secret and nonroot user. Keep the same Compose project and back up volumes before updates; never use `down -v`. Original `compose.yaml` still builds from source. [Maintainer instructions](../docs/RELEASE.md) cover permissions, tags and failed publications.

## Local background mode versus services

Since 1.1, plain `serve` starts in background, reports URL/PID/log and survives terminal closure; `down` stops that verified local instance. This does not enable startup at boot. Services explicitly use **`serve --foreground`** and their own stop command. `down` does not control systemd, launchd, WinSW or Docker instances. Do not delete leases while active.

Background logs live in the data directory under `logs/server.log`. Supervisor logs use its configured files/journal. Language preferences belong to individual clients, not the service: a service's English diagnostic details can be displayed by an Italian CLI/browser.

## Linux / systemd

Administrator-reviewed example for a distribution with `useradd` and Python 3.11+:

```sh
sudo useradd --system --home /var/lib/alterecho --shell /usr/sbin/nologin alterecho
sudo install -d -o alterecho -g alterecho -m 0700 /var/lib/alterecho /var/lib/alterecho-codex
sudo install -d -m 0755 /opt/alterecho
sudo python3 -m venv /opt/alterecho/venv
sudo /opt/alterecho/venv/bin/pip install '/path/alterecho-1.2.0-py3-none-any.whl[server]'
sudo install -d -m 0750 /etc/alterecho
sudo install -m 0644 deploy/systemd/alterecho.service /etc/systemd/system/alterecho.service
```

Copy `server.env.example` to `/etc/alterecho/server.env` and edit it. Secret-containing environment files should be `0600 root:root`; systemd reads them before switching accounts. Install Codex in an accessible location, configure `codex_binary` in `/var/lib/alterecho/config/config.json` or PATH in the environment file. Perform official login as `alterecho` with `CODEX_HOME=/var/lib/alterecho-codex`; do not run inference for diagnostics.

After validating configuration:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now alterecho
sudo systemctl status alterecho
sudo journalctl -u alterecho -f
sudo systemctl stop alterecho
```

`ProtectHome=true` prevents accidental use of an interactive home. For histories outside permitted directories, explicitly migrate/copy after backup, update configuration and `ReadWritePaths`, and verify permissions.

## macOS / system launchd

Use a service account `_alterecho` created by an administrator according to the Mac's policies. A user LaunchAgent does not provide operation without desktop login.

1. Create `/var/lib/alterecho` and `/var/lib/alterecho-codex`, owned by `_alterecho`, mode `0700`.
2. Install the wheel with `server` extra into `/opt/alterecho/venv`.
3. Install/authenticate Codex for that account using explicit home. Verify binary/PATH: Homebrew ARM/Intel locations differ.
4. Adapt `deploy/launchd/org.alterecho.server.plist`. For network access, add token-file, origins and hosts in `EnvironmentVariables`; never place secret values in a public plist.
5. Prepare private writable logs. Install the plist as `root:wheel`, mode `0644`, under `/Library/LaunchDaemons/`.

```sh
sudo plutil -lint /Library/LaunchDaemons/org.alterecho.server.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/org.alterecho.server.plist
sudo launchctl print system/org.alterecho.server
sudo launchctl bootout system /Library/LaunchDaemons/org.alterecho.server.plist
```

The template enables `RunAtLoad` and `KeepAlive`. Service account creation and native launchd installation have not been tested locally by this work.

## Windows / WinSW

Use an official [WinSW release](https://github.com/winsw/winsw) compatible with the template XML. Follow its [service-account documentation](https://github.com/winsw/winsw/blob/v3/docs/xml-config-file.md). No wrapper is downloaded/installed automatically.

Example preparation in an administrator PowerShell, after reviewing paths:

```powershell
python -m venv C:\ProgramData\AlterEcho\venv
C:\ProgramData\AlterEcho\venv\Scripts\python.exe -m pip install 'C:\packages\alterecho-1.2.0-py3-none-any.whl[server]'
```

Place WinSW at `C:\ProgramData\AlterEcho\AlterEcho.exe` and copy `windows/AlterEcho.xml` beside it with the matching base name. Create `state`, `codex` and `logs`. The template uses **LocalService**, not LocalSystem. ACLs should allow LocalService to modify only data/Codex/log directories; protect program files from nonadministrative modification. For a dedicated account, adapt `serviceaccount` to the selected WinSW version and grant service logon rights. Do not store plain passwords in shared files.

Codex must be accessible to that service, with explicit `codex_binary` if needed. Desktop ChatGPT login is not service login: use dedicated protected Codex state and official authentication/secure transfer, never publish `auth.json`. Verify token, session and model access under the service account.

Manual commands, after review:

```powershell
C:\ProgramData\AlterEcho\AlterEcho.exe install
C:\ProgramData\AlterEcho\AlterEcho.exe start
C:\ProgramData\AlterEcho\AlterEcho.exe status
C:\ProgramData\AlterEcho\AlterEcho.exe stop
```

WinSW forwards shutdown to the console process with its configured timeout. Validate stop behavior for the actual release/account before production. No desktop session is required. The wrapper in ProgramData is distinct from the packaged standalone executable.

## Docker and headless Codex

Generate `secrets/service-token.txt` in the checkout; it is excluded from the image. Confirm UID 10001 can read it and other users cannot. [Token generation/permissions](../docs/GUIDE.md#prepare-the-docker-token). Do not make Codex credentials globally readable.

```sh
docker compose build
docker compose up -d
docker compose exec alterecho codex login --device-auth
docker compose ps
```

Device login must be enabled by account/workspace policy; see [official authentication](https://learn.chatgpt.com/docs/auth). `codex_state` preserves credentials and sessions and must be writable for refresh/checkpoints. No authentication file is baked into the image.

Ollama may run on the host (`host.docker.internal`), another container on a shared network (`ollama`) or a trusted LAN server. Update `ALTERECHO_OLLAMA_HOSTS` and the profile; do not expose Ollama automatically. OpenAI/OpenRouter keys can enter the server container through a protected, untracked environment file.

For a separate proxy container use a shared private Docker network without exposing the application port externally. Allow the required hostname, exact HTTPS origin and only actual trusted proxy IPs. Catalogs are packaged locally and need no runtime network access for translation.

## Updates and backup

Stop gracefully, securely back up data/config and Codex volumes, update the package/image and restart. Never use `compose down -v` for upgrades. Keep previous JSON/path backups; directory migration is explicit and never rewrites histories.

Standalone builds use `python -m PyInstaller deploy/alterecho.spec` after frontend build. Each OS needs its own build; no Codex, Ollama or models are bundled. Python packages remain the primary installation route. Native Linux/macOS services remain prepared rather than locally certified; [verification reports](../docs/VERIFICATION-I18N.md) distinguish actual tests from pending checks.
