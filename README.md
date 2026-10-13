# Job Maps CO

Mapa 3D de Colombia con las ofertas de trabajo publicadas por ciudad. Cada ciudad es una columna de luz: entre más alta, más ofertas. Al tocar una ciudad aparecen sus ofertas recientes con el enlace a la fuente original para postularse.

Autores: [Imderf R.](https://imderf.com/) / [Jaime O.](https://jaimeai.co/)

## Qué hace

- **Entrada animada:** un globo de puntos que gira y vuela hasta Colombia.
- **Mapa 3D:** relieve real, ríos y departamentos; los países vecinos quedan atenuados.
- **Rankings** por municipio, departamento e industria.
- **Buscador por palabra clave**, por ejemplo "desarrollador web" o "planner".
- **Filtros coherentes:** al elegir una industria, un departamento o una ciudad, el mapa, el ranking, el total y el panel derecho muestran lo mismo.
- **Ficha por ciudad:** sus ofertas paginadas de a 10, cada una con el botón "Postularme" hacia la fuente original.
- **Registro único:** antes de usar el mapa se piden nombre, correo y la aceptación de la política de datos. Se guarda en MySQL y no se vuelve a pedir en ese navegador.

## Cómo funciona

```
JSearch (RapidAPI) ──► scripts/recolectar.py ──► data/*.json ──► index.html (navegador)
                       (cron, 2 veces al día)                        │
                                                                     ▼
                                                api/registro.php ──► MySQL (tabla registros)
```

- **El sitio es estático.** `index.html` contiene todo, sin compilación. Usa MapLibre GL y deck.gl desde unpkg, y solo lee los archivos de `data/`.
- **El navegador nunca llama a las APIs de empleo.** Las llaves solo las usa el recolector, en el servidor.
- **`scripts/recolectar.py`** usa solo Python estándar (sin `pip install`). Consulta JSearch, clasifica cada oferta por industria según el cargo y escribe `data/`.
- **`api/registro.php`** es lo único que necesita PHP y MySQL.

## Estructura

| Ruta | Qué es |
|---|---|
| `index.html` | Toda la web: mapa, rankings, filtros, buscador y registro |
| `politica-de-datos.html` | Política de tratamiento de datos (Ley 1581 de 2012) |
| `api/registro.php` | Recibe el registro y lo guarda en MySQL |
| `api/config.example.php` | Plantilla de la conexión a MySQL; se copia como `api/config.php` |
| `db/registros.mysql.sql` | Crea la tabla `registros` |
| `scripts/recolectar.py` | Recolector de ofertas (JSearch) y alertas de cupo (Resend) |
| `scripts/preparar_datos.py` | Regenera los datos base del mapa desde `data/raw/` |
| `data/` | Datos que lee el mapa: municipios, departamentos, totales, ofertas por ciudad e industrias |
| `.env.example` | Plantilla de las llaves; se copia como `.env` |
| `.htaccess` | Bloquea en Apache `.env`, `.git`, `scripts/`, `db/` y notas internas |
| `CLAUDE.md` | Notas técnicas y decisiones del proyecto (para Claude Code) |

## Requisitos

- PHP 8.1 o superior, con la extensión `pdo_mysql`.
- MySQL 8 o MariaDB 10.5 o superior.
- Python 3.9 o superior.
- Una llave de [JSearch en RapidAPI](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch). Solo hace falta para actualizar ofertas: el repo ya trae datos, así que el mapa funciona sin llaves.
- Opcional: una cuenta de [Resend](https://resend.com) para recibir un correo cuando el cupo de JSearch se esté acabando.

## Ponerlo a andar en tu computador

**1. Clonar**

```bash
git clone git@github.com:Imderf/jobmapsco.git
cd jobmapsco
```

**2. Llaves**

```bash
cp .env.example .env
```

Abre `.env` y pega tu `RAPIDAPI_KEY`; las de Resend son opcionales. El `.env` está en `.gitignore`: nunca se sube a git.

**3. Base de datos**

Crea la base y un usuario que solo pueda leer y agregar registros. Cambia `CLAVE_SEGURA`:

```bash
mysql -u root -p -e "CREATE DATABASE mapa_empleo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER 'mapa_empleo'@'localhost' IDENTIFIED BY 'CLAVE_SEGURA'; GRANT SELECT, INSERT ON mapa_empleo.* TO 'mapa_empleo'@'localhost';"
```

```bash
mysql -u root -p mapa_empleo < db/registros.mysql.sql
```

**4. Conexión de la web a la base**

```bash
cp api/config.example.php api/config.php
```

En `api/config.php` llena la contraseña (`clave`) y una sal (`sal`), que es un texto aleatorio para cifrar las IP. Genera la sal con:

```bash
php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'
```

`api/config.php` también está en `.gitignore`.

**5. Abrir**

```bash
php -S localhost:4330
```

Entra a http://localhost:4330. Con `?demo` al final de la dirección se simulan subidas y bajadas en vivo.

## Actualizar las ofertas

Primero, una prueba que no gasta consultas:

```bash
python3 -I scripts/recolectar.py --prueba
```

Corrida real, que sí gasta consultas de JSearch:

```bash
python3 -I scripts/recolectar.py
```

Para reclasificar por industria lo ya guardado, sin gastar consultas:

```bash
python3 -I scripts/recolectar.py --industrias
```

En macOS, si Python falla con `CERTIFICATE_VERIFY_FAILED`, antepón `SSL_CERT_FILE=/etc/ssl/cert.pem` al comando.

**Consumo.** Cada corrida hace unas 109 consultas: las 45 ciudades más 18 búsquedas por industria. Con dos corridas al día son unas 6.800 al mes, y eso necesita el plan Pro de JSearch (10.000 al mes). Si haces menos corridas, alcanza un plan más bajo. El ritmo se ajusta con las constantes al inicio de `scripts/recolectar.py` (`CIUDADES_POR_CORRIDA`, `PAGINAS`, `PAGINAS_SECTOR`, `CORRIDAS_AL_DIA`).

**Protección del cupo.**
- **Reserva:** el recolector se detiene si quedan menos de 300 consultas en el mes (`RESERVA`).
- **Avisos:** si configuraste Resend, manda un correo cuando el cupo baja de 2.000, 1.000, 500 y 300, o si JSearch rechaza la llave.
- **Registro:** cada corrida queda en `data/recoleccion.json`.

## Publicar en un servidor

1. **Subir los archivos:** copia el repo a la carpeta web del servidor, con `git clone` o `rsync`.
2. **Crear los archivos privados:** crea `.env` y `api/config.php` directamente en el servidor, nunca desde git. Haz los pasos 2 a 4 de la sección anterior.
3. **Proteger los archivos privados:**
   - **Apache o LiteSpeed:** ya lo hace el `.htaccess` incluido.
   - **Nginx:** agrega esto al bloque `server`:

     ```nginx
     location ~ /\.(?!well-known/) { deny all; }
     location ~ /(scripts|db)/ { deny all; }
     location ~ /CLAUDE\.md$ { deny all; }
     ```

   - **Comprobar:** abre `https://tu-dominio/.env` en el navegador. Tiene que dar 404 o 403.
4. **Permisos:** el usuario que corre el cron tiene que poder escribir en `data/`.
5. **Programar el recolector:** dos veces al día, a las 6 a. m. y 6 p. m. de Colombia, con `crontab -e`. Revisa la zona horaria del servidor con `date`.
   - **Servidor en hora de Colombia:**

     ```
     0 6,18 * * * cd /ruta/a/jobmapsco && /usr/bin/python3 -I scripts/recolectar.py >> /ruta/a/recolector.log 2>&1
     ```

   - **Servidor en UTC:** cambia `0 6,18` por `0 11,23`.
6. **Ajustar lo propio:**
   - **Google Analytics:** el ID `G-WH9WV4JYZB` está en `index.html` y `politica-de-datos.html`. Cámbialo por el tuyo o quita ese bloque.
   - **Política de datos:** en `politica-de-datos.html` cambia `[CORREO DE CONTACTO]` y los responsables.

## Fuentes de datos

- **Totales por ciudad:** línea base tomada a mano de Computrabajo el 13 de octubre de 2026. La entrada del mapa la muestra como corte, no en vivo.
- **Ofertas con enlace:** [JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch), que reúne Google for Jobs (Computrabajo, LinkedIn, elempleo, Magneto, Indeed y otros). Cada ciudad guarda hasta 200 ofertas de los últimos 30 días.
- **Mapa:**
  - relieve SRTM de [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/);
  - agua, ríos y fronteras de [OpenStreetMap](https://www.openstreetmap.org/copyright) vía [OpenFreeMap](https://openfreemap.org);
  - departamentos con base DANE;
  - municipios de DIVIPOLA (MinSalud, datos.gov.co).
- **Regenerar los datos base** después de cambiar algo en `data/raw/`:

  ```bash
  python3 -I scripts/preparar_datos.py
  ```

## Seguridad

- **Llaves:** solo en `.env` y `api/config.php`, fuera de git. Este repo es solo para versiones.
- **Registro:**
  - consultas preparadas, sin SQL armado con texto;
  - validación de datos;
  - límite de 10 registros por hora por IP;
  - campo trampa para bots;
  - la IP se guarda cifrada (SHA-256 con sal).
- **Datos personales:** nunca van en la URL ni se envían a Google Analytics.
- **Textos de las ofertas:** se insertan como texto, nunca como HTML, y los enlaces externos llevan `rel="noopener noreferrer"`.
