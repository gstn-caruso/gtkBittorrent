#!/bin/sh
set -eu
launcher=$(readlink -f -- "$0")
root=$(CDPATH= cd -- "$(dirname -- "$launcher")" && pwd)
export LD_LIBRARY_PATH="$root/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export GI_TYPELIB_PATH="$root/runtime/lib/girepository-1.0"
export GEM_HOME="$root/runtime/gems"
export GEM_PATH="$GEM_HOME:$root/runtime/lib/ruby/gems/4.0.0"
export XDG_DATA_DIRS="$root/runtime/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export GSETTINGS_SCHEMA_DIR="$root/runtime/share/glib-2.0/schemas"
export GTKB_ENGINE="$root/app/bin/gtkbittorrent-engine"
cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/gtkbittorrent"
mkdir -p "$cache_dir"
cache_key=$(printf '%s' "$root" | cksum | cut -d ' ' -f 1)
export GDK_PIXBUF_MODULE_FILE="$cache_dir/loaders-$cache_key.cache"
"$root/runtime/bin/gdk-pixbuf-query-loaders" "$root"/runtime/lib/gdk-pixbuf-loaders/*.so > "$GDK_PIXBUF_MODULE_FILE.tmp.$$"
mv "$GDK_PIXBUF_MODULE_FILE.tmp.$$" "$GDK_PIXBUF_MODULE_FILE"
unset RUBYLIB RUBYOPT BUNDLE_GEMFILE BUNDLE_PATH
exec "$root/runtime/bin/ruby" "$root/app/bin/gtkbittorrent" "$@"
