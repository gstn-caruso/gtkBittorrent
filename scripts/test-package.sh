#!/bin/sh
set -eu
docker build -f test/package.Dockerfile -t gtkbittorrent-package-test .
docker run --rm gtkbittorrent-package-test
