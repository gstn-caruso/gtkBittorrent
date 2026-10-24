#!/bin/sh
set -eu
runtime_dir=$(mktemp -d)
chmod 700 "$runtime_dir"
export XDG_RUNTIME_DIR="$runtime_dir"
export WAYLAND_DISPLAY=gtkb-test
export GDK_BACKEND=wayland
export GIO_USE_VFS=local
weston --backend=headless --socket="$WAYLAND_DISPLAY" --idle-time=0 --width=1280 --height=800 > "$runtime_dir/weston.log" 2>&1 &
weston_pid=$!
trap 'kill "$weston_pid" 2>/dev/null || true; wait "$weston_pid" 2>/dev/null || true; rm -rf "$runtime_dir" || true' EXIT HUP INT TERM
count=0
while [ ! -S "$runtime_dir/$WAYLAND_DISPLAY" ]; do
  count=$((count + 1))
  if [ "$count" -gt 100 ]; then cat "$runtime_dir/weston.log"; exit 1; fi
  sleep 0.1
done
dbus-run-session -- bundle exec ruby test/ui_smoke.rb
