# Validación local — 23 de octubre de 2026

Entorno: Ubuntu 26.04.1 x86_64, Ruby 4.0.7, GTK 4.24.1 y libadwaita 1.10.0
compilados en un prefijo privado; libtorrent 2.0.12; Node 24.18.1.

Resultados:

- `bundle exec rake test`: 15 pruebas, 74 aserciones; sin fallos ni omisiones.
- `npm test`: 13 pruebas; sin fallos. Incluye semantic-release real en dry-run
  contra un origen Git local: primera versión 1.0.0, misma revisión sin nueva
  versión, documentación → 1.0.1, commits agrupados con feature → 1.1.0,
  cambio incompatible → 2.0.0. La prueba incluye un merge entre historiales
  independientes y verifica la exclusión de los commits de la aplicación previa.
- UI en X11/Xvfb y Wayland/Weston headless: creación de torrent, formulario de
  confirmación y prioridades, tabla con una transferencia, páginas de detalles,
  preferencias, cierre en segundo plano, segunda instancia y checkpoint final.
- Paquete 1.0.0 instalado en un contenedor Ubuntu 26.04 sin Ruby, GTK,
  libadwaita ni compiladores. Se verificaron checksums, versión de aplicación y
  motor, entrada de escritorio y arranque gráfico en dos directorios personales,
  uno con espacios.
- `ubuntu-26.04.1-desktop-amd64.iso.torrent`: lectura de metadatos y apertura desde
  el lanzador. Una descarga separada en un directorio temporal obtuvo 1.114.112
  bytes y conectó con 43 peers; pausa correcta y sin error de transferencia.
  El archivo torrent original se conservó. No se descargó la ISO completa.
- Recuperación tras SIGKILL, checkpoint principal dañado, ambos checkpoints
  dañados, destino no escribible y fallo ENOSPC mediante `/dev/full`.

La revisión de Wayland usa un compositor headless; queda pendiente la revisión
interactiva en una sesión GNOME del usuario. El remoto es
`https://github.com/gstn-caruso/gtkBittorrent.git`. El workflow está preparado para
PRs, pushes a `main` y reintentos manuales con `workflow_dispatch`; los resultados
de una publicación remota deben comprobarse en Actions y GitHub Releases.
