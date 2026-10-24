#!/bin/sh
set -eu
sudo apt-get update
sudo apt-get install -y build-essential cmake ninja-build meson pkg-config curl \
  gettext bison flex gobject-introspection libgirepository1.0-dev \
  libffi-dev libpcre2-dev libmount-dev libselinux1-dev libdbus-1-dev \
  libharfbuzz-dev libfribidi-dev libfontconfig1-dev libfreetype-dev \
  libcairo2-dev libgdk-pixbuf-2.0-dev libgraphene-1.0-dev libepoxy-dev \
  libpng-dev libtiff-dev libjpeg-dev libxkbcommon-dev libwayland-dev \
  libx11-dev libxext-dev libxi-dev libxrandr-dev libxcursor-dev \
  libxdamage-dev libxfixes-dev libxinerama-dev libdrm-dev \
  libssl-dev libyaml-dev zlib1g-dev libreadline-dev libgmp-dev \
  libtorrent-rasterbar-dev nlohmann-json3-dev patchelf \
  xvfb xauth dbus-x11 adwaita-icon-theme fonts-cantarell weston grim
