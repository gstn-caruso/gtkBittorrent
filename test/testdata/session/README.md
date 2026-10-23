# Inherited session fixtures

These fixtures were written by the inherited qBittorrent 5.4.0alpha1 engine
(base commit `a87f8f9c282e7341b1f4f9e9a5a66c869d2366a6`) with libtorrent
2.0.12 and Qt 6.10.2 on Linux, on 2026-10-22. No production profile was used.

Each directory contains a stopped, half-complete v1 torrent, its resume storage,
and the first verified 16 KiB piece of a 32 KiB synthetic file. The second piece
is missing. The torrent has no trackers or web seeds and is private. Its payload
is all byte values from 0 to 255 repeated 64 times, followed by `b` repeated
16,384 times.

- Info hash: `5fbbadb85506f6d355f1ae1675fdc211299b8fa1`.
- File: `archivo 日本語.bin`, saved in `descargas 日本語`.
- Category: `pruebas/日本語`; tags: `linux`, `日本語`.
- Download limit: 32,768 bytes/second; file priority: 6.
- Resume paths are relative to `qBittorrent`, using `--relative-fastresume`.
- `legacy` contains bencoded resume data and torrent metadata in `BT_backup`.
- `sqlite` contains the inherited SQLite schema, resume data, and metadata.

`testsession.py` copies these files into disposable profiles and loads each
fixture using both storage implementations. Keep these original files unchanged
when migrating persistence: a round trip through only the new implementation
does not prove that old sessions remain readable.

To reproduce fresh fixtures for investigation, use a separate output directory:

```sh
python3 -B test/testsession.py --binary build/baseline/qbittorrent-nox \
    --fixture-output build/session-fixtures-new TestSession.testRestartPreservesPartialDownload
```

The exporter excludes GeoIP databases and logs. Authentication uses a new random
password for every temporary profile; credentials are not exported. Resume
timestamps and SQLite bytes may vary between generations.
