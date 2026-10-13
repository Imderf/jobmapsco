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
- **JSearch en RapidAPI**: enlaces directos a la fuente. **Empezar con el plan gratis** (200 consultas/mes, ~6/día: rotar pocas ciudades al día); el plan de pago entra cuando todo esté al 100 %.
- No leer Computrabajo ni LinkedIn directamente (términos de uso). `data/ofertas.json` hoy es una línea base manual de Computrabajo del 2026-10-13, solo para diseño.

## Reglas
- Las llaves de API van solo como secretos de GitHub Actions. El navegador nunca llama a las APIs.
- Texto externo (ofertas) siempre con `textContent`, nunca `innerHTML`. Enlaces externos con `rel="noopener noreferrer"`.
- Intro: globo puro (`vertical-perspective`) todo el vuelo; la mezcla globo/plano deformaba los bordes. Al aterrizar pasa a `mercator` y recién ahí se agrega el overlay de deck.gl (con otra proyección lanza `Unsupported projection`).
- Fuera de Colombia (atenuado al 68 %, no oculto; vecinos visibles sin relieve): capa `fuera` (`data/mascara.geo.json`, mundo con Colombia recortada, la genera el script) que se oscurece desde que arranca el vuelo. La sombra del relieve tiene `bounds` de Colombia; el terreno 3D se activa al aterrizar (con `bounds` en el terreno quedan huecos negros en el globo).
- Después de aterrizar: zoom mínimo = ver Colombia completa y `maxBounds` sobre Colombia.
- Barras: halo que pulsa, puntos de luz que suben por la barra (bajan en rojo y más rápido cuando el dato cae), anillo tipo radar en la base, nombre de cada ciudad en mono. Etiquetas y nombres se descartan si chocan en pantalla (proyección con `WebMercatorViewport`).
- Barras "en vivo": cada ciudad tiene `obj` (dato) y `vis` (dibujado) que lo persigue; un cambio destella verde ▲ o rojo ▼ 5 s. La página relee `data/ofertas.json` cada minuto. `?demo` simula cambios y lo marca "Simulación" en el HUD.
- Créditos de mapa obligatorios en el pie del HUD (OSM, OpenFreeMap, AWS Terrain Tiles).

## Ciclos
1. ✅ Mapa 3D con línea base fija, ranking, buscador, ficha, móvil (2026-10-13)
2. ✅ Look Manaure Escucha, intro precargada globo → Colombia, relieve real, barras vivas, órbita de cámara, resto del mundo apagado, zoom limitado a Colombia (2026-10-13)
3. Recolector GitHub Actions con Jooble + JSearch → `data/ofertas.json` + `data/ofertas/<divipola>.json`
4. Flechas con historial (`data/historial/AAAA-MM-DD.json`)
