# GtkBitTorrent

Cliente BitTorrent para Linux, escrito en Ruby y GTK/libadwaita, con un motor
C++20 basado en libtorrent. Interfaz inicial en español. Primera release: 1.0.0.

## Instalar un paquete

En Ubuntu 26.04 x86_64, descarga de GitHub Releases el archivo
`gtkbittorrent-<versión>-ubuntu-26.04-x86_64.tar.gz` y `SHA256SUMS`.

```sh
sha256sum --ignore-missing -c SHA256SUMS
tar -xf gtkbittorrent-<versión>-ubuntu-26.04-x86_64.tar.gz
sh gtkbittorrent/install.sh
~/.local/bin/gtkbittorrent
```

El paquete contiene Ruby, las gems, GTK, libadwaita, sus bibliotecas y el motor.
No necesita compiladores, gems ni GTK instalados en destino. Usa la ABI de glibc
de Ubuntu 26.04, los controladores gráficos y los servicios del escritorio.
El instalador registra `.torrent` y `magnet:` y respeta `XDG_DATA_HOME`.
Conserva la instalación anterior como `gtkbittorrent.previous` al actualizar.
Cierra la aplicación con **Salir** antes de actualizarla.

La ventana puede cerrarse y las transferencias siguen activas. Abre otra vez el
lanzador para recuperar la misma instancia. **Salir**, o `gtkbittorrent --quit`,
guarda un checkpoint y termina la aplicación y su motor.

## Uso

- Abre un `.torrent` o pega un magnet. Espera los metadatos, elige destino,
  categoría y prioridades de los archivos, y confirma **Iniciar descarga**.
  Hasta confirmar, el motor solo recupera metadatos.
- Usa **+** para elegir entre abrir un torrent o añadir un magnet. Ctrl+O abre
  un archivo y Ctrl+L permite pegar un magnet.
- Busca por nombre con Ctrl+F, filtra por estado o categoría y ordena pulsando
  las cabeceras de las columnas. Ctrl y Shift permiten seleccionar varias
  transferencias.
- Al seleccionar aparecen las acciones en la cabecera: **Pausar** para torrents
  activos y **Reanudar** para los pausados. El menú de la selección incluye
  **Propiedades**, **Verificar**, **Cambiar ubicación** y **Eliminar**. Los archivos
  se conservan por defecto; el borrado requiere marcar una casilla y confirmar.
- **Mostrar detalles**, o F9, abre un panel lateral con el progreso, las
  velocidades, los pares y el destino de la selección. Los filtros laterales
  muestran los contadores por estado y categoría, y las velocidades globales.
  En ventanas estrechas, la navegación y los detalles se adaptan al espacio.
- **Propiedades** muestra archivos, trackers, peers y opciones por torrent:
  prioridades de 0 a 7, límites en B/s, categoría y posición de cola desde 0.
  La prioridad 0 omite el archivo. Los archivos de relleno v2 se omiten.
- **Preferencias** define límites globales y cantidad de transferencias activas.
  Un límite de velocidad 0 significa sin límite; una cantidad activa 0 detiene
  esa clase de transferencias mediante la cola de libtorrent.
- **Crear torrent** admite archivos y carpetas, v1 (predeterminado), v2 e híbrido,
  trackers y torrents privados. El archivo de salida debe ser nuevo. La creación
  calcula hashes en el proceso auxiliar; para orígenes grandes puede demorar.
- Si falla el motor, el mensaje aparece en la ventana. **Reiniciar motor** lo
  recupera desde el checkpoint persistido.

## Desarrollo

Dependencias fijadas: Ruby 4.0.7; gems `gtk4` y `adwaita` 4.3.9; GTK 4.24.1;
libadwaita 1.10.0; libtorrent 2.0.12. Los archivos `Gemfile.lock`,
`package-lock.json` y `scripts/runtime-sources.json` fijan dependencias, fuentes
y checksums. Node 24 se usa solamente en las herramientas de automatización.

```sh
sh scripts/install-build-deps.sh
python3 scripts/build-runtime.py
. .deps/env
bundle config set --local path vendor/bundle
bundle install
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build -j 4
bundle exec ruby bin/gtkbittorrent
```

Las dependencias GNOME y Ruby se compilan en `.deps/prefix`, con introspección;
no se instalan en `/usr`. `BUILD_JOBS` permite ajustar el paralelismo.
Las fuentes versionadas incluyen estas mismas instrucciones y el instalador
binario; para instalarlas, primero compila y genera el paquete:

```sh
python3 scripts/package.py 1.0.0
```

El empaquetador compila el motor con esa versión, la incorpora al código Ruby y
al manifiesto, recoge las bibliotecas ELF necesarias y genera los dos tarballs y
`SHA256SUMS`. El código fuente publicado contiene `VERSION`; el repositorio de
desarrollo toma la versión de tags y no recibe commits de versión automáticos.
Después de instalar las dependencias de compilación, `sh install.sh` realiza
la compilación privada, genera el paquete y lo instala desde las fuentes.

## Validación

```sh
. .deps/env
bundle exec rake test
npm ci --ignore-scripts
npm test
dbus-run-session -- xvfb-run -a env GDK_BACKEND=x11 bundle exec ruby test/ui_smoke.rb
sh scripts/test-wayland.sh
python3 scripts/package.py 1.0.0
sh scripts/test-package.sh
```

Las pruebas de integración usan sesiones locales aisladas y datos generados;
no descargan contenido de Internet. Verifican hashes, magnets, duplicados v1/v2,
prioridades, límites, trackers, cola, conservación y borrado de archivos y
recuperación de checkpoints. Las pruebas GTK verifican también ejecución en
segundo plano, segunda apertura y salida. El contenedor final no tiene Ruby,
GTK ni compiladores y prueba dos directorios personales, uno con espacios.

## Estado y arquitectura

`lib/gtkbittorrent/` contiene los casos de uso Ruby y los adaptadores de proceso,
persistencia e interfaz. `engine/main.cpp` controla exclusivamente libtorrent.
El intercambio es JSON por línea; [protocolo](docs/protocol.md).

- `$XDG_CONFIG_HOME/gtkbittorrent/preferences.json`: categorías y preferencias.
- `$XDG_STATE_HOME/gtkbittorrent/checkpoint.json`: catálogo y resume data.
- Cada archivo conserva una copia anterior. Las escrituras usan reemplazo
  atómico y `fsync`; el motor guarda después de las operaciones y cada 30 s.
- Los checkpoints contienen metadatos, prioridades, trackers y límites por
  torrent. Una caída puede perder hasta 30 s de progreso; libtorrent verifica
  los datos al reanudarse. Si ambos checkpoints están dañados se detiene con un
  diagnóstico, preservando los archivos para restaurarlos.
- `engine.log` conserva diagnósticos; puede contener rutas y nombres de torrents.
  Los directorios de estado son privados (0700) y los archivos, 0600.
- GApplication/D-Bus mantiene una instancia por sesión; un bloqueo de archivo
  protege además al motor contra el uso simultáneo del mismo estado.

## Publicación automática

Cada PR y push a `main` ejecuta compilación, tests y validación del paquete.
Solo el job de publicación tiene `contents: write`. No se publican paquetes npm.
Ambos jobs instalan las mismas dependencias nativas. La preparación de cada
release y sus reintentos vuelve a probar el paquete final en Ubuntu limpio antes
de subirlo a GitHub.
Usa [semantic-release](https://semantic-release.org/recipes/ci-configurations/github-actions/),
historial completo, tags `vX.Y.Z` y `GITHUB_TOKEN`.

Conventional Commits: cambios incompatibles → major; `feat` → minor;
cualquier otro commit nuevo → patch, incluso documentación y mantenimiento.
Las notas incluyen esos cambios. El primer lanzamiento es 1.0.0.
El historial anterior hasta `890da1136` se conserva en Git, pero se excluye del
análisis y las notas del MVP Ruby/GTK, incluidos los reintentos de publicación.
Los títulos de PR y los commits se validan en CI; configura squash merge para
usar el título del PR y exige el check `verify` en la protección de `main`.

La publicación se serializa con
[concurrencia de Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
`queue: max` y sin cancelar el job activo. Un commit que quedó detrás de `main`
se omite; una ejecución posterior reúne todos los cambios sin publicar.
Reejecutar el mismo commit no incrementa la versión. Si existe un tag con una
release incompleta, el flujo reconstruye el código de ese tag y repara sus
artefactos antes de analizar nuevos commits. La cola cubre hasta 100 jobs.
No se generan commits de `VERSION` o `CHANGELOG.md`.

El repositorio está en [gstn-caruso/gtkBittorrent](https://github.com/gstn-caruso/gtkBittorrent).
Los pushes a `main` ejecutan el flujo de entrega con Actions habilitado. No se
requiere un PAT ni un token npm. Las pruebas locales no publican tags ni releases.

RSS, buscador integrado, control remoto, Flatpak e inicio automático se reservan
para una etapa posterior.
