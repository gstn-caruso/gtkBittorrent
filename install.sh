#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"
python3 scripts/build-runtime.py
. .deps/env
bundle config set --local path vendor/bundle
BUNDLE_FROZEN=true bundle install
version=1.0.0
if test -f VERSION; then version=$(cat VERSION); fi
python3 scripts/package.py "$version"
staging=$(mktemp -d)
trap 'rm -rf -- "$staging"' EXIT HUP INT TERM
tar -xf "dist/gtkbittorrent-$version-ubuntu-26.04-x86_64.tar.gz" -C "$staging"
sh "$staging/gtkbittorrent/install.sh"
