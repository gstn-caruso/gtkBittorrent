# GTK migration and continuous release plan

Status: implementation in progress; Linux baseline, isolated fork identity, and explicit profile import established.

Assessment date: 2026-10-22.

## Verified progress and continuation

Update this section at verified checkpoints. Mark work complete only after its
relevant checks pass; retain unfinished stage criteria when part of a stage is
delivered.

- [x] Build the inherited Linux desktop and headless applications and pass the
  22 inherited test executables.
- [x] Verify local peer transfer, restart/resume, interrupted settings recovery,
  and frozen legacy/SQLite sessions with real-engine integration tests.
- [x] Establish separate fork identity, executable names, profile directories,
  and command-line environment variables.
- [x] Provide a Qt-free explicit profile importer; verify imported sessions with
  the real engine and confirm source profiles remain unchanged.
- [x] Validate staged Linux installations and fork desktop metadata.
- [ ] Complete the remaining behavior baseline, including proxy/DNS handling.
- [ ] Verify native Windows/macOS installations.
- [ ] Complete release packaging, CI integration, and installed-package smoke
  tests; verify an actual downloadable prerelease.
- [ ] Move the default branch to `main` and verify automatic releases per push.
- [ ] Implement the GTK client/engine boundary and interface.
- [ ] Reach feature parity and remove Qt throughout the application and packages.

Current checkpoint: [release tools](dist/release/README.md) provide a Linux build
driver, Debian packager, and immutable prerelease publisher. Fourteen local tests
pass, including a real fixture package build/extraction and repeated-packaging
byte comparison. Publication tests cover retries, interrupted uploads,
source/asset integrity, and tag collisions without network writes. The pinned
Ubuntu build image builds successfully. These checks do not yet establish that
the full application package or the GitHub pipeline works; no release has been
published.

Resume by building the full application in the release container, checking the
installed package in a clean runtime container, and wiring publication behind
the existing CI checks and package smoke tests. See the release tools guide for
commands. Preserve the full migration scope and use targeted tests for each
change. The current branch is `master`; the latest pushed checkpoint is
`9bdebfb40` (isolated profiles and explicit import). Inspect the worktree before
continuing.

Keep this checkpoint current before context compaction so continuation does not
depend on chat history. The migration remains in progress until all completion
criteria below are met.

## Objective and agreed direction

Migrate this qBittorrent fork completely to GTK, preserving its torrent engine,
features, saved sessions, and remote-control capabilities. Keep and adapt the
existing CI, and publish a release after every successful push to `main`, including
pushes resulting from merges.

A complete migration includes the interface, backend, application lifecycle,
tests, build tools, and distribution packages. A GTK interface with a Qt backend
is an intermediate milestone, not the final result.

The proposed stack is C++20, GTK 4.24.1, gtkmm, CMake, and libtorrent. GTK 4.24.1
was the latest release found in the official source archive and API documentation
at the assessment date. Pin validated dependency versions for reproducible
releases and review updates deliberately.

- [GTK source releases](https://download.gnome.org/sources/gtk/4.24/)
- [gtkmm documentation](https://gnome.pages.gitlab.gnome.org/gtkmm/)

## Repository baseline

The fork identifies its base as qBittorrent `5.4.0alpha1`. Both the local branch
and the GitHub default branch were `master` at the assessment date.

Approximate source sizes exclude bundled third-party code and count C++ headers,
implementation files, and Qt Designer forms:

| Area | Size | Migration implications |
| --- | --- | --- |
| `src/gui` | 57,000 lines; 37 Qt Designer forms | Rebuild the interface and presentation models |
| `src/base` | 49,000 lines | Replace Qt events, networking, settings, SQL, XML, and utility types |
| `src/app` | 4,700 lines | Replace startup, lifecycle, instance handling, and resources |
| `src/webui` | 11,000 C++ lines | Preserve WebUI/API behavior while replacing Qt infrastructure |
| `test` | 22 test sources | Preserve behavior coverage while replacing Qt Test |

The backend links Qt Core, CorePrivate, Network, SQL, XML, and conditionally
D-Bus. Disabling the GUI does not remove Qt. Relevant build definitions:

- [Backend](src/base/CMakeLists.txt)
- [Application](src/app/CMakeLists.txt)
- [WebUI](src/webui/CMakeLists.txt)
- [Tests](test/CMakeLists.txt)
- [Dependency discovery](cmake/Modules/CheckPackages.cmake)

At the assessment, Qt, gtkmm, and libtorrent development dependencies were missing.
They are now installed locally. Linux desktop and headless builds pass the 22
inherited test executables, and staged installations run. The headless build also
passes session integration checks covering local peer transfer, persistence,
settings recovery, and loading frozen legacy/SQLite resume fixtures. See the
[behavior baseline](test/MIGRATION_BASELINE.md) for commands, evidence, the feature
inventory, and remaining validation gates.

Fork identity is now `gtkBittorrent`, with application ID
`io.github.gstn_caruso.gtkBittorrent`, separate profile/settings directories, and
`GTKB_` command-line environment variables. Executables are `gtkbittorrent`,
`gtkbittorrent-engine`, and the Qt-free `gtkbittorrent-import`. The importer
supports closed custom profiles and explicit configuration/data directories;
real-engine tests verify imported legacy and SQLite sessions without modifying
their sources. See the [import guide](src/profile/README.md).

Linux installation metadata and the existing workflow executable paths have been
adapted. Native Windows/macOS installation verification, the branch move, and
automatic prereleases remain pending. Neither the desktop nor the torrent
engine is Qt-free yet.

## Migration stages

Each stage must leave a buildable application and satisfy its completion criteria
before the next stage depends on it.

### 1. Establish behavior and data baselines

Build the inherited application and run its existing tests. Inventory the
supported behavior across torrents, magnets, files, trackers, categories, tags,
limits, RSS, search, Lua plugins, WebUI, and desktop integration.

Create reproducible fixtures for settings and resume data, including Unicode
paths and interrupted downloads. Record the inherited behavior of proxy/DNS
handling, shutdown, and settings writes. Use these fixtures to protect existing
sessions during subsequent changes.

Completion criteria: existing behavior and data formats have a documented
validation baseline, and the inherited application builds and passes its checks.

### 2. Prepare fork identity and continuous releases

Move the default branch from `master` to `main` and update affected references.
Establish gtkBittorrent's application ID, executable names, profile directories,
and package identity. Keep qBittorrent profiles separate and provide an explicit
import path.

Adapt the existing CI and implement the release policy below.

Completion criteria: a successful push to `main` produces an identifiable,
downloadable build with a traceable source commit.

### 3. Define the interface and engine boundary

Introduce commands, torrent identifiers, status snapshots, events, and structured
errors using C++ types. GTK widgets consume this boundary rather than accessing
Qt objects or libtorrent handles directly.

The proposed transition uses a separate headless backend process, initially
accessed through an adapter for the existing Web API. Verify API coverage first
and identify operations that need an additional implementation. Define
authentication, startup, shutdown, crash handling, and ownership of the profile.

Completion criteria: a GTK client can control a test session through this
boundary. The Qt backend remains an explicit temporary dependency.

### 4. Deliver a usable GTK interface

Implement the main window, torrent list, filtering, sorting, torrent/magnet
addition, pause/resume, removal, destination selection, and basic preferences.

Use GTK's current list-model architecture, including `ColumnView`, list models,
filters, and sorters. Deliver engine updates to the GTK main thread and keep
blocking work outside the interface thread.

- [GTK list models](https://docs.gtk.org/gtk4/section-list-widget.html)
- [GTK threading rules](https://docs.gtk.org/gtk4/section-threading.html)

Completion criteria: a user can add, download, restart, and resume a torrent
through the packaged GTK application.

### 5. Reach interface feature parity

Implement file trees and priorities, peers, trackers, graphs, scheduling, share
limits, RSS rules, search, torrent creation, Lua plugins, and advanced preferences.
Include keyboard navigation, accessibility, translations, notifications, file
associations, and desktop integration.

Completion criteria: every baseline feature has an implemented and verified
equivalent, or an explicitly agreed scope change.

### 6. Remove Qt from the backend

Replace infrastructure subsystem by subsystem while preserving the torrent
engine and business rules. The following replacements are proposed directions;
validate compatibility with small trials before adopting them.

| Qt dependency | Replacement direction |
| --- | --- |
| Containers, paths, time, ownership | C++ standard library |
| Signals, timers, queued work | Explicit events and an engine executor |
| HTTP downloads and SMTP | Evaluate libcurl against current proxy/TLS behavior |
| HTTP server | Evaluate Boost.Beast while preserving API behavior |
| SQL storage | SQLite directly, retaining compatible schemas |
| Settings | Versioned storage with a tested importer |
| XML/RSS | A maintained XML parser behind an adapter |
| Desktop services and resources | GIO, GResource, gettext |
| Qt Test | A C++ test framework retaining meaningful behavior coverage |

Give resume data, proxy/DNS behavior, shutdown, and atomic settings writes
particular attention. Verify the WebUI and its API as backend implementations
change.

Completion criteria: the GTK application and headless engine work without the
temporary Qt backend.

### 7. Verify complete removal and distribution

Remove the Qt interface, temporary adapters, MOC/RCC/UIC, Linguist tooling,
Qt Test, and Qt packaging steps. Inspect packaged dependencies as well as source
imports to verify Qt removal.

Prioritize Linux delivery while retaining Windows and macOS as migration
milestones.

Completion criteria:

- Clean environments build and run the application without Qt.
- Imported sessions resume correctly using the baseline fixtures.
- WebUI and API compatibility checks pass.
- Installation and application smoke tests pass on Linux, Windows, and macOS.
- Every retained baseline feature passes its validation checks.

## Existing CI

Six GitHub Actions workflows run on both pushes and pull requests, without
branch filters:

| Workflow | Current work |
| --- | --- |
| [Ubuntu](.github/workflows/ci_ubuntu.yaml) | Six combinations: three libtorrent versions multiplied by GUI/headless; tests, C++ CodeQL, AppImages |
| [macOS](.github/workflows/ci_macos.yaml) | Six combinations; tests and DMG packaging |
| [Windows](.github/workflows/ci_windows.yaml) | Three x64 combinations; tests, packaged files, NSIS installers |
| [WebUI](.github/workflows/ci_webui.yaml) | Tests, lint, formatting, JavaScript CodeQL |
| [Python](.github/workflows/ci_python.yaml) | Type checking, lint, formatting, compilation |
| [File health](.github/workflows/ci_file_health.yaml) | Pre-commit checks, generated documentation checks, workflow analysis |

There is also a scheduled stale-PR bot and Dependabot configuration. Reassess the
stale bot separately from the build pipeline when adapting fork administration.

These workflows upload build artifacts; they do not create GitHub Releases.
GitHub reports Actions enabled for the fork and seven active workflows, but no
workflow runs or commit checks have been returned after the pushes made so far.
Successful execution of the checked-in workflows therefore remains unverified.

Keep and adapt the existing checks. For routine builds, select one validated
libtorrent version and retain the wider compatibility matrix on a schedule.
Keep Python, WebUI, file-health, and security checks while those components remain.
Replace Qt-specific build and packaging steps as their corresponding migration
stages land.

## Continuous release policy

Use one pipeline with this dependency chain:

```text
Push to main
  -> checks and tests
  -> build and package
  -> package smoke tests
  -> GitHub Release
```

- A merge already produces a push to `main`; avoid a separate merge trigger that
  duplicates releases.
- Publish one release for each successful push, using its exact commit SHA.
  A push containing multiple commits produces one release for its head commit.
- During migration, publish prereleases and clearly identify remaining Qt
  dependencies.
- Use an immutable tag such as `build-<commit-sha>`, with binaries, checksums, and
  commit information.
- Make retries reuse that release instead of creating duplicates.
- Grant `contents: write` only to the publishing job.
- Keep main-branch runs uncancelled so every successful push receives a release.
- Build and publish in the same workflow. Do not rely on a token-created tag to
  trigger a second workflow.

See [GitHub workflow trigger behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

## Next implementation milestone

Extend the established baseline for proxy/DNS behavior and the remaining feature
gates, adapt CI, and enable automatic prereleases. Then implement the GTK
client/engine boundary and the first usable GTK interface.

This plan does not change the contribution policy in [AGENTS.md](AGENTS.md): a
human contributor must review and submit issues and pull requests.
