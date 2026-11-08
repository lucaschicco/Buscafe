# Reporte de performance — Buscafes

Fecha: 2026-11-07 · Commit analizado: `0cce9c6`

## Resumen

El arranque en un celular está limitado por **cuatro problemas puntuales**. Ninguno es la
plataforma (Dash/Leaflet), y los cuatro se arreglan con cambios chicos:

1. **El callback Python `hide_spinner_on_load` sube el geojson entero al servidor**
   (≈3,5 MB por request) solo para ocultar el spinner. Corre en la carga inicial **y cada vez
   que se mueve o se hace zoom en el mapa**. Mientras ese POST no responde, el overlay blanco
   *"Estamos preparando el café"* (z-index 3000, opaco) tapa el mapa, aunque los marcadores ya
   estén dibujados debajo.
2. **Un debounce de 700 ms** en el callback de filtros también corre en la carga inicial.
3. **El geojson recién empieza a bajar cuando Dash termina de arrancar** (fetch dentro de un
   clientside callback), en serie después de ~450 KB de JS.
4. **El HTML pesa 729 KB (115 KB gzip)**: el 84 % es `buscafesLookup`, un JSON inline con los
   3.000 cafés que repite datos que ya están en `/api/geojson`. Además, el HTML no se cachea.
   A eso se suman fuentes Montserrat completas (2 × 125 KB) precargadas con prioridad alta.

### Antes / después (medido)

Celular emulado: viewport 412×823, red *Slow 4G* (150 ms RTT, 1,6 Mbps de bajada y 750 kbps de
subida), CPU 4× más lenta. Mediana de 3 corridas. "Frío" es la primera visita y "repetida",
la segunda con caché.

| Métrica | Hoy | Etapa A | Etapa B |
|---|---:|---:|---:|
| **Overlay de carga desaparece** (frío) | **45,5 s** | 5,2 s | 4,9 s |
| Primer marcador en el mapa (frío) | 7,9 s | 5,2 s | **4,9 s** |
| Primer marcador (visita repetida) | 3,1 s | 2,4 s | **2,1 s** |
| Total Blocking Time (frío) | 2.170 ms | 560 ms | 570 ms |
| Tarea larga máxima | 1.000 ms | 215 ms | 240 ms |
| HTML (gzip) | 115 KB | 115 KB | **29 KB** |
| HTML terminado de bajar | 1,77 s | 1,67 s | 0,30 s |
| Bytes propios, frío / repetida | 1.170 / 150 KB | 943 / 151 KB | 855 / 63 KB |
| **5 arrastres del mapa: datos subidos** | **17,4 MB** | — | **0 MB** |
| 5 arrastres: tiempo bloqueado | 3,7 s (máx. 640 ms) | — | 0,67 s (máx. 124 ms) |

* **Etapa A**: spinner como clientside callback, sin debounce en la carga inicial, `preload`
  del geojson y fuentes subseteadas a Latin.
* **Etapa B**: lo de la Etapa A, más `buscafesLookup` armado en el cliente desde el geojson en
  vez de venir inline en el HTML.
* **Estado:** la Etapa B y las fuentes subseteadas ya están aplicadas en `app.py` y `assets/` (puntos 1 a 5). Después de aplicarlas se repitió la medición: overlay a 5,1 s, el lookup del cliente idéntico al que generaba el servidor, filtros y deep link funcionando, 0 POST grandes. Los puntos 6 a 10 siguen pendientes.
  Las fuentes subseteadas se generan con el comando de la sección 5.

En desktop sin throttling, el primer marcador aparece a 1,57 s aunque la página termina de
cargar a 0,3 s. Unos 700 ms de esa diferencia son el debounce.

> La subida de 750 kbps del perfil Slow 4G es pesimista. Con un 4G decente (5 Mbps de subida),
> el POST de 3,5 MB igual tarda unos 6 s por request, así que el problema sigue siendo
> perceptible en cualquier red móvil.

---

## Hallazgos en detalle (de mayor a menor impacto)

### 1. 🔴 El spinner sube el geojson al servidor (`app.py`, `hide_spinner_on_load`)

```python
@app.callback(Output('loading-div', 'style'),
              Input('geojson-layer', 'data'),          # ← FeatureCollection visible
              Input('clientside-store-data', 'data'),  # ← geojson COMPLETO
              prevent_initial_call=True)
```

Un callback de servidor recibe en el body el valor de todos sus `Input`. Esto se midió
interceptando los requests:

```
1600ms POST /_dash-update-component  3556KB  output=loading-div.style   ← carga inicial
4413ms POST /_dash-update-component  3556KB  output=loading-div.style   ← pan
5274ms POST /_dash-update-component  3556KB  output=loading-div.style   ← pan
...
```

Consecuencias:
- **UX**: el overlay opaco queda arriba del mapa hasta que termina la subida. En Slow 4G eso son
  45 s.
- **CPU del cliente**: el navegador hace `JSON.stringify` de 3,5 MB en el hilo principal en cada
  pan o zoom. Es la causa de la mayor parte del TBT (2,1 s → 0,56 s al sacarlo) y de los saltos
  al arrastrar el mapa.
- **Datos móviles del usuario**: ~3,5 MB subidos por cada movimiento del mapa.
- **Servidor**: hay 1 worker gunicorn y el GIL es compartido. Cada pan de cada usuario obliga a
  parsear unos 3,5 MB de JSON (≈50 ms de CPU), lo que degrada el servicio para todos cuando hay
  tráfico.
- **Application Insights** también instrumenta esos POST.

**Fix** (aplicado): pasarlo a `app.clientside_callback` con la misma lógica. No
tiene que ir al servidor.

### 2. 🟠 Debounce de 700 ms en la carga inicial

En el callback de filtros, `const delay = isMapMove ? 0 : 700;`: cuando llega el store
(primer render) el disparador no es un movimiento del mapa, así que espera 700 ms.
**Fix**: `delay = 0` también cuando el disparador es `clientside-store-data`.

### 3. 🟠 El geojson se pide tarde

El `fetch('/api/geojson')` vive en un clientside callback que se dispara recién cuando
dash-renderer cargó, pidió `/_dash-layout` y `/_dash-dependencies` y montó el árbol. Queda así
una cascada HTML → 18 scripts → layout → deps → geojson → render.
**Fix**: `<link rel="preload" as="fetch" href="/api/geojson" crossorigin="anonymous">` en el
`<head>`. El `fetch()` posterior reutiliza esa descarga.

### 4. 🟠 `buscafesLookup` inline en el HTML (614 KB)

`geo_lookup` (nombre, dirección, barrio, web y coordenadas de cada café) se mete con
`json.dumps` en `index_string`, `/perfil` y `/comunidad`. Todo eso ya viene en el geojson. Como
el HTML no se cachea, se baja y se parsea entero en cada visita.
**Fix (aplicado, solo para el mapa)**: arrancar con `window.buscafesLookup = {}` y llenarlo
en el mismo callback que hace el fetch del geojson. Casi todos los usos de `buscafesLookup`
en el index dependen de interacciones del usuario (favoritos, ficha, buscador), que pasan
después de la carga. La excepción es el deep link `/?cafe=<id>`, que lo lee apenas corre el
script: se resuelve dentro del `setInterval` que ya tenía, y se verificó que el popup
se sigue abriendo.
**Pendiente**: hacer lo mismo en `/perfil` y `/comunidad` (692 KB y 670 KB de HTML), que pueden
leer `/api/geojson` desde la caché del navegador. Hoy además ejecutan `json.dumps(geo_lookup)`
en cada request.

### 5. 🟠 Fuentes Montserrat completas (2 × ~125 KB, precargadas)

Las dos `.woff2` traen todos los glifos (cirílico, vietnamita, etc.) y se precargan con
prioridad alta, así que compiten por ancho de banda con los bundles de JS. En Slow 4G son unos
1,3 s de transferencia. Subseteadas a Latin-1 + puntuación pesan **11,7 KB cada una**:

```bash
pip install fonttools brotli
pyftsubset assets/Montserrat-Regular.ttf --flavor=woff2 --layout-features='kern,liga' \
  --unicodes="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2190-2193,U+2212,U+2215,U+25BC,U+FEFF,U+FFFD" \
  --output-file=assets/Montserrat-Regular.woff2
# ídem para Bold
```

(Incluye ← → ▼, que la app usa. No incluye emojis, que de todos modos los dibuja la fuente del sistema.)

### 6. 🟡 Tiles del mapa bajados dos veces en celulares (pantallas retina)

El layout arranca con `.../{y}.png` y el callback `update_map_style` (sin
`prevent_initial_call`) lo cambia enseguida a `.../{y}{r}.png`. En pantallas con
`devicePixelRatio > 1` eso reemplaza los tiles normales por `@2x` apenas se cargan. Medido con
DPR 3: **8 tiles normales + 8 `@2x`** para la misma vista. Suma además 1 round-trip al servidor
en el arranque.
**Fix**: usar la misma URL (`{r}`) en el layout y `prevent_initial_call=True` en
`update_map_style`, o convertirlo en clientside callback.

### 7. 🟡 `/api/geojson` se comprime en cada request

`Flask-Compress` comprime los 3,3 MB en cada request (brotli q4 ≈ 18 ms, gzip ≈ 31 ms de CPU)
y `orjson.dumps(geojson_data)` también se rehace cada vez. Con datos sintéticos de 3.000 cafés:

| Variante | raw | gzip | brotli |
|---|---:|---:|---:|
| Actual (servido con br q4: 262 KB) | 3.315 KB | 241 KB | 151 KB (q11) |
| Sin `iconUrl`, sin `false`/`null`/`""` | 2.115 KB | 174 KB | 113 KB (q11) |

**Fix**:
- (a) Precalcular una vez al arrancar los bytes con brotli q11 y gzip, servirlos según
  `Accept-Encoding` y agregar `ETag` para que la revalidación devuelva 304. Son unos 110 KB
  menos por visita nueva y 0 ms de CPU por request.
- (b) Mediano plazo: adelgazar el formato. `iconUrl` es una URL absoluta que se repite 3.000
  veces y se puede derivar del rating en el cliente. Los booleanos en `false` pueden omitirse.
  El JSON queda un 36 % más chico, así que también se parsea más rápido en el celular. Esto
  implica tocar `admin_publicar` y el JS que lee esas claves.

### 8. 🟡 Íconos de marcadores servidos desde otro origen

`iconUrl` apunta a `jsonbuscafe.blob.core.windows.net`. Es otro host, así que antes de pintar
los íconos hay que pagar DNS + TCP + TLS (~3 RTT ≈ 450 ms en 4G lenta), y no hay `preconnect`.
Los mismos SVG ya están en `assets/` (`markverde.svg`, etc.).
**Fix**: usar `/assets/mark*.svg` (mismo origen), o como mínimo agregar
`<link rel="preconnect" href="https://jsonbuscafe.blob.core.windows.net">`.

### 9. 🟡 Arranque del servidor (cold start en Azure)

Medido localmente sin red: importar `app.py` tarda **~0,8 s** de CPU. Lo que más pesa:
`pandas` 225 ms, `firebase_admin.firestore` 220 ms y `dash` 170 ms; armar el índice de nombres
lleva unos 80 ms. En producción a eso se suman dos llamadas de red **en serie y bloqueantes**,
que corren en el master de gunicorn por `--preload`:

- `cargar_data_buscador()`: hace un `stream()` de **todos** los cafés activos con sus `tags`
  desde Firestore. Son unas 3.000 lecturas facturadas por cada reinicio y probablemente varios
  segundos.
- `requests.get(url)` del geojson **sin `timeout`**. Si el blob tarda o se cuelga, el worker no
  arranca nunca. El `--timeout 120` de gunicorn no cubre el master durante `--preload`.

**Fixes**:
- Agregar `timeout=(5, 30)` al `requests.get` del geojson.
- Correr las dos cargas en paralelo, por ejemplo con `ThreadPoolExecutor`.
- Mover `import pandas` adentro de las funciones de `/admin/publicar`, que es el único lugar
  donde se usa. Ahorra unos 225 ms de boot y algo de RAM.
- Mediano plazo: publicar también un snapshot de `CAFES_BUSCADOR` en el blob (desde
  `admin_publicar`), así el boot no barre Firestore.
- Si el plan lo permite, activar **Always On** en el App Service para evitar cold starts.
- Fijar versiones en `requirements.txt`. Hoy no hay ninguna, y un deploy puede traer un *major*
  nuevo de Dash sin aviso: este análisis se corrió con Dash 4.5.0.

### 10. 🟢 Menores

- Los assets propios (`/assets/*.css`, fuentes, íconos) se sirven con `Cache-Control: no-cache`,
  así que cada visita revalida unos 12 archivos con un RTT cada uno. Los que llevan `?m=` de Dash
  pueden tener un `max-age` largo.
- `bWLwgP.css` (34 KB) se sirve **sin comprimir**: Flask-Compress no comprime las respuestas
  `send_file` de los assets.
- La CSS referencia `/assets/buscafes_header2.jpeg`, que no existe (404). Hoy no se pide porque
  otra regla lo pisa, pero conviene limpiarlo.
- `assets/cafeterias.gif` (4,9 MB) no se usa en ningún lado y engorda el zip de deploy.
- Se cargan bundles que no se usan: `dash_table` (9 KB gz), `async-datepicker.js` y
  `dash_extensions` (que entra solo por usar `assign`).
- El *floor* de JS de Dash es de ~450 KB gzip (dash_leaflet 96, dcc 83, renderer 68,
  react-dom 43, polyfill 34). Bajarlo implica sacar Dash de la página del mapa, así que solo
  vale la pena si después de los fixes anteriores sigue siendo el cuello de botella.

---

## Prioridad sugerida

| # | Cambio | Impacto | Esfuerzo | Riesgo |
|---|---|---|---|---|
| 1 | Spinner → clientside callback | Muy alto (UX, datos, CPU de cliente y servidor) | 10 min | Bajo |
| 2 | Debounce 0 en la carga inicial | −0,7 s en todas las cargas | 2 min | Bajo |
| 3 | `preload` de `/api/geojson` | −0,3 a −1 s en mobile | 2 min | Bajo |
| 4 | Fuentes subseteadas | −230 KB en la primera visita | 10 min | Bajo |
| 5 | `buscafesLookup` armado en el cliente | −85 KB gz por visita, −1,4 s de HTML en 4G lenta | 30 min | Medio (probar favoritos, ficha y buscador) |
| 6 | Tiles: misma URL + `prevent_initial_call` | Evita tiles duplicados en celulares | 5 min | Bajo |
| 7 | Geojson precomprimido + ETag | −110 KB, 0 CPU por request | 30 min | Bajo |
| 8 | Íconos same-origin | −1 handshake TLS antes de pintar | 15 min | Bajo |
| 9 | Boot: timeout, paralelo, pandas lazy, Always On | Cold start más corto y sin cuelgues | 30 min | Bajo |

---

## Metodología y limitaciones

- **Entorno**: no hay acceso de red al blob de Azure, a Firestore ni al sitio en producción, así
  que se usó un geojson **sintético de 3.000 cafés** con el mismo esquema que genera
  `_pub_df_a_geojson`, y un Firestore en memoria con tags sintéticos (`perf/bench/fake_env.py`).
  Los tamaños y tiempos con datos reales van a diferir algo, pero las proporciones y los
  problemas estructurales son los mismos.
- La app se levantó con gunicorn y las mismas opciones que `startup.txt`. Navegador: Chromium
  (Playwright), con throttling por CDP. Los hosts externos (tiles, Firebase SDK, App
  Insights, íconos del blob) quedaron bloqueados por DNS para que la medición sea estable. Su
  costo real se suma encima, aunque casi todo es posterior al primer render.
- No se midió el cold start real de Azure App Service ni la latencia real de Firestore.

### Cómo repetir las mediciones

```bash
python -m venv venv && venv/bin/pip install -r requirements.txt
# servidor con datos sintéticos (puerto 8050)
venv/bin/gunicorn --chdir perf/bench wsgi_bench:server --bind=127.0.0.1:8050 --workers 1 --threads 8 --preload &
venv/bin/python perf/bench/startup_profile.py           # tiempo de boot (PROF=1 para cProfile)
node perf/bench/browser_bench.js mobile 3               # métricas de carga (frío y visita repetida)
node perf/bench/spinner.js                              # cuándo se va el overlay
node perf/bench/posts.js                                # tamaño de los POST de callbacks
node perf/bench/pan.js http://127.0.0.1:8050/           # costo de arrastrar el mapa
node perf/bench/tiles.js                                # tiles duplicados en retina
node perf/bench/cpu_profile.js                          # perfil de CPU de la carga
```

Requiere Playwright con Chromium. Si no está en el proyecto, usar `NODE_PATH=$(npm root -g)`.
