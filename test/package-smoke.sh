#!/bin/sh
set -eu
cd /artifacts
sha256sum -c SHA256SUMS
test ! -e /usr/bin/ruby
test ! -e /usr/bin/gcc
test ! -e /usr/lib/x86_64-linux-gnu/libgtk-4.so.1
test ! -e /usr/lib/x86_64-linux-gnu/libadwaita-1.so.0
for name in 'alice' 'second user'; do
  export HOME="/tmp/$name"
  export XDG_DATA_HOME="$HOME/.local/share"
  export XDG_CONFIG_HOME="$HOME/.config"
  export XDG_STATE_HOME="$HOME/.local/state"
  mkdir -p "$HOME/unpack"
  tar -xf /artifacts/*ubuntu-26.04-x86_64.tar.gz -C "$HOME/unpack"
  sh "$HOME/unpack/gtkbittorrent/install.sh"
  version=$("$HOME/.local/bin/gtkbittorrent" --version)
  engine_version=$("$XDG_DATA_HOME/gtkbittorrent/app/bin/gtkbittorrent-engine" --version)
  test "$version" = "$engine_version"
  desktop-file-validate "$XDG_DATA_HOME/applications/org.gtkbittorrent.GtkBitTorrent.desktop"
  dbus-run-session -- xvfb-run -a env GDK_BACKEND=x11 GTK_A11Y=none "$HOME/.local/bin/gtkbittorrent" --smoke-test
done
