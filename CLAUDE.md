# Mapa del Empleo Colombia

Proyecto de laboratorio de Imderf Ríos (no es de Ogilvy). Fuente de verdad del plan: nota del vault `laboratorio/plataformas/mapa-empleo-colombia.md` (Vault person). Metodología de 11 pasos obligatoria (`~/.claude/CLAUDE.md`).

## Qué es
Mapa 3D animado de Colombia: una columna de luz por ciudad (altura = ofertas de trabajo publicadas, escala raíz), flecha ▲▼ contra 7 días atrás, ranking, buscador y ficha por ciudad con sus ofertas y enlace a la fuente para postularse. Referencia visual: `~/Downloads/Mapa 3D.mp4` (mapa de hinchas de Nacional).

## Estructura
- `index.html` — toda la web (deck.gl 9.0.38 por CDN, sin build). Estático: solo lee `data/*.json`.
- `scripts/preparar_datos.py` — genera `data/municipios.json`, `data/departamentos.geo.json` y `data/ofertas.json` desde `data/raw/`. Correr con `python3 -I scripts/preparar_datos.py`.
- `data/raw/divipola.json` — MinSalud Divipola (datos.gov.co `pqwj-3fi4`), 1.122 municipios con lat/lon. Los códigos vienen sin cero inicial; el script los rellena a 5 dígitos.
- `data/raw/departamentos.geo.json` — 33 departamentos (gist john-guerra, base DANE).

## Local
Config `mapa-empleo` en `.claude/launch.json` del vault: `python3 -m http.server 4330` en esta carpeta.

## Fuentes de ofertas (decisión 2026-10-13)
- **Jooble API** (gratis, llave por formulario): conteo por ciudad y listado. Confirmar `totalCount` al tener la llave.
- **JSearch en RapidAPI**: enlaces directos a la fuente. **Empezar con el plan gratis** (200 consultas/mes, ~6/día: rotar pocas ciudades al día); el plan de pago entra cuando todo esté al 100 %.
- No leer Computrabajo ni LinkedIn directamente (términos de uso). `data/ofertas.json` hoy es una línea base manual de Computrabajo del 2026-10-13, solo para diseño.

## Reglas
- Las llaves de API van solo como secretos de GitHub Actions. El navegador nunca llama a las APIs.
- Texto externo (ofertas) siempre con `textContent`, nunca `innerHTML`. Enlaces externos con `rel="noopener noreferrer"`.
- La animación de entrada arranca en `onLoad` de deck: antes, el cambio de cámara se pierde.

## Ciclos
1. ✅ Mapa 3D con línea base fija, ranking, buscador, ficha, intro animada, móvil (2026-10-13)
2. Motion fino (transiciones de ficha, pulso de columnas, San Andrés en recuadro)
3. Recolector GitHub Actions con Jooble + JSearch → `data/ofertas.json` + `data/ofertas/<divipola>.json`
4. Flechas con historial (`data/historial/AAAA-MM-DD.json`)
