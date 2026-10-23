# GTK migration and continuous release plan

Status: implementation in progress; first prerelease published and a Qt-free GTK preview controls test sessions.

Assessment date: 2026-10-22.

Latest verified checkpoint: 2026-10-23.

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
- [x] Build an Ubuntu 26.04 amd64 release package in a container, install it in a
  clean runtime without development dependencies, and pass import, identity,
  transfer, persistence, and recovery checks against both installed applications.
- [x] Introduce a Qt-free C++ engine client and verify authentication, snapshots,
  torrent/magnet addition, start/stop, removal, and resumed partial downloads
  against disposable real-engine sessions on Linux.
- [x] Add a Qt-free worker with value-based commands/events, FIFO results,
  cancellation, snapshot coalescing, and nonblocking submission; pass local
  address, undefined-behavior, and thread sanitizer checks.
- [x] Build a Qt-free native GTK preview; display Unicode rows and start/stop
  selected torrents through actual widgets against a real disposable engine.
- [x] Publish/download the first CI-tested prerelease and verify its checksums
  and real-engine session/import behavior locally.
- [ ] Complete the remaining behavior baseline, including proxy/DNS handling.
- [ ] Verify native Windows/macOS installations.
- [x] Complete Linux release packaging, CI integration, and installed-package smoke
  tests; verify an actual downloadable prerelease.
- [x] Move the local and GitHub default branch to `main`.
- [ ] Verify the first automatic prerelease and subsequent per-push releases.
- [ ] Implement the GTK client/engine boundary and interface.
- [ ] Reach feature parity and remove Qt throughout the application and packages.

Current checkpoint: [release tools](dist/release/README.md) provide a Linux build
driver, Debian packager, and immutable prerelease publisher. Fifteen local tool
tests pass (ten publisher and five packager tests). Full container builds passed
26 desktop and 27 headless CTest entries.
The resulting 18 MB package passed the real installed-runtime smoke suite for
both applications. Its build manifest is retained outside documentation paths,
which minimal Ubuntu images exclude. Publication tests cover retries,
interrupted uploads, source/asset integrity, and tag collisions without network
writes. All seven push workflows for `e9a353126` passed on GitHub: Ubuntu,
Windows, macOS, Python, WebUI, file-health, and engine-client security/sanitizer
checks. The earlier manual release run also passed its Linux package and clean
installation job; its Python/macOS failures were corrected and verified in the
newer push runs. The first [prerelease](https://github.com/gstn-caruso/gtkBittorrent/releases/tag/build-b6f7379035dc430334f44f312d8a0b1e0c40230c)
is now published. GitHub rewrote `~` in the uploaded package filename, so the
initial publisher refused its checksum/name mismatch. After verifying all
original CI artifact digests and ten passing prerequisite jobs, the draft's
checksum metadata was corrected and publication resumed. Package bytes were
unchanged. The downloaded release passes checksums and all five real-engine
session/import tests. Future packages use safe filenames; automatic publication
with that correction remains to be verified in the next main run.

The [Qt-free engine client](src/engine/README.md) now has thirteen HTTP contract
tests and a real-engine integration test. These pass with address/undefined
behavior sanitizers and in the pinned release container. The public boundary
uses standard C++ identifiers, snapshots, and errors; HTTP/JSON types remain
private. Eight worker tests now verify blocked-server submission, FIFO command
results, recoverable command errors, authentication failure, cancellation,
snapshot coalescing, and owned torrent/magnet/removal payloads. All client and
worker tests pass under address/undefined-behavior sanitizers; the worker tests
also pass under ThreadSanitizer. CI now includes these checks and security
analysis, and release builds exercise the client against the newly built engine.
The [native GTK preview](src/gtk/README.md) now consumes these events in a
`ColumnView` and controls selected torrents. Three local UI cases cover Unicode
rendering/selection, authentication failures, and real partial-download controls
under isolated D-Bus/Xvfb. The window follows GTK theme settings, retains selected
IDs across updates, and joins workers after its application loop exits. Process
lifecycle/profile ownership, advanced API operations, and a usable packaged GTK
application remain pending; this does not complete stages 3 or 4.

The local and remote default branch are now `main`. The first automatic release
run was [39892861397](https://github.com/gstn-caruso/gtkBittorrent/actions/runs/39892861397),
for `b6f737903`. All prerequisite jobs passed; only publication failed before the
verified draft recovery described above. That run is terminal. Inspect the
newest main run to verify the corrected automatic publisher and the new GTK
workflow. Verify a downloadable prerelease with matching commit/checksums before
marking automatic releases complete. Do not restart jobs that are still running.
The native GTK build, widget tests, and security analysis passed in
[39898196612](https://github.com/gstn-caruso/gtkBittorrent/actions/runs/39898196612),
including a clean container without Qt development packages. Its file-health
job rejected GLib's valid `G_DEBUG="fatal-criticals"` token as a spelling error.
A narrow spelling exception now passes the same pinned checker locally; the
runtime setting remains enabled. The corrected source needs another main run
before automatic publication can be verified.
The earlier [manual run](https://github.com/gstn-caruso/gtkBittorrent/actions/runs/39887360562)
is also terminal; the current source includes its verified fixes. Preserve the
full migration scope and use targeted tests for each change. The downloaded and
locally verified public package records `b6f737903`; its artifacts, checksum
recovery record, and session results are under `build/release-recovery` when
available. Earlier build/runtime logs remain under `build/release-verified` and
`build/release-runtime-*.log`. Inspect the worktree and remote state before
continuing.

Next implement GTK file/magnet/removal dialogs, filtering/sorting, and managed
backend/profile ownership. The current preview connects to externally owned
engines and is available from source, not in the release package. Local GTK UI
checks and a rendered screenshot are under `build/gtk-preview`. GTK 4.24.1
dependency validation and native GTK distribution remain pending.
Keep network calls off GTK's main thread; request worker stop without joining
on an active UI thread.
The standalone client build is under `build/engine-client`,
sanitizer checks under `build/engine-client-sanitize`, and release-container
client checks under `build/release-verified/client` when available.
ThreadSanitizer checks are under `build/engine-client-tsan`.

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

Linux installation metadata, workflow executable paths, and the CI dependency
chain have been adapted. GitHub workflows execute, the default branch is `main`,
and the first CI-tested prerelease is published. Native Windows/macOS installer
execution, the corrected fully automatic publisher, and GTK distribution remain
pending. The default desktop and torrent engine still use Qt; the new preview
frontend is Qt-free.

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

Six existing check workflows are retained and reusable. The continuous-release
workflow calls them for pushes to `main`; other branches and pull requests run
the checks directly. A separate engine-client workflow adds sanitizer tests and
C++ security analysis for the new boundary. Routine native builds use
libtorrent 2.0.12, the version
validated locally on Linux. The original wider version matrices run weekly or
through manual dispatch with `full_matrix` enabled:

| Workflow | Current work |
| --- | --- |
| [Ubuntu](.github/workflows/ci_ubuntu.yaml) | GUI/headless; tests, C++ CodeQL, AppImages; six combinations in the wider matrix |
| [macOS](.github/workflows/ci_macos.yaml) | GUI/headless; tests and DMG packaging; six combinations in the wider matrix |
| [Windows](.github/workflows/ci_windows.yaml) | x64 tests, packaged files, NSIS installer; three combinations in the wider matrix |
| [WebUI](.github/workflows/ci_webui.yaml) | Tests, lint, formatting, JavaScript CodeQL |
| [Python](.github/workflows/ci_python.yaml) | Type checking, lint, formatting, compilation |
| [File health](.github/workflows/ci_file_health.yaml) | Pre-commit checks, generated documentation checks, workflow analysis |
| [Engine client](.github/workflows/ci_engine_client.yaml) | Independent Qt-free build, HTTP contracts, sanitizers, C++ CodeQL |
| [GTK preview](.github/workflows/ci_gtk.yaml) | Native widgets under Xvfb in Ubuntu 26.04, Qt-free dependency check, C++ CodeQL |

There is also a scheduled stale-PR bot and Dependabot configuration. Reassess the
stale bot separately from the build pipeline when adapting fork administration.

The [continuous-release workflow](.github/workflows/release.yaml) builds a pinned
Ubuntu package, tests its installed binaries in a separate runtime container,
and publishes only after all required jobs succeed. Its manual trigger can
validate other branches without publishing. Only the publishing job grants
contents write permission, and main-branch runs are not cancelled by new pushes.
Native build/test, WebUI, file-health, client/worker, and package smoke jobs passed
in the first main run. Its publication required the checksum recovery described
above; the corrected full pipeline still needs an automatic successful run.

Keep Python, WebUI, file-health, and security checks while those components remain.
Replace Qt-specific build and packaging steps as their corresponding migration
stages land. Native Windows/macOS builds/tests validated the selected routine
version. Native installer execution and native GTK distribution remain pending.

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
