# Tag-triggered builds and releases

**English** | [Italiano](RELEASE.it.md)

`.github/workflows/release.yml` builds distributions only when a **new version tag** is pushed. Creating a local commit/tag does not publish anything. The i18n work is included in version 1.2.0; publication requires an explicit tag push. The first real remote release remains unverified; repository/package visibility is not changed automatically.

## Two workflows

| Event | `test.yml` | `release.yml` |
| --- | --- | --- |
| Branch push, including README-only changes | Python/frontend/browser checks | Does not run |
| Pull request | Same checks, read-only permissions | Does not run |
| Unrelated tag or old unprefixed `1.0.0` | Does not run | Does not run |
| New `v1.2.0` | Called as a reusable workflow | Validate, test, build and publish |
| Matching glob but invalid SemVer, e.g. `v01.2.0` | Not called | Fails validation before builds |
| Deleted/moved tag or duplicate version | Not called | Validation rejects it |

There is no publication `workflow_dispatch`, PR/branch trigger or `workflow_call`. GitHub glob `v[0-9]*.[0-9]*.[0-9]*` is only a prefilter. `deploy/release.py` strictly checks SemVer, push event, `created=true`, `forced=false`, `deleted=false`, version files and the remote tag's peeled commit. Both annotated and lightweight tags are handled.

Normal CI does not invoke `python -m build`, PyInstaller, Docker builds or release uploads. Editable installation tests the CLI launcher, rather than producing packages in `dist/`. Python tests use committed static files. Playwright tests current source through Vite development mode with real HTTP/SSE and mock providers, without production frontend build.

## Order and permissions

```text
validate → tests → frontend → python → standalone (5 native runners)
         → docker-build (2 native runners) → docker-publish → GitHub Release
```

Every phase requires previous success. Both image archives carry architecture/version/commit verification and SHA-256; the publisher validates both before any registry write and publishes those exact tested images without rebuilding.

Default token permissions are `contents: read`. Only Docker publication requests `packages: write`; only final GitHub publication requests `contents: write`. Actions uses `GITHUB_TOKEN`, not a required PAT. There are no provider keys, signing credentials or Codex login in tests. Checkouts do not persist credentials; official GitHub/Docker Actions are pinned to reviewed commit SHAs.

Global release concurrency prevents an active release from being interrupted and serializes `latest`/minor alias updates. Do not push bursts of tags: GitHub may replace a pending run in the same concurrency group.

## Coherent versions without automatic edits

| Component | Stable | Prerelease example |
| --- | --- | --- |
| Git tag | `v1.2.0` | `v1.2.0-rc.1` |
| Python project and runtime | `1.2.0` | `1.2.0rc1` |
| npm package and both lock version fields | `1.2.0` | `1.2.0-rc.1` |
| Python artifact | `alterecho-1.2.0…` | `alterecho-1.2.0rc1…` |
| Specific Docker tag | `1.2.0` | `1.2.0-rc.1` |

Python follows PEP 440; Git/npm follow SemVer. Runtime, CLI and server must exactly match the Python project version. The Web UI displays npm's version. No job rewrites files after checkout. Supported prerelease phases are `alpha.N`, `beta.N`, `rc.N` and `dev.N`; other SemVer identifiers are rejected clearly because they cannot be represented by this Python mapping.

Build metadata such as `+build.4` is supported: Python uses PEP 440 normalization; Docker replaces `+` with `_` because OCI tags reject `+`. OCI version labels retain original SemVer. Docker tags cannot exceed 128 characters. Stable releases must increase beyond published stable versions to avoid rolling `latest` backward. Equivalent unprefixed tags, existing releases/drafts and moved refs are rejected; refs are rechecked before publication.

## Matrix and assets

| Target | Native runner | Asset for `v1.2.0` |
| --- | --- | --- |
| Windows x64 | `windows-2022` | `AlterEcho-1.2.0-windows-x64.zip` |
| Linux x64 | `ubuntu-22.04` | `AlterEcho-1.2.0-linux-x64.tar.gz` |
| Linux ARM64 | `ubuntu-22.04-arm` | `AlterEcho-1.2.0-linux-arm64.tar.gz` |
| macOS ARM64 | `macos-15` | `AlterEcho-1.2.0-macos-arm64.tar.gz` |
| macOS Intel | `macos-15-intel` | `AlterEcho-1.2.0-macos-x64.tar.gz` |
| Python | `ubuntu-22.04` | `alterecho-1.2.0-py3-none-any.whl`, `alterecho-1.2.0.tar.gz` |

Verify runner availability, private-repository policy and billed minutes on the account. Missing required runners stop the release; no platform is silently skipped or cross-compiled fictitiously. Changing supported platforms requires changing both the workflow and `PLATFORMS` in release tooling before a new tag. [GitHub runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Every executable is run outside the checkout: version, foreground/background server, static Web resources, HTTP CLI, demo, persistence and shutdown. Windows also checks for no visible console. Archives contain only executable/guide; Web resources and language catalogs are embedded. Codex, Ollama, weights and credentials are excluded.

Linux release binaries target Ubuntu 22.04/glibc 2.35+, not Alpine/musl or older glibc. macOS 15 builds are unsigned/not notarized; Gatekeeper and older-system compatibility require separate validation. Do not disable Gatekeeper globally.

Wheel and sdist are separately installed into fresh environments and checked for HTTP/CLI/Web/demo/provider metadata and restart persistence, without importing from checkout. No PyPI publication. Intermediate Actions artifacts expire after three days; final distribution is in GitHub Releases.

## Docker / GHCR

Image: `ghcr.io/giovannirob/alterecho`. Stable `v1.2.0` publishes `1.2.0`, `1.2`, `latest`. Prerelease `v1.2.0-rc.1` publishes only `1.2.0-rc.1`, without changing `latest` or the minor alias.

The multistage Dockerfile builds UI, packages Python and supplies Codex runtime; the server is nonroot UID 10001 and runs `serve --foreground` with healthcheck/SIGTERM/persistent volumes. Ollama stays external. Codex is pinned through `deploy/codex-version.txt`, passed as build argument; update Dockerfile/Compose defaults and recheck both architectures when changing it.

Native AMD64/ARM64 jobs actually start each image. `codex --version`/`codex app-server --help` verify binaries without login/inference. HTTP tests use demo. Checks cover architecture, user, command, OCI labels, Web/API, health, saving, restart and shutdown. A multiarch manifest is created only after both pass. Unique `build-RUN-ATTEMPT-ARCH` staging references may remain in Packages; use version tags for installation.

OCI labels include source/revision/version/title/description; `source` associates the package with the repository. Existing version tags are refused. Authentication errors never count as an absent image. The workflow never modifies visibility/policy. Private pulls need an authorized identity: Actions may use `GITHUB_TOKEN` with `packages: read`; local users may use an appropriately scoped PAT classic with `read:packages` and repository/SSO access, per GitHub's supported method.

```sh
printf '%s' "$GHCR_READ_TOKEN" | docker login ghcr.io -u YOUR_USERNAME --password-stdin
docker pull ghcr.io/giovannirob/alterecho:1.2.0
```

Store the read token securely, never in Git. [GHCR authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) · [Actions publication](https://docs.github.com/en/actions/use-cases-and-examples/publishing-packages/publishing-docker-images).

## Manual GitHub configuration

1. Enable Actions, allow pinned official GitHub/Docker Actions, and verify all five native runners and available minutes.
2. Permit the two publication jobs' requested token permissions within organization policy. Do not add provider credentials for tests.
3. For an existing GHCR package created elsewhere, grant this repository Actions write access. Verify repository association, private visibility and read permissions after first publication.
4. Create a tag ruleset for `v*`: restrict creation to authorized maintainers, block updates/deletions and minimize bypasses. Protect workflow changes through branch review. Trigger filters do not replace rulesets.
5. Optionally enable immutable releases manually. The workflow uploads/checks a draft before publication. Signing, notarization and OIDC attestations remain future work, not simulated features.

No settings have been changed remotely by this implementation.

## Maintainer procedure

Review and commit complete source, versions, catalogs, documentation and workflows; check that commit's CI. Update [CHANGELOG.md](../CHANGELOG.md) and its [Italian counterpart](../CHANGELOG.it.md), moving unreleased changes to a dated version when preparing a release. The tag must point to the intended committed tree, not working-copy-only edits. Automatic notes supplement the editorial changelog with repository references.

```sh
git status
git show HEAD:pyproject.toml
git tag -a v1.2.0 -m "AlterEcho 1.2.0"
git push origin v1.2.0
```

The release tag must point to the reviewed commit. To publish this prepared version, push only its explicit references:

```sh
git push origin main v1.2.0
```

This sends no `v1.1.0` tag. Its former local tag is retained only under `refs/alterecho/archived-tags/v1.1.0`, outside `refs/tags/`. Local `push.followTags=false` prevents implicit annotated-tag publication. Do not recreate/push the old tag or use an indiscriminate tag push when publishing a selected release. Pushing a branch's history does not publish ancestor tags.

GitHub Release creation/upload is automatic. Notes include version/date, generated changes, actual assets and Docker digest/instructions. `SHA256SUMS.txt` covers all seven payloads plus `release-manifest.json`; the manifest records tag, commit, platforms and image digest. Uploads are checked against GitHub's returned size/digest before removing draft state. Prereleases do not become latest.

## Failed releases

- Before publication, correct the cause. For transient failures, **Re-run failed jobs** while successful-job artifacts remain available.
- Interrupted GitHub uploads leave a private draft identified by run ID/commit. Only that draft can resume; matching assets are reused by digest/size. Foreign drafts or differing assets are not overwritten.
- If GHCR succeeded and Release upload failed, rerun only the failed Release job. Rerunning successful Docker publication is rejected because the version exists. GHCR and GitHub Releases are not one atomic transaction; the workflow never deletes remote objects for rollback.
- If artifacts expired, a build must change or a tag is wrong, prepare a new version/new tag. Never move a published tag. Draft/staging cleanup is manual and reviewable.

## Local checks without publication

```sh
python -m pip install -e '.[dev]'
python -m unittest tests.test_release tests.test_i18n -v
python -m unittest discover -q
cd web
npm run check
npm test
# Set ALTERECHO_BROWSER_DEV=1 for development-mode browser tests:
npm run test:e2e
npm run build
cd ..
python -m build
python deploy/check-package.py --clean-install
python -m PyInstaller --noconfirm deploy/alterecho.spec
python deploy/check-standalone.py dist/alterecho.exe
```

Use `dist/alterecho` on Linux/macOS. `publish-docker` and `publish-release` write remotely and must not be used without authorization. Tests inject fake HTTP/registry clients; no test tag is needed to verify triggers, versions, DAG, duplicates, checksums or interrupted uploads. [Recorded results](VERIFICATION-RELEASE.md).
