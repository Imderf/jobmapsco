# Mapa del Empleo Colombia

Proyecto de laboratorio de Imderf Ríos (no es de Ogilvy). Fuente de verdad del plan: nota del vault `laboratorio/plataformas/mapa-empleo-colombia.md` (Vault person). Metodología de 11 pasos obligatoria (`~/.claude/CLAUDE.md`).

## Qué es
Mapa 3D animado de Colombia: una columna de luz por ciudad (altura = ofertas de trabajo publicadas, escala raíz), flecha ▲▼ contra 7 días atrás, ranking, buscador y ficha por ciudad con sus ofertas y enlace a la fuente para postularse. Referencia visual: `~/Downloads/Mapa 3D.mp4` (mapa de hinchas de Nacional).

## Estructura
- `index.html` — toda la web, sin build. MapLibre GL 5.24.0 (globo → plano, relieve SRTM de AWS Terrain Tiles, agua/ríos/fronteras de OpenStreetMap vía OpenFreeMap, sin llaves) + deck.gl 9.4.0 `MapboxOverlay` no intercalado (columnas y cifras). Estático: solo lee `data/*.json`.
- Look: showreel "Manaure Escucha" (`~/Downloads/manaure-escucha_showreel_16x9_v04_liviano.mp4`): espacio con estrellas, azul eléctrico `#2f6bff`, Inter Tight 800 para títulos, JetBrains Mono para HUD y cifras.
- `scripts/preparar_datos.py` — genera `data/municipios.json`, `data/departamentos.geo.json` y `data/ofertas.json` desde `data/raw/`. Correr con `python3 -I scripts/preparar_datos.py`.
- `data/raw/divipola.json` — MinSalud Divipola (datos.gov.co `pqwj-3fi4`), 1.122 municipios con lat/lon. Los códigos vienen sin cero inicial; el script los rellena a 5 dígitos.
- `data/raw/departamentos.geo.json` — 33 departamentos (gist john-guerra, base DANE).

## Local
Config `mapa-empleo` en `.claude/launch.json` del vault: `python3 -m http.server 4330` en esta carpeta.

## Fuentes de ofertas (decisión 2026-10-13)
- **Jooble API**: devuelve `totalCount` por consulta (probado). La llave actual (en `.env`, `JOOBLE_KEY`) es de la base de EE. UU.: Colombia devuelve 0 y `co.jooble.org/api` responde 403. Hay que pedir a Jooble acceso a Colombia. Cupo por defecto: 500 consultas (van 4).
- **JSearch en RapidAPI** (OpenWeb Ninja, endpoint `GET /search-v2`, `country=co`; llave en `.env` como `RAPIDAPI_KEY`; probado 2026-10-13: 10 ofertas por página con `job_apply_link` a Computrabajo, LinkedIn, elempleo, Magneto, Indeed, BeBee; sin total por ciudad; `job_city` suele venir vacío): enlaces directos a la fuente. **Empezar con el plan gratis** (200 consultas/mes, ~6/día: rotar pocas ciudades al día); el plan de pago entra cuando todo esté al 100 %.
- No leer Computrabajo ni LinkedIn directamente (términos de uso). `data/ofertas.json` hoy es una línea base manual de Computrabajo del 2026-10-13, solo para diseño.

## Reglas
- Las llaves de API van solo como secretos de GitHub Actions. El navegador nunca llama a las APIs.
- Texto externo (ofertas) siempre con `textContent`, nunca `innerHTML`. Enlaces externos con `rel="noopener noreferrer"`.
- Entrada (referencias: globos de GitHub/Stripe y COBE): globo oscuro de puntos (`data/puntos.json`: tierra cada 1,2°, Colombia con la misma rejilla en azul), pulsos tipo radar en las ciudades, título letra por letra, contador de ofertas, marco HUD con línea de escaneo. Los puntos se vuelven mapa real entre `ZA` y `ZB` (relativos al zoom del globo `Z0`, para cualquier pantalla). Giro y pulsos arrancan después de cargar: con animación corriendo el mapa nunca llega a `idle`.
- La vista de Colombia es plana (mercator) con deck.gl. Probado y descartado (2026-10-13): dejarla sobre la curva del globo con barras `fill-extrusion` y terreno; el mapa se quedó sin dibujar. Imderf pidió volver a la vista plana.
- Clic en un departamento (capa invisible `deptos-zona`, si no se tocó una barra) o en el ranking de departamentos: zoom a su área y ficha con sus ciudades.
- Intro: globo puro (`vertical-perspective`) todo el vuelo; la mezcla globo/plano deformaba los bordes. Al aterrizar pasa a `mercator` y recién ahí se agrega el overlay de deck.gl (con otra proyección lanza `Unsupported projection`).
- Fuera de Colombia (atenuado al 68 %, no oculto; vecinos visibles sin relieve): capa `fuera` (`data/mascara.geo.json`, mundo con Colombia recortada, la genera el script) que se oscurece desde que arranca el vuelo. La sombra del relieve tiene `bounds` de Colombia; el terreno 3D se activa al aterrizar (con `bounds` en el terreno quedan huecos negros en el globo).
- Después de aterrizar: zoom mínimo = ver Colombia completa y `maxBounds` sobre Colombia.
- Barras: halo que pulsa, puntos de luz que suben por la barra (bajan en rojo y más rápido cuando el dato cae), anillo tipo radar en la base, nombre de cada ciudad en mono. Etiquetas y nombres se descartan si chocan en pantalla (proyección con `WebMercatorViewport`).
- Barras "en vivo": cada ciudad tiene `obj` (dato) y `vis` (dibujado) que lo persigue; un cambio destella verde ▲ o rojo ▼ 5 s. La página relee `data/ofertas.json` cada minuto. `?demo` simula cambios y lo marca "Simulación" en el HUD. La leyenda de alza/baja solo aparece en `?demo` hasta que haya una fuente de totales que cambie (Jooble Colombia): ahí se muestra siempre.
- Créditos de mapa obligatorios en el pie del HUD (OSM, OpenFreeMap, AWS Terrain Tiles).

## Ciclos
1. ✅ Mapa 3D con línea base fija, ranking, buscador, ficha, móvil (2026-10-13)
2. ✅ Look Manaure Escucha, intro precargada globo → Colombia, relieve real, barras vivas, órbita de cámara, resto del mundo apagado, zoom limitado a Colombia (2026-10-13)
3. 🔶 Recolector (2026-10-13): `scripts/recolectar.py` (stdlib; `--prueba` sin gastar consultas, `--industrias` reclasifica lo guardado) trae 6 ciudades por corrida desde JSearch por turnos (`data/recoleccion.json`: turno + registro de corridas con consultas restantes), guarda `data/ofertas/<divipola>.json` y `data/industrias.json`. Ficha de ciudad con ofertas y botón "Postularme" (solo enlaces http/https, `noopener noreferrer`); pestaña "Industrias" en el ranking (muestra, clasificada por el cargo). Workflow diario en `.github/workflows/recolectar.yml` (falta repo en GitHub y el secreto `RAPIDAPI_KEY`). En esta Mac el Python de python.org no trae certificados: correr con `SSL_CERT_FILE=/etc/ssl/cert.pem`. Cada corrida: 3 búsquedas por industria en todo el país (`BUSQUEDAS`, por turnos; cada oferta va a su ciudad por `job_location` "Ciudad • a través de …"; ubicación "Colombia" se descarta porque existe el municipio Colombia, Huila) + 3 búsquedas por ciudad. Cada ciudad guarda sus 30 ofertas más recientes de los últimos 30 días. Filtro por industria en el ranking: encoge las barras de las ciudades sin ofertas de esa industria y filtra la lista de la ficha. Los totales por ciudad siguen siendo la línea base hasta que Jooble habilite Colombia.
4. Flechas con historial (`data/historial/AAAA-MM-DD.json`)
