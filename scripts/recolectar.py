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
from datetime import datetime, timezone
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
    """Variable de entorno (GitHub Actions) o línea del .env local."""
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
    cuerpo = json.dumps({"from": config("AVISO_REMITENTE") or "Mapa del Empleo <onboarding@resend.dev>",
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
        avisar(f"Mapa del Empleo: quedan {n} consultas de JSearch este mes",
               f"Al ritmo actual ({CORRIDAS_AL_DIA} corridas al día) alcanzan para unos {dias} días. El cupo se renueva el {cuando}.\n"
               + (f"Con menos de {RESERVA} el recolector se detiene solo hasta que se renueve, para no generar cobros extra.\n" if n < RESERVA else "")
               + "Plan actual: Pro, 10.000 consultas al mes.")
    llave_mala = [e for e in errores if "HTTP 401" in e or "HTTP 403" in e]
    if llave_mala and not estado["avisos"].get("llave_mala"):
        avisar("Mapa del Empleo: JSearch rechazó la llave", "La corrida se detuvo:\n" + "\n".join(llave_mala))
    estado["avisos"]["llave_mala"] = bool(llave_mala)
    estado["registro"] = ([{"fecha": ahora, "busquedas": hechas, "ofertas": total, "errores": errores, "consultas_restantes": restantes}]
                          + estado["registro"])[:60]
    estado_f.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    print(f"{len(hechas)} búsquedas, {total} ofertas, {len(errores)} errores, consultas restantes del mes: {restantes}")
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
    print("prueba ok")


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        prueba()
    elif "--industrias" in sys.argv:   # solo reclasifica lo guardado
        (DATA / "industrias.json").write_text(json.dumps(resumir_industrias(), ensure_ascii=False, indent=1))
    else:
        main()
