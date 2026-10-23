# Transitional Linux releases

The release tools build an Ubuntu 26.04 amd64 Debian package containing the
current Qt desktop, headless engine, and Qt-free profile importer. They do not
provide the final native GTK application. Windows/macOS release packages remain
pending.

## Build and verify locally

Use a clean checkout with all source changes committed. Docker builds use a
pinned Ubuntu image and exact top-level dependency versions from
`dependencies.lock`. Transitive dependencies are resolved by Ubuntu; the full
installed package/version inventory is recorded in `build-info.json`. This is
not a claim of a fully hermetic or byte-reproducible application build.

```sh
docker build -t gtkbittorrent-release:ubuntu26 dist/release
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD:/source" -w /source \
  gtkbittorrent-release:ubuntu26 \
  python3 -B -m dist.release.build --directory build/release-local \
    --commit "$(git rev-parse HEAD)" --jobs 2
```

The build directory must be new. Both GUI/headless builds enable tests; CTest
must pass before installation into a shared staging tree. Packaging rejects
dirty source trees, mismatched commits, and missing executables. Outputs are
under `build/release-local/artifacts`: the `.deb`, `build-info.json`, and
`SHA256SUMS`. The package also includes its source commit, build manifest, and
license under `/usr/share/doc/gtkbittorrent`.

Installation smoke tests must run in a separate clean runtime container and use
the installed binaries, including the session/import integration tests. A build
container alone does not prove that all runtime dependencies are packaged.

## Publication

`publish.py` accepts only a complete artifact directory whose checksums and
manifest match a full source SHA. It creates an immutable `build-<full-sha>` tag
and a draft prerelease, uploads missing assets, checks GitHub's asset digests,
and publishes only after every asset matches. Retries reuse matching drafts or
published releases. Conflicting tags/assets are rejected rather than replaced.

```sh
python3 -B -m dist.release.publish --artifacts build/release-local/artifacts \
  --repository gstn-caruso/gtkBittorrent --commit "$(git rev-parse HEAD)"
```

Publication requires an authenticated `gh` with repository contents permission.
The CI publishing job must depend on all required checks and package smoke
tests, and grant write permission only to publication. CI integration remains
pending; running the local build does not publish a release.

## Tool tests

```sh
python3 -B -m unittest discover -s test -p testrelease.py -v
python3 -B -m unittest discover -s test -p testpackage.py -v
```

Publication tests use a fake API and make no network writes. Packaging tests use
a temporary Git repository; on Ubuntu 26.04 they also build/extract a real Debian
package, verify its metadata/checksums, and compare repeated packaging of the
same staged files. Other platforms skip that package-format test.
