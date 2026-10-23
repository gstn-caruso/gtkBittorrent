# Native GTK preview

This frontend consumes standard C++ snapshots and events from the Qt-free engine
worker. The current engine process is still the transitional Qt backend. The
preview connects to an externally started engine; process/profile ownership and
the full interface feature set remain migration work.

## Design direction

Use a native desktop layout centered on the torrent table: a quiet header,
connection controls, compact actions, and aligned name/size/progress/state
columns. Keep text left aligned, byte counts right aligned, and actions close to
the selected torrent. Empty and failed connection states must explain the next
action. Avoid decorative panels and nonessential animation.

Follow GTK's font, focus, contrast, accent, and dark-theme settings. The light
reference palette is paper `#FFFFFF`, workspace `#F7F8FA`, sidebar `#EDF1F4`, ink
`#202A34`, secondary text `#596674`, and transfer blue `#2D6E96`; these are design
references rather than forced overrides of the user's theme. Use the system
sans family, with a small semibold window title and ordinary native control/table
text. The table, rather than a branded hero or cards, carries the visual weight.

```text
gtkBittorrent                                      Connect
Address / username / password / Connect
Add magnet   Start   Stop   Remove
Name                            Size    Progress    State
Torrent rows, using GTK's virtualized ColumnView
Connection and operation status
```

The preview verifies connection, live torrent rows, selected-torrent start/stop,
and magnet addition. The native magnet dialog accepts a destination on the
engine and an optional stopped state; cancel and invalid links send no request.
File/removal dialogs, filtering/sorting, automatic backend ownership, packaging,
and feature parity remain required follow-up work. The release target
is GTK 4.24.1; the initial local trial uses GTK 4.22.4 and gtkmm 4.20.0 available
on the development machine. Final GTK dependency pinning remains unverified.

## Build and run

Install gtkmm 4.20 or later, the engine-client dependencies, and CMake. Tests
also need `xvfb-run`, `dbus-run-session`, and Python 3.10 or later.

```sh
cmake -S src/gtk -B build/gtk-preview -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build/gtk-preview -j3
ctest --test-dir build/gtk-preview --output-on-failure
build/gtk-preview/gtkbittorrent-gtk
```

Enter the address and credentials of an existing headless engine, then choose
Connect. The preview keeps credentials in memory and does not write profiles or
launch/stop the engine. It retires replaced workers without joining on GTK's
main thread. Shutdown joins remaining workers after the application loop exits.

The table uses `ColumnView`, `ListStore`, and `SingleSelection`. Selected torrent
IDs are retained across snapshot updates. Native theme settings, keyboard focus,
and labelled connection fields remain available. The UI test drives actual GTK
buttons and verifies rendered Unicode text and selected-torrent API requests
on an isolated D-Bus/Xvfb session.

To include the real partial-download UI case, configure with
`-DENGINE_TEST_BINARY="$PWD/build/engine/gtkbittorrent-engine"` (adjust to the
headless binary built locally). The case verifies that closing GTK leaves the
external engine running and its half-complete payload intact. Authentication
failure tests check the visible error and disabled torrent controls.
Magnet tests exercise cancel, invalid input, Unicode destinations, and addition
to a real engine without public trackers or peer discovery.
