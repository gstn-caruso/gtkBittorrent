# Profile import

`gtkbittorrent-import` copies a closed qBittorrent profile into a new gtkBittorrent
profile. It uses C++20 and the standard library, with no Qt dependency. It imports
settings, torrent metadata, resume data, and any downloads inside a custom
profile. Cache files are excluded. Download payloads outside the profile stay
where they are; their stored paths are preserved.

Close qBittorrent and keep it closed throughout the copy. The importer refuses a
source with a `config/lockfile` and never opens the source through the torrent
engine. It refuses existing targets, overlapping source/target directories,
symlinks, special files, and ambiguous `.conf`/`.ini` settings. Failed copies are
discarded before a target profile is published. On POSIX, the new profile has
owner-only directory permissions. Copied settings are writable by their new
owner, including when the source is read-only.

For a custom profile whose directory contains `config` and `data`:

```sh
gtkbittorrent-import /path/to/old-root/qBittorrent /path/to/new-root/gtkBittorrent
gtkbittorrent-engine --profile=/path/to/new-root
```

For default profiles with separate configuration and data directories, pass both
directories explicitly. For example, for the usual Linux locations:

```sh
gtkbittorrent-import --config "$HOME/.config/qBittorrent" \
    --data "$HOME/.local/share/qBittorrent" /path/to/new-root/gtkBittorrent
gtkbittorrent-engine --profile=/path/to/new-root
```

Use the actual data directory if the old application uses a legacy or customized
location. The importer does not guess locations or automatically read another
application's profile. `--profile` points to the **parent** of `gtkBittorrent`,
whereas the import target is the `gtkBittorrent` directory itself. The desktop
application accepts the same `--profile` option.

Settings filenames become `gtkBittorrent.conf` on Linux or `gtkBittorrent.ini` on
Windows and macOS. A pending `qBittorrent_new` recovery file is copied and renamed
as well; the engine retains its existing recovery behavior. Resume bytes and
SQLite schemas are copied unchanged. Absolute download paths keep referring to
the original payloads, so only run one torrent engine against those payloads at
a time.

If the original profile used `--relative-fastresume`, pass that flag to the new
engine too and preserve the same directory layout relative to the profile.
Internal `downloads` are copied with a custom profile. External relative paths
need their payload directories at the equivalent location in the new layout;
importing settings does not move external downloads.

Build and test this tool independently of the inherited Qt application:

```sh
cmake -S src/profile -B build/profile-tools -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build/profile-tools
ctest --test-dir build/profile-tools --output-on-failure
```

The main build includes the same tool. The standalone tests cover copying,
source preservation, Unicode, separate default-profile directories, recovery
filenames, existing destinations, locked sources, symlinks, ambiguous settings,
read-only input, and rollback. The headless session suite additionally starts
the real engine with imported legacy and SQLite fixtures and verifies the
restored torrents and unchanged source files.
Use `-DBUILD_TESTING=OFF` for a standalone build without the Python test dependency.
