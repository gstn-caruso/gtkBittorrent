#!/bin/sh
set -eu
python3 scripts/package.py "$1"
sh scripts/test-package.sh
