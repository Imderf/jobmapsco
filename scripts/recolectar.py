"""Recolector: trae ofertas recientes por ciudad desde JSearch (RapidAPI, agrega Google for Jobs) y las guarda en data/.

Plan Pro de JSearch (10.000 consultas al mes; cada consulta extra se cobra): 2 corridas al día, y en cada una
- 1 búsqueda por cada sector en todo el país (18, incluidos los de agencia), de 3 páginas (30 ofertas); cada oferta va a su ciudad por el lugar que trae
  ("Bogotá • a través de Computrabajo").
- 1 búsqueda general por cada ciudad de la línea base (45); las grandes piden más páginas (cada página = 1 consulta,
  10 ofertas): Bogotá 5, Medellín y Cali 3, Barranquilla y Bucaramanga 2.
109 consultas por corrida ≈ 6.800 al mes. Cada ciudad guarda hasta 200 ofertas de los últimos 30 días. Si en el mes quedan menos de RESERVA consultas, se detiene (sin cobros extra).
Cada consulta trae hasta 10 ofertas con enlace directo al portal. Cada ciudad guarda sus 30 más recientes (máx. 30 días).

Escribe:
- data/ofertas/<divipola>.json  ofertas de cada ciudad (las nuevas se suman a las anteriores)
- data/industrias.json          conteo por industria sobre todas las ofertas guardadas
- data/todas.json               todas las ofertas guardadas con su ciudad (el buscador por palabras y los filtros de la página)
- data/recoleccion.json         turno siguiente y registro de las últimas corridas

Uso: python3 -I scripts/recolectar.py          (llave en RAPIDAPI_KEY o en .env)
     python3 -I scripts/recolectar.py --prueba (solo verifica la clasificación y la rotación, sin gastar consultas)
     python3 -I scripts/recolectar.py --industrias (reclasifica lo guardado, sin gastar consultas)
"""
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
CIUDADES_POR_CORRIDA = 45     # todas (con el plan gratis eran 1 o 2 por turnos)
PAGINAS = ((20000, 5), (5000, 3), (1500, 2))
PAGINAS_SECTOR = 3            # cada búsqueda por sector trae 30 ofertas (3 consultas)   # (ofertas en la línea base desde, páginas): más ofertas para las ciudades grandes
CORRIDAS_AL_DIA = 2           # 6 a. m. y 6 p. m. (el horario está en .github/workflows/recolectar.yml)
RESERVA = 300                 # consultas del mes que nunca se gastan: protege de cobros por exceso
PAUSA = 0.3                   # segundos entre consultas (límite del plan: 5 por segundo)
AVISOS = (2000, 1000, 500, RESERVA)   # consultas restantes del mes que disparan un correo (una vez cada una por mes)
JOOBLE_CUPO = 2900            # consultas de Jooble por mes: ampliado el 2026-10-27 a pedido de 3.000/mes (no confirmaron la cifra exacta)
JOOBLE_DEPTOS_DIAS = 7        # los departamentos cambian despacio: se piden una vez por semana
MAX_POR_CIUDAD = 200
VIGENCIA_DIAS = 30
API = "https://jsearch.p.rapidapi.com/search-v2"

# Primera regla que coincide con el cargo gana; el orden importa ("auxiliar de enfermería" antes que "auxiliar").
# Primera regla que coincide con el cargo gana; el orden importa. Un sector puede tener varias reglas en distinto
# orden (talento humano va antes que operaciones por " sst"; el resto de administración, después).
INDUSTRIAS = [
    ("Salud", ["enfermer", "medic", "odontolog", "farmac", "droguer", "regente", "fisioterap", "bacteriolog", "salud", "clinic", "terapeuta", "psicolog", "hospitaliz", "microbiolog"]),
    ("Desarrollo y Tecnología", ["desarrollador", "developer", "software", "devops", "programador", "sistemas", "datos", "data ", "qa ", "tester", "frontend", "backend", "full stack", "soporte tecnico", "cloud", "ciberseguridad", " it ", " ti ", "product owner", "scrum"]),
    ("Trade Marketing", ["trade marketing", "trade mkt", "shopper"]),
    ("Medios", ["planeador de medios", "compra de medios", "central de medios", "agencia de medios", "media planner", "media buyer", "medios de comunicacion"]),
    ("Planeación", ["planner", "planeacion estrategica", "planeador estrategico", "estratega", "strategist"]),
    ("Cuentas", ["account", "director de cuentas", "directora de cuentas", "cuentas publicitarias"]),
    ("Audiovisual", ["audiovisual", "editor de video", "video", "camarograf", "fotograf", "postproduc", "animador", "motion"]),
    ("Diseño y Arte", ["disenador", "diseno grafico", "director de arte", "directora de arte", " arte", "ilustrador", " ux", " ui "]),
    ("Creatividad", ["creativ", "copywriter", "redactor", " copy "]),
    ("Publicidad", ["publicidad", "publicitari", "agencia de publicidad", "agencia creativa"]),
    ("Eventos", ["evento", " btl", "activacion"]),
    ("Digital", ["digital", "social media", "community", "redes sociales", " seo", " sem ", "pauta", "e-commerce", "ecommerce", "growth", "contenido", "website", " web "]),
    ("Comunicación", ["comunicacion", "comunicador", "periodist", "relaciones publicas"]),
    ("Marketing", ["marketing", "mercadeo", "brand", "encuest", "investigacion de mercado"]),
    ("Ventas", ["ventas", "vendedor", "comercial", "asesor", "telemercad", "mercaderista", "impulsador", "promotor", "autoventa", "preventa", "cajer", "sales", "tienda", "almacen ", "punto de venta", "market", "categorias", "jefe de zona", "ejecutivo de cuenta", "seguros", "surtido", "volantea", "consultor de servicios",
                "call center", "contact center", "servicio al cliente", "atencion al cliente", "atencion a clientes", "experiencia al cliente", "auxiliar de servicio", "agente", "agent ", "teleoperador", "bilingue", "bilingual", "customer", "vinculacion"]),
    ("Administración y talento humano", ["talento humano", "recursos humanos", "gestion humana", "seleccion", "reclutador", "contratacion", "entrenamiento", "trainer", "human resources", "hr "]),
    ("Operaciones y logística", ["conductor", "bodeg", "logistic", "almacenista", "almacenamiento", "despachador", "montacarg", "motacarg", "mensajer", "domiciliari", "inventario", "transport", "distribucion", "reparto", "picking", "entrega", "recoleccion", " ruta", "trafico", "proveeduria", " carga", "asistencia en tierra",
                                 "guarda", "vigilante", "seguridad", "aseo", "servicios generales", "limpieza", "escolta", "cctv", "monitoreo", "medios tecnologicos", "control perdidas", "lavanderia", "domestic", "roceria", "guadan",
                                 "operari", "operador", "operativo", "oficios varios", "obrero", "ayudante", "produccion", "planta", "ensambl", "manufactura", "empacador", "maquina", "tornero", "polifuncional", "taller", "quimico",
                                 " sst", "hseq", "ambiental", "calidad", "inspector", "cumplimiento",
                                 "obra", "construccion", "civil", "electricista", "mantenimiento", "tecnico", "soldador", "mecanic", "ingenier", "residente", "montajes", "automation", "cargue", "motorizado", "valet", "impresion", "automotriz", "operaciones", "aeroportuario", "arquitect", "tapicer"]),
    ("Administración y talento humano", ["contador", "contable", "contabilidad", "administrativ", "administrador", "financier", "cartera", "cobranza", "cobro", "tesorer", "facturacion", "credito", "nomina", "auditor", "riesgo", "informes", "analista juridico", "abogad", "recepcionista", "secretari", "archivo", "documental", "office", "payroll", "invoic", "gerente", "coordinador", "gestor", "administracion"]),
    ("Hotelería y alimentos", ["cocin", "mesero", "chef", "panader", "barista", "hotel", "restaurante", "alimentos", "alimentacion", "steward", "cafeteria", "carnicer", "parrillero", "casino"]),
]


# Búsqueda por industria (todo Colombia), en orden de turno
BUSQUEDAS = {
    "Desarrollo y Tecnología": "desarrollador software", "Salud": "enfermería salud", "Ventas": "asesor comercial ventas servicio al cliente",
    "Operaciones y logística": "operario logística bodega producción", "Administración y talento humano": "contador administrativo recursos humanos",
    "Hotelería y alimentos": "cocinero mesero",
    # sectores de agencia
    "Audiovisual": "productor audiovisual editor de video", "Comunicación": "comunicador social comunicaciones",
    "Creatividad": "creativo publicitario copywriter", "Cuentas": "ejecutivo de cuentas agencia de publicidad",
    "Digital": "social media pauta digital", "Diseño y Arte": "diseñador gráfico director de arte",
    "Eventos": "productor de eventos BTL", "Marketing": "marketing mercadeo", "Medios": "planeador de medios",
    "Planeación": "planner estratégico", "Publicidad": "agencia de publicidad", "Trade Marketing": "trade marketing",
}


# sectores que se unificaron: las ofertas guardadas con la búsqueda vieja ("q") pasan al sector nuevo
RENOMBRADAS = {"Marketing y comunicación": "Marketing", "Tecnología": "Desarrollo y Tecnología", "Ventas y comercial": "Ventas", "Servicio al cliente": "Ventas",
               "Producción y operarios": "Operaciones y logística", "Logística y transporte": "Operaciones y logística", "Seguridad y aseo": "Operaciones y logística",
               "Construcción y mantenimiento": "Operaciones y logística", "Calidad, SST y ambiente": "Operaciones y logística",
               "Administración y finanzas": "Administración y talento humano", "Recursos humanos": "Administración y talento humano",
               "Prácticas y aprendices": None, "Educación": None}


def simple(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return " " + "".join(c for c in s if unicodedata.category(c) != "Mn") + " "


def industria(cargo):
    t = simple(cargo)
    return next((nombre for nombre, claves in INDUSTRIAS if any(k in t for k in claves)), "Otros")


def turno(codigos, siguiente, n):
    """Las n ciudades que tocan hoy y el índice de la próxima corrida (da la vuelta al final)."""
    if not codigos:
        return [], 0
    hoy = [codigos[(siguiente + k) % len(codigos)] for k in range(min(n, len(codigos)))]
    return hoy, (siguiente + len(hoy)) % len(codigos)


def oferta(j):
    """Solo lo que la página muestra. Enlaces que no sean http(s) se descartan (dato externo)."""
    enlace = (j.get("job_apply_link") or "").strip()
    if not enlace.startswith(("https://", "http://")) or not j.get("job_title"):
        return None
    return {
        "t": j["job_title"].strip()[:160],
        "e": (j.get("employer_name") or "").strip()[:90],
        "p": (j.get("job_publisher") or "").strip()[:40],
        "u": enlace[:600],
        "f": j.get("job_posted_at_datetime_utc"),
        "h": (j.get("job_posted_at") or "")[:40],
        "s": (j.get("job_salary_string") or "")[:60],
        "i": industria(j["job_title"]),
    }


def indice_ciudades(municipios, ofertas_base):
    """nombre normalizado → código DIVIPOLA. Nombres repetidos: gana el de más ofertas en la línea base."""
    idx = {}
    for m in sorted(municipios, key=lambda m: ofertas_base.get(m["c"], 0)):
        n = simple(m["n"]).strip()
        for alias in {n, n.replace(" d.c.", "").replace(" dc", ""), n.split(" de ")[0]}:
            idx[alias] = m["c"]
    return idx


def ciudad_de(j, idx):
    lugar = (j.get("job_city") or j.get("job_location") or "").split("•")[0].split(",")[0]
    n = simple(lugar).strip()
    if n in ("", "colombia", "remoto", "remote"):   # sin ciudad (existe un municipio "Colombia" en el Huila)
        return None
    return idx.get(n) or idx.get(n.split(" de ")[0])


def guardar(cod, nuevas, ahora):
    """Suma las nuevas a las guardadas: sin repetir enlace, máximo 30, nada de hace más de 30 días."""
    f = DATA / "ofertas" / f"{cod}.json"
    viejas = json.loads(f.read_text())["ofertas"] if f.exists() else []
    limite = datetime.now(timezone.utc).timestamp() - VIGENCIA_DIAS * 86400
    vistos, lista = set(), []
    for o in nuevas + viejas:
        o.setdefault("r", ahora)
        if o["u"] in vistos or datetime.fromisoformat(o["r"]).timestamp() < limite:
            continue
        vistos.add(o["u"]); lista.append(o)
    f.write_text(json.dumps({"actualizado": ahora, "fuente": "JSearch (Google for Jobs)", "ofertas": lista[:MAX_POR_CIUDAD]}, ensure_ascii=False, indent=1))
    return len(nuevas)


def config(nombre):
    """Variable de entorno o línea del .env de la raíz del proyecto."""
    if os.environ.get(nombre):
        return os.environ[nombre].strip()
    env = RAIZ / ".env"
    for linea in env.read_text().splitlines() if env.exists() else []:
        k, _, v = linea.partition("=")
        if k.strip() == nombre:
            return v.strip()
    return None


def llave():
    return config("RAPIDAPI_KEY") or sys.exit("Falta RAPIDAPI_KEY (variable de entorno o .env)")


def avisar(asunto, texto):
    """Correo por Resend a AVISO_CORREO. Sin RESEND_API_KEY o sin destino, solo queda en el registro de la corrida."""
    print(f"AVISO: {asunto}")
    clave, para = config("RESEND_API_KEY"), config("AVISO_CORREO")
    if not (clave and para):
        return False
    cuerpo = json.dumps({"from": config("AVISO_REMITENTE") or "Job Maps CO <onboarding@resend.dev>",
                         "to": [para], "subject": asunto, "text": texto}).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=cuerpo,
                                 headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json", "User-Agent": "mapa-empleo"})
    try:
        with urllib.request.urlopen(req, timeout=20):
            return True
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  no se pudo enviar el correo: {e}")
        return False


def avisos_pendientes(restantes, previo):
    """Umbrales de AVISOS cruzados que no se han avisado este mes. Si el cupo subió, empezó un mes nuevo."""
    if restantes is None:
        return [], previo
    enviados = [] if restantes > previo.get("restantes", 10 ** 9) else previo.get("enviados", [])
    nuevos = [u for u in AVISOS if restantes < u and u not in enviados]
    return nuevos, {"restantes": restantes, "enviados": enviados + nuevos}


def paginas(n):
    return next((p for desde, p in PAGINAS if n >= desde), 1)


def consultar(clave, texto, num_paginas=1):
    q = urllib.parse.urlencode({"query": texto, "country": "co", "num_pages": num_paginas, "date_posted": "month"})
    req = urllib.request.Request(f"{API}?{q}", headers={"x-rapidapi-key": clave, "x-rapidapi-host": "jsearch.p.rapidapi.com"})
    for intento in (1, 2):   # JSearch a veces tarda: un reintento si se vence el tiempo
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r), r.headers.get("x-ratelimit-requests-remaining"), r.headers.get("x-ratelimit-requests-reset")
        except TimeoutError:
            if intento == 2:
                raise


def resumir_industrias():
    """Reclasifica lo guardado (por si cambiaron las reglas), cuenta por industria y escribe data/todas.json."""
    conteo, muestra, ciudades, por_ciudad, todas = {}, 0, 0, {}, []
    for f in (DATA / "ofertas").glob("*.json"):
        d = json.loads(f.read_text())
        ofertas = d["ofertas"]
        for o in ofertas:
            o["i"] = industria(o["t"])
            if o.get("q") in RENOMBRADAS:
                o["q"] = RENOMBRADAS[o["q"]]
            if o["i"] == "Otros" and o.get("q"):
                o["i"] = o["q"]
            cod = por_ciudad.setdefault(o["i"], {})
            cod[f.stem] = cod.get(f.stem, 0) + 1
            todas.append({**{k: o[k] for k in ("t", "e", "p", "u", "h", "s", "i") if o.get(k)}, "c": f.stem})
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        ciudades += bool(ofertas)
        for o in ofertas:
            conteo[o["i"]] = conteo.get(o["i"], 0) + 1
            muestra += 1
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (DATA / "todas.json").write_text(json.dumps({"actualizado": ahora, "fuente": "JSearch (Google for Jobs)", "ofertas": todas}, ensure_ascii=False, separators=(",", ":")))
    nombres = list(dict.fromkeys(n for n, _ in INDUSTRIAS)) + ["Otros"]
    orden = {n: conteo.get(n, 0) for n in sorted(nombres, key=lambda n: (-conteo.get(n, 0), n == "Otros"))}
    return {"muestra": muestra, "ciudades": ciudades, "industrias": orden, "por_ciudad": por_ciudad}


def lugar_jooble(m, deptos):
    """Texto de ubicación para Jooble: "Ciudad, Departamento" separa homónimos (Rionegro de Antioquia o de Santander)."""
    return "Bogotá" if m["c"] == "11001" else f"{m['n']}, {deptos[m['d']]}"


def total_jooble(clave, lugar):
    """totalCount de Jooble Colombia para una ubicación, solo ese lugar (radio 0)."""
    req = urllib.request.Request(f"https://co.jooble.org/api/{clave}", headers={"Content-Type": "application/json", "User-Agent": "jobmapsco"},
                                 data=json.dumps({"keywords": "", "location": lugar, "radius": "0"}).encode())
    time.sleep(PAUSA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("totalCount")


def toca_deptos(ultima, hoy):
    """¿Ya pasó una semana desde los últimos totales por departamento?"""
    return not ultima or (date.fromisoformat(hoy) - date.fromisoformat(ultima)).days >= JOOBLE_DEPTOS_DIAS


def actualizar_totales():
    """Totales de Jooble Colombia → data/ofertas.json: cada ciudad en cada corrida y cada departamento una vez por semana
    (cuida el cupo mensual). Guarda la cifra anterior para que el mapa anime ▲▼. Si algo falla, deja los totales de antes."""
    clave = config("JOOBLE_KEY")
    if not clave:
        return print("totales: sin JOOBLE_KEY, se dejan los de antes")
    base_f, estado_f = DATA / "ofertas.json", DATA / "recoleccion.json"
    base = json.loads(base_f.read_text())
    muni = json.loads((DATA / "municipios.json").read_text())
    estado = json.loads(estado_f.read_text()) if estado_f.exists() else {"siguiente": 0, "registro": []}
    por_cod = {m["c"]: m for m in muni["municipios"]}
    hoy = datetime.now(timezone.utc).date().isoformat()
    if estado.get("jooble_mes") != hoy[:7]:   # cupo mensual: el contador vuelve a cero cada mes
        estado.update(jooble_mes=hoy[:7], jooble_usadas=0)
        estado.setdefault("avisos", {}).update(jooble_agotado=False, jooble_rechazo=False)
    usadas = estado.get("jooble_usadas", 0)
    pedir_deptos = toca_deptos(estado.get("jooble_deptos_fecha"), hoy)
    necesarias = len(base["ciudades"]) + (len(muni["deptos"]) - 1 if pedir_deptos else 0)
    if usadas + necesarias > JOOBLE_CUPO:
        if not estado.setdefault("avisos", {}).get("jooble_agotado"):
            avisar("Job Maps CO: se acabó el cupo de Jooble",
                   f"Se usaron {usadas} de las {JOOBLE_CUPO} consultas del mes. El mapa se queda con los totales del {base.get('actualizado')} y vuelve a actualizarse el mes entrante.")
            estado["avisos"]["jooble_agotado"] = True
            estado_f.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
        return print(f"totales: cupo de Jooble del mes agotado ({usadas} de {JOOBLE_CUPO}), se dejan los de antes")

    def pedir(lugares):   # {código: texto de ubicación} → {código: total}; para ante llave rechazada o cupo agotado
        nonlocal usadas
        res = {}
        for cod, lugar in lugares.items():
            try:
                n = total_jooble(clave, lugar)
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                print(f"  totales: {lugar}: {e}")
                usadas += 1
                if getattr(e, "code", None) in (401, 403, 429):   # llave rechazada o cupo real menor al esperado
                    if not estado.setdefault("avisos", {}).get("jooble_rechazo"):
                        avisar("Job Maps CO: Jooble rechazó las consultas", f"Respuesta HTTP {e.code} con {usadas} consultas usadas este mes. "
                               "Puede que el cupo ampliado sea menor de lo pedido; el mapa conserva los últimos totales.")
                        estado["avisos"]["jooble_rechazo"] = True
                    break
                continue
            usadas += 1
            if isinstance(n, int) and n > 0:
                res[cod] = n
        return res

    lugares = {cod: lugar_jooble(por_cod[cod], muni["deptos"]) for cod in base["ciudades"]}
    nuevos = pedir(lugares)
    if len(nuevos) < len(base["ciudades"]) * .8:   # media corrida no reemplaza un total completo
        estado["jooble_usadas"] = usadas
        estado_f.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
        return print(f"totales: solo {len(nuevos)} ciudades respondieron, se dejan los de antes ({usadas} consultas de Jooble usadas)")
    deptos = base.get("deptos") if base.get("deptos_fuente") == "Jooble" else None
    if pedir_deptos:
        d = pedir({cod: nombre for cod, nombre in muni["deptos"].items() if cod != "11"})
        if len(d) >= (len(muni["deptos"]) - 1) * .8:
            deptos = d
            estado["jooble_deptos_fecha"] = hoy
    if deptos is None:   # aún sin departamentos de Jooble: suma de las ciudades medidas
        deptos = {}
        for cod, n in nuevos.items():
            deptos[por_cod[cod]["d"]] = deptos.get(por_cod[cod]["d"], 0) + n
        fuente_deptos = "suma de ciudades"
    else:
        fuente_deptos = "Jooble"
    deptos["11"] = nuevos.get("11001", deptos.get("11", 0))   # Bogotá D.C. es ciudad y departamento a la vez
    estado["jooble_usadas"] = usadas
    estado_f.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    # la primera vez lo anterior es el corte de Computrabajo: comparar fuentes distintas daría flechas falsas
    anterior = base["ciudades"] if base.get("fuente", "").startswith("Jooble") else None
    base.update(actualizado=datetime.now(timezone.utc).isoformat(timespec="seconds"), fuente="Jooble Colombia (API, total por ciudad)",
                ciudades=nuevos, deptos=deptos, deptos_fuente=fuente_deptos, anterior=anterior,
                enlaces={cod: "https://co.jooble.org/SearchResult?" + urllib.parse.urlencode({"rgns": lugares[cod]}) for cod in nuevos})
    base_f.write_text(json.dumps(base, ensure_ascii=False, indent=1))
    print(f"totales: {len(nuevos)} ciudades, {sum(nuevos.values()):,} ofertas; departamentos: {fuente_deptos}; {usadas} de {JOOBLE_CUPO} consultas de Jooble este mes")
    escribir_resumen()


MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def escribir_resumen():
    """acerca.html y llms.txt con las cifras del momento: texto fijo y citable para buscadores y robots de IA.
    Toda comparación se calcula de los datos, para que la página nunca afirme algo que ya no es cierto."""
    import html
    o = json.loads((DATA / "ofertas.json").read_text())
    m = json.loads((DATA / "municipios.json").read_text())
    ind_f = DATA / "industrias.json"
    ind = json.loads(ind_f.read_text()) if ind_f.exists() else {"industrias": {}, "muestra": 0, "ciudades": 0}
    mun, dep, e = {x["c"]: x for x in m["municipios"]}, m["deptos"], html.escape
    f = lambda n: f"{n:,}".replace(",", ".")
    p = lambda n, t: f"{n / t * 100:.1f}".replace(".", ",") + " %"
    nom = lambda c: "Bogotá" if c == "11001" else mun[c]["n"]
    dt = datetime.fromisoformat(o["actualizado"]) if "T" in o["actualizado"] else datetime.fromisoformat(o["actualizado"] + "T12:00:00+00:00")
    dt = dt.astimezone(timezone(timedelta(hours=-5)))
    fecha = f"{dt.day} de {MESES[dt.month - 1]} de {dt.year}"
    jooble = o.get("fuente", "").startswith("Jooble")
    fuente = "Jooble Colombia" if jooble else "Computrabajo"
    ciu = sorted(o["ciudades"].items(), key=lambda x: -x[1]); T = sum(o["ciudades"].values())
    dps = sorted(((d, n) for d, n in o["deptos"].items() if n), key=lambda x: -x[1]); TD = sum(n for _, n in dps)
    sec = sorted(((k, v) for k, v in ind["industrias"].items() if v), key=lambda x: -x[1]); TS = ind.get("muestra") or sum(v for _, v in sec)
    (c1, n1), top3 = ciu[0], sum(n for _, n in ciu[:3])
    # municipios que no son capital con mucha oferta, frente a capitales con menos (solo si de verdad es así)
    no_cap = [(c, n) for c, n in ciu if not c.endswith("001")][:4]
    piso = min(n for _, n in no_cap) if no_cap else 0
    capitales = [c for c, n in ciu if c.endswith("001") and n < piso][:3]
    def lista(xs):
        xs = list(xs)
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]
    def lista_o(xs):
        xs = list(xs)
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " o " + xs[-1]
    pequenas = (f"{lista(f'{nom(c)} ({f(n)})' for c, n in no_cap)} tienen más ofertas que capitales como {lista_o(nom(c) for c in capitales)}. "
                if capitales else f"Entre los municipios que no son capital, los de más ofertas son {lista(f'{nom(c)} ({f(n)})' for c, n in no_cap)}. ")
    filas_c = "\n".join(f"<tr><td>{i}</td><td>{e(nom(c))}</td><td>{e(dep[mun[c]['d']])}</td><td>{f(n)}</td><td>{p(n, T)}</td></tr>" for i, (c, n) in enumerate(ciu, 1))
    filas_d = "\n".join(f"<tr><td>{i}</td><td>{e(dep[d])}</td><td>{f(n)}</td></tr>" for i, (d, n) in enumerate(dps, 1))
    filas_s = "\n".join(f"<tr><td>{e(k)}</td><td>{f(v)}</td><td>{p(v, TS)}</td></tr>" for k, v in sec)
    s2 = sum(v for _, v in sec[:2])
    D = "https://jobmapsco.xyz/"
    desc = f"Ofertas de trabajo publicadas en Colombia por ciudad y departamento: {f(T)} ofertas en {len(ciu)} ciudades el {fecha}, según {fuente}. {nom(c1)} concentra el {p(n1, T)}."
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "Ofertas de trabajo publicadas en Colombia por ciudad y departamento",
          "description": f"Número de ofertas de trabajo publicadas en {len(ciu)} ciudades y {len(dps)} departamentos de Colombia según {fuente}, actualizado dos veces al día, y una muestra de ofertas recientes clasificadas por sector. Base del mapa 3D Job Maps CO.",
          "url": D + "acerca.html", "inLanguage": "es-CO", "isAccessibleForFree": True, "temporalCoverage": dt.date().isoformat(), "dateModified": dt.date().isoformat(),
          "spatialCoverage": {"@type": "Country", "name": "Colombia"},
          "creator": [{"@type": "Person", "name": "Imderf R.", "url": "https://imderf.com/"}, {"@type": "Person", "name": "Jaime O.", "url": "https://jaimeai.co/"}],
          "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": D + "data/ofertas.json"},
                           {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": D + "data/industrias.json"}]}
    if jooble:
        origen = (f"Los totales por ciudad y por departamento vienen de Jooble Colombia, que reúne vacantes de muchos portales. Las ciudades se actualizan dos veces al día, a las 6 a. m. y 6 p. m. hora de Colombia, y los departamentos una vez al día; cada cifra cuenta solo las ofertas de ese lugar, sin su área metropolitana. "
                  "Las ofertas con enlace que ves al tocar una ciudad se recogen desde Google for Jobs a través de la API JSearch (Computrabajo, LinkedIn, elempleo, Magneto, Indeed y otros); cada ciudad muestra hasta 200 de los últimos 30 días. Las cifras no cubren todo el mercado laboral: faltan vacantes que no se publican en internet.")
    else:
        origen = "Los totales por ciudad y departamento son un corte de Computrabajo tomado a mano el 13 de octubre de 2026. Las ofertas con enlace se recogen dos veces al día desde Google for Jobs a través de la API JSearch."
    GA = """<script async src="https://www.googletagmanager.com/gtag/js?id=G-WH9WV4JYZB"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-WH9WV4JYZB');
</script>"""
    pagina = f"""<!doctype html>
<html lang="es-CO">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ofertas de trabajo en Colombia por ciudad · Job Maps CO</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{D}acerca.html">
<meta name="theme-color" content="#04060c">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Job Maps CO">
<meta property="og:locale" content="es_CO">
<meta property="og:url" content="{D}acerca.html">
<meta property="og:title" content="¿Dónde hay trabajo en Colombia? Ofertas por ciudad">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{D}og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.svg?v=2" type="image/svg+xml">
<link rel="icon" href="favicon-32.png?v=2" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="apple-touch-icon.png?v=2">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False)}
</script>
{GA}
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Inter+Tight:wght@800&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
:root{{--bg:#04060c;--text:#e6ebf7;--muted:#8a94b3;--blue:#2f6bff;--line:rgba(110,140,255,.17)}}
body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.65 Inter,system-ui,sans-serif}}
main{{max-width:780px;margin:0 auto;padding:40px 20px 80px}}
.ojo{{font:400 11px 'JetBrains Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:#6b95ff}}
h1{{font:800 clamp(28px,5vw,40px)/1.05 'Inter Tight',sans-serif;letter-spacing:-.02em;margin:8px 0 14px}}
h2{{font:800 21px/1.2 'Inter Tight',sans-serif;margin:40px 0 10px}}
p,li{{color:#c9d0e4}}
.sub{{color:var(--muted);font-size:13px}}
a{{color:#6b95ff}}
.boton{{display:inline-block;margin:6px 0 4px;padding:10px 16px;border:1px solid var(--blue);border-radius:8px;color:#fff;background:rgba(47,107,255,.15);text-decoration:none;font-weight:500}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{color:var(--muted);font-weight:500}}
td:nth-child(n+3),th:nth-child(n+3){{text-align:right;font-variant-numeric:tabular-nums}}
.tabla{{overflow-x:auto}}
</style>
</head>
<body>
<main>
  <div class="ojo">Job Maps CO · datos y preguntas frecuentes</div>
  <h1>¿Dónde hay trabajo en Colombia? Ofertas por ciudad y departamento</h1>
  <p><strong>Job Maps CO</strong> es un mapa 3D gratuito que muestra cuántas ofertas de trabajo hay publicadas en cada ciudad de Colombia y enlaza a la fuente para ver y postularse a cada oferta. El {fecha} había <strong>{f(T)} ofertas publicadas en {fuente} en las {len(ciu)} ciudades medidas</strong>. {nom(c1)} concentra el {p(n1, T)}, y {lista(nom(c) for c, _ in ciu[:3])} juntas suman el {p(top3, T)}.</p>
  <p class="sub">Actualizado el {fecha} · Por <a href="https://imderf.com/" rel="author">Imderf R.</a> y <a href="https://jaimeai.co/" rel="author">Jaime O.</a></p>
  <a class="boton" href="./">Abrir el mapa 3D →</a>

  <h2>¿Qué ciudades de Colombia tienen más ofertas de trabajo?</h2>
  <p>{nom(c1)} lidera con {f(n1)} ofertas publicadas, seguida de {lista(f'{nom(c)} ({f(n)})' for c, n in ciu[1:7])}. Esta es la tabla completa de las {len(ciu)} ciudades medidas el {fecha}:</p>
  <div class="tabla"><table>
<thead><tr><th>#</th><th>Ciudad</th><th>Departamento</th><th>Ofertas</th><th>% del total</th></tr></thead>
<tbody>
{filas_c}
</tbody></table></div>

  <h2>¿Qué municipios que no son capital tienen mucha oferta de empleo?</h2>
  <p>{pequenas}Varios son municipios vecinos de las grandes ciudades, con bodegas, plantas y centros de distribución que contratan en operaciones, logística y producción.</p>

  <h2>¿Qué departamentos tienen más ofertas de trabajo?</h2>
  <p>{lista(f'{dep[d]} ({f(n)})' for d, n in dps[:3])} encabezan la lista. Total de los {len(dps)} departamentos con datos: {f(TD)} ofertas.</p>
  <div class="tabla"><table>
<thead><tr><th>#</th><th>Departamento</th><th>Ofertas</th></tr></thead>
<tbody>
{filas_d}
</tbody></table></div>

  <h2>¿Qué tipo de empleos hay en Colombia?</h2>
  <p>En una muestra de {f(TS)} ofertas recientes recogidas en {ind.get('ciudades', 0)} ciudades, {sec[0][0].lower() if sec else ''}{' y ' + sec[1][0].lower() if len(sec) > 1 else ''} suman el {p(s2, TS) if TS else '0 %'} de las vacantes. Cada oferta se clasifica por su cargo en 18 sectores, incluidos los creativos y digitales (publicidad, diseño, marketing, medios, tecnología). Es una muestra para comparar sectores, no el total del mercado.</p>
  <div class="tabla"><table>
<thead><tr><th>Sector</th><th>Ofertas</th><th>% de la muestra</th></tr></thead>
<tbody>
{filas_s}
</tbody></table></div>

  <h2>¿Cómo buscar empleo con Job Maps CO?</h2>
  <ol>
    <li>Abre el <a href="./">mapa</a>: cada ciudad es una columna de luz; entre más alta, más ofertas.</li>
    <li>Escribe una palabra clave (por ejemplo "desarrollador web" o "planner") o elige un sector.</li>
    <li>Mira qué ciudades tienen ofertas de lo tuyo en el ranking o en el mapa.</li>
    <li>Toca una ciudad para ver sus ofertas recientes{' y el enlace a todas sus ofertas en Jooble' if jooble else ''}.</li>
    <li>Usa "Postularme" para ir a la oferta en su fuente original.</li>
  </ol>

  <h2>¿De dónde salen los datos y cada cuánto se actualizan?</h2>
  <p>{origen}</p>

  <h2>¿Job Maps CO es gratis?</h2>
  <p>Sí. Solo pide nombre y correo una vez, con aceptación de la <a href="politica-de-datos.html">política de tratamiento de datos</a>. Job Maps CO no publica vacantes ni cobra a quien se postula: lleva a la oferta original.</p>

  <h2>¿Quién hace Job Maps CO?</h2>
  <p>Es un proyecto independiente de <a href="https://imderf.com/">Imderf R.</a> y <a href="https://jaimeai.co/">Jaime O.</a>, construido con Claude Code. Contacto: <a href="mailto:contacto@jobmapsco.xyz">contacto@jobmapsco.xyz</a>.</p>

  <p class="sub">Datos descargables: <a href="data/ofertas.json">ofertas por ciudad y departamento (JSON)</a> · <a href="data/industrias.json">ofertas por sector (JSON)</a>{' · Totales: <a href="https://co.jooble.org" rel="noopener">Jooble</a>' if jooble else ''}</p>
</main>
</body>
</html>
"""
    (RAIZ / "acerca.html").write_text(pagina)
    (RAIZ / "llms.txt").write_text(f"""# Job Maps CO

> Mapa 3D gratuito de las ofertas de trabajo publicadas en Colombia, ciudad por ciudad, con enlace a la fuente de cada oferta para postularse. Sitio en español (Colombia): {D}

## Páginas
- [Mapa 3D]({D}): ranking por municipio, departamento y sector; buscador por palabra clave; ofertas por ciudad con botón para postularse.
- [Datos y preguntas frecuentes]({D}acerca.html): ofertas por ciudad, departamento y sector en tablas, fuentes y método. Se actualiza dos veces al día.
- [Política de datos]({D}politica-de-datos.html): tratamiento de datos personales (Ley 1581 de 2012).

## Datos
- [Ofertas por ciudad y departamento (JSON)]({D}data/ofertas.json): totales de {fuente}; ciudades con código DIVIPOLA del DANE.
- [Ofertas por sector (JSON)]({D}data/industrias.json): muestra de ofertas recientes clasificadas por cargo en 18 sectores.

## Datos clave ({fecha})
- {f(T)} ofertas publicadas en {fuente} en {len(ciu)} ciudades de Colombia.
- {"; ".join(f"{nom(c)}: {f(n)}" for c, n in ciu[:5])}.
- {nom(c1)} concentra el {p(n1, T)} de las ofertas de las ciudades medidas.

## Autores
Imderf R. (https://imderf.com/) y Jaime O. (https://jaimeai.co/). Contacto: contacto@jobmapsco.xyz
""")
    print(f"resumen: acerca.html y llms.txt con datos del {fecha}")

def main():
    clave = llave()
    base = json.loads((DATA / "ofertas.json").read_text())
    muni = json.loads((DATA / "municipios.json").read_text())
    por_cod = {m["c"]: m for m in muni["municipios"]}
    codigos = sorted(base["ciudades"], key=lambda c: -base["ciudades"][c])
    estado_f = DATA / "recoleccion.json"
    estado = json.loads(estado_f.read_text()) if estado_f.exists() else {"siguiente": 0, "registro": []}
    ciudades_hoy, sig_c = turno(codigos, estado.get("siguiente", 0), CIUDADES_POR_CORRIDA)
    industrias_hoy, sig_i = turno(list(BUSQUEDAS), estado.get("siguiente_industria", 0), len(BUSQUEDAS))
    idx = indice_ciudades(muni["municipios"], base["ciudades"])

    (DATA / "ofertas").mkdir(exist_ok=True)
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    hechas, errores, restantes, renueva, total = [], [], None, None, 0
    for tipo, x in [("industria", i) for i in industrias_hoy] + [("ciudad", c) for c in ciudades_hoy]:
        nombre = x if tipo == "industria" else por_cod[x]["n"]
        texto = f"{BUSQUEDAS[x]} en Colombia" if tipo == "industria" else f"empleos en {nombre}, {muni['deptos'][por_cod[x]['d']]}"
        if restantes is not None and int(restantes) < RESERVA:
            errores.append(f"se detuvo: quedan {restantes} consultas del mes (reserva {RESERVA})")
            break
        time.sleep(PAUSA)
        try:
            cuerpo, restantes, renueva = consultar(clave, texto, PAGINAS_SECTOR if tipo == "industria" else paginas(base["ciudades"][x]))
        except urllib.error.HTTPError as e:
            errores.append(f"{nombre}: HTTP {e.code}")
            if e.code in (401, 403, 429):   # llave inválida o cupo agotado: no seguir gastando
                break
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            errores.append(f"{nombre}: {e}")
            continue
        por_ciudad, vistos = {}, set()
        for j in (cuerpo.get("data") or {}).get("jobs", []):
            o = oferta(j)
            cod = ciudad_de(j, idx) if tipo == "industria" else x
            if not o or not cod or o["u"] in vistos:
                continue
            if tipo == "industria":
                o["q"] = x   # si el cargo no deja clasificarla, queda en la industria que se buscó
            vistos.add(o["u"]); por_ciudad.setdefault(cod, []).append(o)
        n = sum(guardar(cod, lista, ahora) for cod, lista in por_ciudad.items())
        hechas.append(nombre); total += n
        print(f"  {tipo:9} {nombre:30} {n:2} ofertas en {len(por_ciudad)} ciudades")

    (DATA / "industrias.json").write_text(json.dumps(resumir_industrias(), ensure_ascii=False, indent=1))
    if not errores:   # con errores se repite el mismo turno mañana
        estado["siguiente"], estado["siguiente_industria"] = sig_c, sig_i
    # correo si el cupo del mes baja de un umbral (una vez por umbral) o si la llave falla
    n = int(restantes) if restantes is not None else None
    nuevos, estado["avisos"] = avisos_pendientes(n, estado.get("avisos", {}))
    if nuevos:
        dias = n // (sum(paginas(v) for v in base["ciudades"].values()) + len(BUSQUEDAS) * PAGINAS_SECTOR) // CORRIDAS_AL_DIA
        cuando = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + int(renueva or 0), timezone.utc).strftime("%Y-%m-%d") if renueva else "sin dato"
        avisar(f"Job Maps CO: quedan {n} consultas de JSearch este mes",
               f"Al ritmo actual ({CORRIDAS_AL_DIA} corridas al día) alcanzan para unos {dias} días. El cupo se renueva el {cuando}.\n"
               + (f"Con menos de {RESERVA} el recolector se detiene solo hasta que se renueve, para no generar cobros extra.\n" if n < RESERVA else "")
               + "Plan actual: Pro, 10.000 consultas al mes.")
    llave_mala = [e for e in errores if "HTTP 401" in e or "HTTP 403" in e]
    if llave_mala and not estado["avisos"].get("llave_mala"):
        avisar("Job Maps CO: JSearch rechazó la llave", "La corrida se detuvo:\n" + "\n".join(llave_mala))
    estado["avisos"]["llave_mala"] = bool(llave_mala)
    estado["registro"] = ([{"fecha": ahora, "busquedas": hechas, "ofertas": total, "errores": errores, "consultas_restantes": restantes}]
                          + estado["registro"])[:60]
    estado_f.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    print(f"{len(hechas)} búsquedas, {total} ofertas, {len(errores)} errores, consultas restantes del mes: {restantes}")
    actualizar_totales()
    if errores:
        print("errores:", *errores, sep="\n  ")
        sys.exit(1 if not hechas else 0)


def prueba():
    for cargo, sector in [
        ("Auxiliar de enfermería", "Salud"), ("Conductor/a de Distribución y Reparto - Licencia C2", "Operaciones y logística"),
        ("Asesor comercial de libranza", "Ventas"), ("Agente de servicio al cliente en español", "Ventas"), ("Bilingual Agent - Weekends OFF!!", "Ventas"),
        ("Practicante de diseño gráfico", "Diseño y Arte"), ("Ingeniero DevOps Junior Azure DevOps", "Desarrollo y Tecnología"),
        ("Guarda de Seguridad", "Operaciones y logística"), ("Gerente general", "Administración y talento humano"), ("Cali Sur", "Otros"),
        ("Ayudante de Almacén", "Ventas"), ("Bodeguero-307903", "Operaciones y logística"), ("Inspector/a SST - La Guajira Rioacha", "Operaciones y logística"),
        ("Operador de Medios Tecnológicos", "Operaciones y logística"), ("Analista de Contabilidad", "Administración y talento humano"),
        ("Analista de gestión humana y sst", "Administración y talento humano"), ("Carniceros (as) con experiencia Acacias Meta", "Hotelería y alimentos"),
        ("Gestor de proyectos de TI", "Desarrollo y Tecnología"), ("Director de Arte", "Diseño y Arte"), ("Copywriter Senior", "Creatividad"),
        ("Planner estratégico", "Planeación"), ("Analista de Trade Marketing", "Trade Marketing"), ("Community Manager", "Digital"),
        ("Productor de eventos BTL", "Eventos"), ("Planeador de medios", "Medios"), ("Account Manager agencia", "Cuentas"),
        ("Editor de video", "Audiovisual"), ("Comunicador social", "Comunicación"), ("Coordinador de mercadeo", "Marketing"),
        ("Ejecutivo de Cuenta Pyme", "Ventas"), ("Docente de matemáticas", "Otros"), ("Supervisor de Operaciones - Prestación de servicios", "Operaciones y logística"),
        ("PRODUCT OWNER - PRODUCTOS Y REQUERIMIENTOS", "Desarrollo y Tecnología"), ("Website Specialist", "Digital")]:
        assert industria(cargo) == sector, (cargo, industria(cargo))
    assert turno(list("abcdefgh"), 5, 6) == (list("fghabc"), 3)
    assert [paginas(n) for n in (29530, 10643, 2390, 1049)] == [5, 3, 2, 1]
    assert turno(list("ab"), 1, 6) == (["b", "a"], 1)
    assert oferta({"job_title": "X", "job_apply_link": "javascript:alert(1)"}) is None
    idx = indice_ciudades([{"c": "41206", "n": "Colombia"}, {"c": "11001", "n": "Bogotá D.C."}, {"c": "13001", "n": "Cartagena"}, {"c": "05615", "n": "Rionegro"}, {"c": "68615", "n": "Rionegro"}], {"05615": 1049})
    assert ciudad_de({"job_location": "Bogotá     •  a través de Computrabajo"}, idx) == "11001"
    assert ciudad_de({"job_location": "Cartagena de Indias, Bolívar"}, idx) == "13001"
    assert ciudad_de({"job_location": "Rionegro, Antioquia"}, idx) == "05615"
    assert ciudad_de({"job_location": "Colombia"}, idx) is None
    assert avisos_pendientes(2500, {}) == ([], {"restantes": 2500, "enviados": []})
    assert avisos_pendientes(1800, {"restantes": 2500, "enviados": []})[0] == [2000]
    assert avisos_pendientes(1700, {"restantes": 1800, "enviados": [2000]})[0] == []
    assert avisos_pendientes(400, {"restantes": 1700, "enviados": [2000]})[0] == [1000, 500]
    assert avisos_pendientes(9900, {"restantes": 250, "enviados": [2000, 1000, 500, RESERVA]}) == ([], {"restantes": 9900, "enviados": []})
    deptos = {"05": "Antioquia", "11": "Bogotá D.C."}
    assert lugar_jooble({"c": "05615", "n": "Rionegro", "d": "05"}, deptos) == "Rionegro, Antioquia"
    assert lugar_jooble({"c": "11001", "n": "Bogotá D.C.", "d": "11"}, deptos) == "Bogotá"
    assert toca_deptos(None, "2026-10-28") and toca_deptos("2026-10-21", "2026-10-28") and not toca_deptos("2026-10-22", "2026-10-28")
    print("prueba ok")


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        prueba()
    elif "--totales" in sys.argv:   # solo los totales por ciudad de Jooble (no gasta JSearch)
        actualizar_totales()
    elif "--resumen" in sys.argv:   # solo regenera acerca.html y llms.txt (no gasta consultas)
        escribir_resumen()
    elif "--industrias" in sys.argv:   # solo reclasifica lo guardado
        (DATA / "industrias.json").write_text(json.dumps(resumir_industrias(), ensure_ascii=False, indent=1))
    else:
        main()
