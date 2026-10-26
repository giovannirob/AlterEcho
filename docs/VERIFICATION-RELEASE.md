# Release-system verification

**English** | [Italiano](VERIFICA-RELEASE.md)

Recorded on **26 October 2026**, before the subsequently authorized local 1.1.0 commit/tag. No version-1.1 push, remote workflow run, GitHub Release or GHCR publication was performed. Publication tests used fake clients. Later i18n checks are recorded [separately](VERIFICATION-I18N.md).

## Implemented scope

Separate ordinary CI and new-tag-only release workflow; strict tag/version/remote-ref checks; native build matrix; clean wheel/sdist installs; archive/checksum/manifest generation; verified image transport; GHCR publishing; draft creation and digest-checked uploads before final publication. Codex is fixed through `deploy/codex-version.txt`. README/deployment/maintainer documentation covers downloads, private GHCR and failed-release recovery. The conversation engine was not rewritten.

## Actual local results

| Check | Result |
| --- | --- |
| Python on Windows/Python 3.12 | 150 tests passed, including 14 offline release tests |
| Frontend | 11 tests passed; Svelte/TypeScript: zero errors/warnings |
| Playwright through Vite development mode | 12 desktop/emulated-mobile tests passed, no production build required |
| actionlint 1.7.12 | Both workflows valid; official download hash verified |
| Wheel/sdist 1.1.0 | Built, inspected and separately installed into clean venvs; HTTP/CLI/Web/demo/restart outside checkout passed |
| Windows x64 standalone | Version, foreground/background, no visible console, down, Web/demo/persistence passed; local archive produced |
| Linux x64 standalone | Built/run in Debian bookworm; smoke passed with glibc 2.36, not the future Ubuntu 22.04/glibc 2.35 runner |
| Docker AMD64 | Local build passed nonroot, labels, foreground, Codex 0.164.0, health/API/Web/demo, SIGTERM and restart persistence |
| Docker ARM64 | Actually built and run in Docker Desktop emulation; same checks passed, including native ARM64 Codex binary under emulation |
| Image archives | Saved with version/architecture/revision/hash records, without registry push |
| Distribution content | Required resources and forbidden credential/path checks passed; no weights or authentication files included |

UUID-labeled temporary image-test containers/volumes were verified before cleanup. Ignored `dist/`/`.runtime-test/` hold local outputs. OCI revision was explicitly `local-uncommitted`, not a claimed remote commit. The final Web version-display binding was checked by frontend tests/build and included in rebuilt Python packages; standalone/image operational smoke preceded only that text-binding adjustment.

## Acceptance coverage

1. Main/branch pushes do not distribute: trigger/command tests and actionlint.
2. PRs cannot publish: no release PR trigger; read-only CI; event tests.
3. Invalid tags are rejected: strict SemVer/event/prerelease mapping tests.
4. Valid new tags enter the pipeline: trigger/DAG statically verified, remote execution pending.
5. Incoherent versions fail: project/runtime/npm/lock tests without mutation.
6. Failed checks gate publication: transitive job-dependency tests.
7. Wheel/sdist install: real clean-environment tests.
8. Standalone outside repo: Windows/Linux x64 tested; other native targets pending.
9. Web resources included: archive inspection and installed HTTP JS/CSS checks.
10. Headless foreground Docker: actual command inspection and runtime checks.
11. Multiarch requires two tested images: both records verified before writes, manifest checked in mocked publication tests.
12. GHCR tags correct: mocked stable/prerelease publication tests; real auth/push pending.
13. Release files/checksums complete: exact seven payloads, manifest, interrupted upload and own-draft resume tests.
14. Prereleases preserve latest: Docker tags and GitHub `make_latest=false` tested.
15. No overwrites: existing releases/foreign drafts/moved tags/modified assets/existing image versions rejected.
16. No personal files: inspected packages, restricted standalone archive contents and denylist tests.

The [previous remote run](https://github.com/giovannirob/AlterEcho/actions/runs/40119953017) was still failed when inspected. Windows/macOS temporary-root normalization fixes were preserved; no tests were removed or skipped to work around path comparisons. A new successful remote macOS CI is not claimed.

## First authorized remote release still needs

- Complete workflows and actual private-repository runner availability/policy/minutes, especially macOS and Linux ARM64.
- Native Ubuntu 22.04/glibc 2.35 and macOS Intel/ARM standalone builds.
- Real GHCR token access, package association/private visibility and authenticated pull.
- Actual two-image push, manifest/aliases, GitHub upload/digests/generated notes and draft publication.
- Manual tag rulesets/optional immutable releases.
- Signing/notarization/attestations remain unconfigured; there is no PyPI publication.

[Release guide](RELEASE.md) documents recovery without tag/version overwrites. GHCR and GitHub Releases are separate services; no automatic destructive rollback is attempted.
