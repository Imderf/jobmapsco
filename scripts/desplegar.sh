#!/bin/sh
# Sube el sitio al servidor (alias ssh "jobmapsco"). No toca llaves, configuración
# ni los datos que el recolector escribe allá (ofertas por ciudad, todas, industrias, registro de corridas).
# Uso: sh scripts/desplegar.sh        muestra qué cambiaría, sin subir nada
#      sh scripts/desplegar.sh --ya   sube
set -e
cd "$(dirname "$0")/.."
DESTINO=${DESTINO:-jobmapsco:webapps/Jobmapsco/}
SIMULAR=-n
[ "$1" = "--ya" ] && SIMULAR=
rsync -az $SIMULAR --itemize-changes \
  --exclude .git/ --exclude .env --exclude '.my.sock*' --exclude api/config.php \
  --exclude __pycache__/ --exclude .DS_Store --exclude .claude/ \
  --exclude data/ofertas/ --exclude data/todas.json --exclude data/industrias.json --exclude data/recoleccion.json \
  ./ "$DESTINO" | grep -v '^\.d' || true
[ -n "$SIMULAR" ] && echo "(simulación: corre con --ya para subir)" || echo "subido a $DESTINO"
