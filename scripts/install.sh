#!/bin/sh
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}
target="$data_dir/gtkbittorrent"
bin_dir="$HOME/.local/bin"
test -x "$source_dir/launch" || { echo 'Extraiga el paquete binario de GitHub Releases para instalar sin compilar.' >&2; exit 1; }
mkdir -p "$data_dir" "$bin_dir" "$data_dir/applications" "$data_dir/icons/hicolor/scalable/apps" "${XDG_CONFIG_HOME:-$HOME/.config}"
staging=$(mktemp -d "$data_dir/.gtkbittorrent-install.XXXXXX")
trap 'rm -rf -- "$staging"' EXIT HUP INT TERM
cp -a "$source_dir/." "$staging/"
if test -e "$target"; then
  test ! -e "$target.previous" || { echo 'Respaldo de instalación existente: quite gtkbittorrent.previous antes de actualizar.' >&2; exit 1; }
  mv "$target" "$target.previous"
fi
mv "$staging" "$target"
# A symlink keeps spaces and shell characters in home directories literal.
ln -sfn "$target/launch" "$bin_dir/gtkbittorrent"
LD_LIBRARY_PATH="$target/runtime/lib" "$target/runtime/bin/ruby" - "$bin_dir/gtkbittorrent" "$data_dir/applications/org.gtkbittorrent.GtkBitTorrent.desktop" <<'RUBY'
command = ARGV[0].gsub(/[\\"`$%]/) { |char| char == '%' ? '%%' : "\\#{char}" }
File.write(ARGV[1], "[Desktop Entry]\nType=Application\nName=GtkBitTorrent\nComment=Descarga y comparte torrents\nExec=\"#{command}\" %U\nIcon=org.gtkbittorrent.GtkBitTorrent\nTerminal=false\nCategories=Network;FileTransfer;\nMimeType=application/x-bittorrent;x-scheme-handler/magnet;\nStartupNotify=true\nDBusActivatable=false\n")
RUBY
cp "$target/app/data/org.gtkbittorrent.GtkBitTorrent.svg" "$data_dir/icons/hicolor/scalable/apps/"
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$data_dir/applications"; fi
if command -v xdg-mime >/dev/null 2>&1; then
  xdg-mime default org.gtkbittorrent.GtkBitTorrent.desktop application/x-bittorrent
  xdg-mime default org.gtkbittorrent.GtkBitTorrent.desktop x-scheme-handler/magnet
fi
echo "Instalado en $target. Ejecute $bin_dir/gtkbittorrent"
