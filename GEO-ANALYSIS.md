# GEO y AEO · jobmapsco.xyz (2026-10-13)

Criterio de la skill `seo-geo`: para Google, GEO y AEO son SEO aplicado a buscadores con IA. Lo que más pesa es que los robots de IA no ejecutan JavaScript: el contenido citable tiene que estar en el HTML.

## Puntaje GEO (estimado)

| Criterio | Peso | Antes | Después |
|---|---|---|---|
| Citabilidad (datos concretos, respuestas autocontenidas) | 25 % | 5 | 70 |
| Estructura (H1/H2 en preguntas, tablas, listas) | 20 % | 10 | 85 |
| Multimodal (mapa interactivo, imagen para compartir) | 15 % | 60 | 70 |
| Autoridad y marca (autores, fechas, fuentes, menciones) | 20 % | 20 | 40 |
| Acceso técnico (HTML sin JavaScript, robots, sitemap) | 20 % | 25 | 85 |
| **Total** | | **~22/100** | **~68/100** |

## Acceso de robots de IA

`robots.txt` permite todo salvo `/api/`. Probado el 2026-10-13: GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended y Googlebot reciben 200 (Cloudflare no los bloquea).

## Lo que veía un robot sin JavaScript

- Portada: 143 palabras y "0 ofertas en 0 ciudades" (las cifras las pone el JS).
- Ahora: portada 188 palabras con `<noscript>` (63.051 ofertas, 45 ciudades, Bogotá 46,8 %) y enlace a `acerca.html` (1.068 palabras).

## Cambios hechos

1. `acerca.html`: definición en las primeras 60 palabras ("Job Maps CO es..."), 8 preguntas como H2 con respuesta directa, tablas de 45 ciudades, 23 departamentos y 19 sectores, fecha de corte, autores, fuentes y método. Generada desde `data/ofertas.json` e `industrias.json` (cifras verificadas contra los datos).
2. JSON-LD `Dataset` en `acerca.html` con descarga JSON (`data/ofertas.json`, `data/industrias.json`), cobertura Colombia, fecha y autores.
3. `llms.txt` con resumen, páginas, datos clave y descargas. Google y los estudios citados por la skill no le dan peso de cita hoy; se deja porque cuesta poco.
4. Enlace "Datos y preguntas" en el pie de la portada y `acerca.html` en `sitemap.xml`.
5. Google Search Console: propiedad de dominio `jobmapsco.xyz` verificada por TXT en Cloudflare, sitemap enviado e indexación pedida para `/` y `/acerca.html`.

## Próximos cambios de mayor impacto

1. **Frescura:** las tablas son un corte fijo del 13 de octubre. Regenerar `acerca.html` en cada corrida del recolector (o al menos cada mes); el contenido de menos de 3 meses se cita ~3 veces más.
2. **Páginas por ciudad** (`/empleo/medellin/`…) generadas por el recolector: responden "empleo en Medellín" y similares.
3. **Menciones de marca** (pesan más que los enlaces para la IA): el post de LinkedIn, un hilo en r/Colombia o r/medellin con los datos, y un video corto en YouTube o TikTok.
4. **`sameAs`** en el JSON-LD cuando existan perfiles de Job Maps CO (LinkedIn, X, YouTube).
5. Revisar en Search Console en 1 o 2 semanas: páginas indexadas y consultas con impresiones.
