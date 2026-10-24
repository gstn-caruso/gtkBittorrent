# Protocolo del motor, versión 1

El proceso `gtkbittorrent-engine --state-dir /ruta/absoluta` lee stdin y escribe
stdout. Cada línea es un objeto JSON UTF-8, con un máximo de 1 MiB por solicitud.
stderr se reserva para diagnósticos. `--version` imprime únicamente la versión.
`--listen 127.0.0.1:0 --discovery false` aísla las pruebas de descubrimiento.

```json
{"v":1,"id":42,"method":"pause","params":{"torrent":"1"}}
{"v":1,"id":42,"result":true}
{"v":1,"id":43,"error":{"code":"not_found","message":"Transferencia inexistente"}}
{"v":1,"event":"metadata","data":{"torrent":"1"}}
```

Los IDs de solicitud permiten correlacionar resultados entre eventos. Los IDs
de transferencia son cadenas locales al catálogo; los hashes v1 y v2 permiten
detectar duplicados, incluso entre magnets y torrents híbridos.

| Método | Parámetros | Resultado |
| --- | --- | --- |
| `hello` | ninguno | versión de app, protocolo, libtorrent, recuperación de copia anterior |
| `inspect` | `source`: ruta .torrent o magnet | transferencia preparada; permite solo metadatos |
| `confirm` | `torrent`, `destination`, `category?`, `priorities?` | confirma destino y activa descarga |
| `list` | ninguno | catálogo y métricas (incluye preparados) |
| `details` | `torrent` | métricas, archivos, trackers, peers, magnet |
| `pause`, `resume`, `recheck` | `torrent` | acción sobre la transferencia |
| `move` | `torrent`, `destination` | mueve el almacenamiento y espera destino efectivo |
| `priorities` | `torrent`, `priorities`: array de 0 a 7 | aplica una prioridad por archivo |
| `category` | `torrent`, `category` | actualiza categoría |
| `queue` | `torrent`, `position` desde 0 | cambia posición de cola |
| `limits` | `torrent?`, `download`, `upload`, `active_downloads?`, `active_seeds?` | límites B/s; sin torrent, globales |
| `settings` | ninguno | límites globales persistidos |
| `trackers` | `torrent`, `trackers`: array http/https/udp | reemplaza y anuncia |
| `connect_peer` | `torrent`, `address`, `port` | conexión directa (también útil para pruebas locales) |
| `remove` | `torrent`, `delete_files?`, `confirmed?` | elimina; borrar datos exige ambas opciones true |
| `create` | `source`, `output`, `format?`: v1/v2/hybrid, `trackers?`, `private?` | genera metainfo; devuelve ruta y magnet |
| `checkpoint`, `shutdown` | ninguno | guarda estado; shutdown termina después de responder |

`status` se emite cada segundo. `metadata`, `storage_moved` y `error` informan
eventos asíncronos. Los errores de libtorrent se reflejan además en el estado.
ETA -1 significa desconocida; las velocidades se expresan en bytes/s y el
progreso es una fracción entre 0 y 1. `paused` indica pausa pedida por el usuario;
`queued` distingue la espera por límites automáticos de la sesión.

Las mutaciones confirmadas generan un checkpoint antes de responder. Los
preparados no se persisten; cancelar equivale a `remove` conservando datos.
El checkpoint de esquema 1 guarda resume data bencode de libtorrent codificada
en hexadecimal y metadatos del catálogo en un solo reemplazo atómico.
EOF, SIGTERM y SIGINT intentan un checkpoint final; SIGKILL recupera el último
checkpoint. Un fallo de escritura o de resume data se devuelve explícitamente.
