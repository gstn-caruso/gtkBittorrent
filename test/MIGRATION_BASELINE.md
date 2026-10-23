# Migration behavior baseline

The inherited application identifies as qBittorrent 5.4.0alpha1, base commit
`a87f8f9c282e7341b1f4f9e9a5a66c869d2366a6`. This is the compatibility target
for the GTK migration. A listed feature remains required until verified in the
replacement or explicitly removed from scope by agreement.

## Local build and validation

Validated on Ubuntu 26.04, GCC 15.2.0, CMake 4.2.3, Qt 6.10.2, Boost 1.90,
libtorrent 2.0.12, OpenSSL 3.5.5, and zlib 1.3.1. GTK 4.22.4 and gtkmm 4.20.0
are installed for subsequent trials; GTK 4.24.1 from the plan is not locally
validated yet. The build still requires Qt.

```sh
cmake -S . -B build/baseline -G Ninja -DCMAKE_BUILD_TYPE=Debug -DGUI=OFF -DTESTING=ON
cmake --build build/baseline -j4
ctest --test-dir build/baseline --output-on-failure -j4

cmake -S . -B build/qt-gui -G Ninja -DCMAKE_BUILD_TYPE=Debug -DTESTING=ON
cmake --build build/qt-gui -j4
ctest --test-dir build/qt-gui --output-on-failure -j4
QT_QPA_PLATFORM=offscreen build/qt-gui/gtkbittorrent --version
```

The 22 inherited test executables pass in both configurations. Testing is now
enabled at the build root; previously CTest reported zero tests there.
The headless build also registers `testsession`, a Python standard-library
integration suite. Both configurations register identity and profile import
checks, giving 25 CTest entries headless and 24 desktop on Linux. Existing CI's
`check` target discovers tests throughout the build tree and builds the backend
and importer first. No Python runtime dependency is added to production builds.

Both builds install into a disposable `DESTDIR`; each installed executable's
`--version` command succeeds. Session integration tests also pass against
the staged headless executable. This does not establish AppImage, Windows, or
macOS package compatibility, nor interactive desktop behavior.

## Automated session coverage

Run the focused checks without rebuilding unrelated components:

```sh
ctest --test-dir build/baseline -L session --output-on-failure
python3 -B test/testsession.py --binary build/baseline/gtkbittorrent-engine \
    --importer build/baseline/gtkbittorrent-import -v
```

The suite uses temporary profiles, loopback HTTP and peer listeners, random test
passwords, and synthetic data. DHT, LSD, PeX, port forwarding, and country database
downloads are disabled. HTTP requests bypass system proxies. No public tracker,
peer, RSS server, or user profile is required.

| Behavior | Evidence |
| --- | --- |
| Authenticated remote control | Anonymous requests rejected with HTTP 403; wrong password rejected with HTTP 401; valid login permits operations |
| Actual torrent transfer | Two independent processes transfer and verify all 32 KiB over a manually connected loopback peer |
| Interrupted download and Unicode paths | One verified piece of two survives a clean stop and restart with the same info hash, destination, and stopped state |
| Torrent settings | Category, Unicode tags, per-torrent limit, file priority, and global download limit survive restart |
| Lifecycle | SIGTERM exits successfully, saves resume state, and permits the same profile to restart |
| Old session loading | Frozen legacy and SQLite fixtures load under each storage mode; paths relocate to the temporary profile |
| Explicit import | Both frozen storage formats start in the engine after copying through the importer; source profile bytes remain unchanged |
| Fork isolation | Custom, default XDG, and named profiles use gtkBittorrent settings; the old qBittorrent profile stays unchanged and `QBT_` variables are ignored |
| Settings recovery | A populated `qBittorrent_new.conf` takes precedence over the older main file and is promoted during recovery |
| Unknown settings | An unrecognized key survives saving and recovering settings |
| Start and removal | A restored torrent starts; removal without deleting files retains its payload |

Login success in this inherited revision has an empty response body. Clients
must use HTTP status and the session cookie; assuming the older `Ok.` body fails.
Torrent restoration initially reports `checkingResumeData` before its saved
stopped state. Consumers must handle asynchronous state transitions.

The frozen data's provenance and regeneration command are documented in
[the fixture README](testdata/session/README.md). A generated round trip and
loading frozen inherited files are separate compatibility checks.

## Feature inventory and remaining gates

This inventory identifies implementation areas and the remaining verification
work. Rows marked pending are not claims of behavioral equivalence.

| Feature group | Inherited implementation | Remaining validation gate |
| --- | --- | --- |
| Torrents and magnets | `src/base/bittorrent`, `src/base/addtorrentmanager.*`, `src/gui/addnewtorrentdialog.*` | Magnet metadata exchange, duplicates, v2 and hybrid torrents, corrupt metadata |
| Files and destinations | `src/gui/torrentcontent*`, `src/base/bittorrent/torrentcontent*` | Multi-file trees, renames, moves, skipped files, deletion with payload |
| Trackers and peers | `src/gui/properties`, `src/base/bittorrent/tracker*`, `src/base/bittorrent/peer*` | Tracker announce/authentication, peer lists, IP filtering, bans |
| Categories and tags | `src/gui/torrentcategorydialog.*`, `src/gui/torrenttagsdialog.*`, session and torrent implementations | Automatic torrent management, nested category moves, filtering and sorting |
| Transfer and share limits | `src/base/bittorrent/bandwidthscheduler.*`, `src/gui/torrentsharelimitswidget.*` | Scheduler, queue order, ratio/time limits, alternative speed mode |
| RSS | `src/base/rss`, `src/gui/rss`, `src/webui/api/rsscontroller.*` | Feed import/export, local XML fixtures, rules and automatic downloading |
| Search | `src/base/search`, `src/searchengine`, `src/gui/search`, `src/webui/api/searchcontroller.*` | Python engine checks and a deterministic local plugin |
| Lua plugins | `src/base/plugins`, `src/gui/plugins` | Plugin discovery, lifecycle, callbacks, errors and permissions |
| Torrent creation | `src/base/bittorrent/torrentcreat*`, `src/gui/torrentcreatordialog.*`, `src/webui/api/torrentcreatorcontroller.*` | File hashing, v1/v2/hybrid output and cancellation |
| WebUI and API | `src/webui`, `src/webui/www` | JavaScript suite, CSRF/host-header rejection, incremental sync, all command coverage |
| Network policy | `src/base/net`, `src/base/bittorrent/sessionimpl.*` | HTTP/SOCKS proxies, remote versus local DNS, tracker TLS, authentication and failure behavior |
| Settings and lifecycle | `src/base/settingsstorage.*`, `src/base/profile*`, `src/app`, `src/profile` | Disk-full and engine settings permission failures, forced-kill recovery, single-instance ownership |
| Desktop integration | `src/gui`, `dist` | Keyboard and accessibility, translations, notifications, tray, power inhibition, associations and platform packaging |

Stage 1 remains in progress while these baseline gates are pending. In particular,
loopback transfer coverage does not prove proxy/DNS equivalence or complete
feature parity. Subsequent implementation should add focused characterization
tests before replacing each affected subsystem.

## Fork identity and import tools

The application ID is `io.github.gstn_caruso.gtkBittorrent`; Linux desktop files,
icons, metainfo, manual names, and the systemd unit now use the fork's names.
Executables are `gtkbittorrent`, `gtkbittorrent-engine`, and
`gtkbittorrent-import`. Linux metadata validates with `desktop-file-validate`
and `appstreamcli validate --no-net`. macOS bundle IDs and Windows installer
directories, registry keys, and uninstaller paths were adapted, but those
platforms still require native build and installation verification.

`src/profile` builds independently with C++20 and no Qt. Its command tests cover
custom and split-directory profiles, Unicode paths, existing targets, locked
sources, symlinks, overlapping directories, ambiguous settings, rollback, and
read-only source permissions. The linked standalone importer uses only the C/C++
runtime libraries on Linux. See [its guide](../src/profile/README.md) for usage.

Native GTK UI implementation, automatic prereleases, and moving the default
branch to `main` remain pending. The desktop and engine still depend on Qt.
