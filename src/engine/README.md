# Qt-free engine client

This C++20 library is the beginning of the GTK application's engine boundary.
Its public types use the standard library. HTTP and JSON dependencies remain
private; widgets do not receive Qt objects or libtorrent handles. The backend
process is still the transitional Qt engine.

`Client` owns one HTTP session with cookies held only in memory. Calls are
blocking and must run sequentially on an engine worker, outside GTK's main
thread. The owner must finish calls before destroying the client. A request
timeout bounds transport operations. Constructing or destroying a client does
not start, stop, or take ownership of an engine process or profile.

The boundary authenticates through the existing Web API and returns
complete torrent snapshots with validated identifiers, Unicode strings, and
64-bit byte counts. Failures use `ErrorKind` and an optional HTTP status. It
accepts HTTP/HTTPS base URLs, including reverse-proxy path prefixes, and leaves
TLS certificate verification enabled. Redirects are rejected.

It also starts/stops selected torrents, adds torrent files and magnets with an
explicit destination/stopped state, and removes torrents with an explicit
delete-files choice. Torrent identifiers exclude wildcard and multi-torrent
strings. Uploads preserve binary bytes. Add acknowledgements support the current
JSON summary, including pending additions, and legacy empty/`Ok.` replies.
An acknowledgement does not mean that asynchronous engine state has settled;
the owner must keep refreshing snapshots.

Process startup/shutdown, profile ownership, preferences, and advanced feature
coverage remain pending. These are required before the GTK
client can replace the existing interface.

## Worker and events

`Worker` owns its authenticated `Client` on a dedicated C++ thread. Construction
and `submit()` do not wait for network requests. Commands own their strings,
identifiers, and uploaded bytes. `takeEvents()` transfers standard C++ values to
the caller; GTK must consume them on its main thread. No callback accesses a
widget from the worker.

The worker authenticates once, publishes `Connected` and `Snapshot` events, and
processes commands in FIFO order. `Accepted` means the HTTP operation was
acknowledged; subsequent snapshots show asynchronous state changes. `Failure`
includes a request ID (`0` for connection/poll failures), kind, HTTP status, and
safe message. Individual server rejections leave the connection usable.
Authentication, transport, or protocol failures stop processing and fail queued
commands without replaying them. Reconnection requires a new worker.

Only the newest pending snapshot is retained for slow consumers. A nonblocking
`requestStop()` cancels queued work and wakes the polling wait. An in-flight
request finishes or times out; the destructor joins the thread. GTK should keep
retired workers until `finished()` before destroying them, or join after its main
loop has stopped. Stopping this client never stops an externally owned engine
process.

Eight loopback worker tests cover the blocked-server boundary, request ordering,
authentication failures, cancellation, idle shutdown, snapshot coalescing, and
owned addition/removal payloads. Local address, undefined-behavior, and thread
sanitizer runs pass. The CI workflow includes the same worker checks.

## Build and test without Qt

Install libcurl development files (8.4 or later), nlohmann-json (3.11 or later),
CMake, and a C++20 compiler. Python 3.10 or later is needed only for tests.

```sh
cmake -S src/engine -B build/engine-client -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build/engine-client -j4
ctest --test-dir build/engine-client --output-on-failure
```

For real-engine integration checks, configure with an existing headless binary:

```sh
cmake -S src/engine -B build/engine-client \
  -DENGINE_TEST_BINARY="$PWD/build/baseline/gtkbittorrent-engine"
cmake --build build/engine-client -j4
ctest --test-dir build/engine-client --output-on-failure
```

Thirteen HTTP tests cover request encoding, authentication/expiry, errors,
malformed snapshots, redirects, reverse-proxy paths, timeouts, control requests,
and binary uploads. A separate real-engine test adds a partial Unicode download,
starts/stops it, restarts the backend, verifies resumed progress, adds a magnet,
and checks both file-preserving and file-deleting removal in a disposable profile.
The standalone CI job runs with address/undefined-behavior sanitizers; release
builds also exercise the client against the newly built real engine.

Tests launch a C++ probe against a disposable loopback HTTP server. Credentials
travel through its standard input and are not command-line arguments. Neither
the probe nor tests are installed as application tools. This is not yet a GTK
interface or a complete replacement for the backend.

The implementation follows libcurl's [threading](https://curl.se/libcurl/c/threadsafe.html)
and [in-memory cookie](https://curl.se/libcurl/c/CURLOPT_COOKIEFILE.html) contracts.
JSON integration uses the library's [CMake target](https://json.nlohmann.me/integration/cmake/).
