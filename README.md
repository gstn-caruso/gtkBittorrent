# gtkBittorrent

gtkBittorrent is a C++20 BitTorrent client being migrated from qBittorrent to
GTK and gtkmm while retaining libtorrent, saved sessions, and remote control.
The default desktop and headless engine currently still use Qt. The separate profile
import tool and new engine-client library already build and run without Qt.

The migration scope, stages, and release policy are in
[MIGRATION_PLAN.md](MIGRATION_PLAN.md). Verified behavior and remaining gates are
recorded in [the migration baseline](test/MIGRATION_BASELINE.md).

## Build and test

Install the dependencies listed in [INSTALL](INSTALL), then build the headless
engine and its tests:

```sh
cmake -S . -B build/engine -G Ninja -DCMAKE_BUILD_TYPE=Debug -DGUI=OFF -DTESTING=ON
cmake --build build/engine -j4
ctest --test-dir build/engine --output-on-failure -j4
```

The executable is `build/engine/gtkbittorrent-engine`. With `GUI=ON`, the inherited
Qt desktop application is built as `gtkbittorrent`. Both builds include
`gtkbittorrent-import`. A native GTK interface remains a migration milestone.

The [engine-client library](src/engine/README.md) builds independently with
libcurl and nlohmann-json. Its real-engine tests verify the control boundary that
the GTK interface will use.

An initial [native GTK preview](src/gtk/README.md) now connects to a running
engine, displays live torrent rows, and starts/stops selected torrents. It builds
as `gtkbittorrent-gtk` from `src/gtk` and is tested locally against a real engine.
It is not yet included in release packages; torrent addition, preferences, and
managed backend startup remain in progress.

## Profiles

gtkBittorrent uses its own `gtkBittorrent` profile directories and settings files.
It uses `GTKB_` environment variables for command line defaults, such as
`GTKB_PROFILE` and `GTKB_WEBUI_PORT`. Existing `QBT_` variables belong to
qBittorrent and are ignored.

To import an old session, explicitly copy a closed profile with
`gtkbittorrent-import`. Both custom profiles and separate default configuration
and data directories are supported. See the [profile import guide](src/profile/README.md)
for commands, portable paths, and an independent build without Qt.

## Upstream and license

This fork is based on [qBittorrent](https://github.com/qbittorrent/qBittorrent)
5.4.0alpha1. Existing authorship and license notices remain in the sources.
See [COPYING](COPYING) for the license and [AGENTS.md](AGENTS.md) for the
contribution policy.

The free IP to Country Lite database from [DB-IP](https://db-ip.com/) is used for
peer country resolution and is licensed under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
