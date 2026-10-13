"""Recolector: trae ofertas recientes por ciudad desde JSearch (RapidAPI, agrega Google for Jobs) y las guarda en data/.

Plan gratis de JSearch: 200 consultas al mes → 3 corridas al día de 2 consultas (≈186 al mes):
- 1 búsqueda por industria en todo el país (por turnos: cada industria cada ~5 días); cada oferta se asigna a su
  ciudad por el lugar que trae ("Bogotá • a través de Computrabajo").
- 1 búsqueda general por ciudad (por turnos, las de más ofertas primero: cada ciudad cada ~15 días).
Cada consulta trae hasta 10 ofertas con enlace directo al portal. Cada ciudad guarda sus 30 más recientes (máx. 30 días).

Escribe:
- data/ofertas/<divipola>.json  ofertas de cada ciudad (las nuevas se suman a las anteriores)
- data/industrias.json          conteo por industria sobre todas las ofertas guardadas
- data/recoleccion.json         turno siguiente y registro de las últimas corridas

Uso: python3 -I scripts/recolectar.py          (llave en RAPIDAPI_KEY o en .env)
     python3 -I scripts/recolectar.py --prueba (solo verifica la clasificación y la rotación, sin gastar consultas)
     python3 -I scripts/recolectar.py --industrias (reclasifica lo guardado, sin gastar consultas)
"""
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
POR_CORRIDA = 2        # plan gratis: 200 consultas/mes → 3 corridas al día de 2
POR_INDUSTRIA = 1      # de esas, búsquedas por industria en todo el país; el resto, por ciudad
MAX_POR_CIUDAD = 30
VIGENCIA_DIAS = 30
API = "https://jsearch.p.rapidapi.com/search-v2"

# Primera regla que coincide con el cargo gana; el orden importa ("auxiliar de enfermería" antes que "auxiliar").
INDUSTRIAS = [
    ("Prácticas y aprendices", ["practicante", "aprendiz", "pasante", "etapa productiva"]),
    ("Salud", ["enfermer", "medic", "odontolog", "farmac", "regente", "fisioterap", "bacteriolog", "salud", "clinic", "terapeuta", "psicolog"]),
    ("Tecnología", ["desarrollador", "developer", "software", "devops", "programador", "sistemas", "datos", "data ", "qa ", "tester", "frontend", "backend", "full stack", "soporte tecnico", "cloud", "ciberseguridad", "it "]),
    ("Servicio al cliente", ["call center", "contact center", "servicio al cliente", "atencion al cliente", "agente", "agent ", "teleoperador", "bilingue", "bilingual", "customer"]),
    ("Marketing y comunicación", ["marketing", "mercadeo", "contenido", "comunicacion", "publicidad", "disenador", "community", "brand"]),
    ("Ventas y comercial", ["ventas", "vendedor", "comercial", "asesor", "telemercad", "mercaderista", "impulsador", "promotor", "autoventa", "preventa", "cajer", "sales", "tienda", "almacen "]),
    ("Logística y transporte", ["conductor", "bodega", "logistic", "almacenista", "despachador", "montacarg", "mensajer", "domiciliari", "inventario", "transport", "distribucion", "reparto", "picking"]),
    ("Producción y operarios", ["operari", "operativo", "oficios varios", "produccion", "planta", "ensambl", "manufactura", "empacador", "maquina"]),
    ("Administración y finanzas", ["contador", "contable", "administrativ", "financier", "cartera", "cobranza", "cobro", "tesorer", "facturacion", "credito", "nomina", "auditor", "analista juridico", "abogad", "recepcionista", "secretari", "archivo", "documental", "office", "payroll", "invoic", "gerente", "coordinador"]),
    ("Recursos humanos", ["talento humano", "recursos humanos", "seleccion", "reclutador", "human resources", "hr "]),
    ("Construcción y mantenimiento", ["obra", "construccion", "civil", "electricista", "mantenimiento", "tecnico", "soldador", "mecanic", "ingenier"]),
    ("Hotelería y alimentos", ["cocin", "mesero", "chef", "panader", "barista", "hotel", "restaurante", "alimentos", "steward"]),
    ("Seguridad y aseo", ["guarda", "vigilante", "seguridad", "aseo", "servicios generales", "limpieza", "escolta"]),
    ("Educación", ["docente", "profesor", "maestr", "tutor", "instructor", "educacion"]),
]


# Búsqueda por industria (todo Colombia), en orden de turno
BUSQUEDAS = {
    "Tecnología": "desarrollador software", "Marketing y comunicación": "marketing publicidad", "Salud": "enfermería salud",
    "Administración y finanzas": "contador administrativo", "Recursos humanos": "recursos humanos",
    "Construcción y mantenimiento": "ingeniero construcción mantenimiento", "Educación": "docente", "Hotelería y alimentos": "cocinero mesero",
    "Logística y transporte": "logística bodega conductor", "Servicio al cliente": "servicio al cliente call center",
    "Ventas y comercial": "asesor comercial ventas", "Producción y operarios": "operario producción",
    "Seguridad y aseo": "guarda de seguridad aseo", "Prácticas y aprendices": "practicante aprendiz",
}


def simple(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return " " + "".join(c for c in s if unicodedata.category(c) != "Mn") + " "


def industria(cargo):
    t = simple(cargo)
    return next((nombre for nombre, claves in INDUSTRIAS if any(k in t for k in claves)), "Otros")


def turno(codigos, siguiente, n=POR_CORRIDA):
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


def llave():
    if os.environ.get("RAPIDAPI_KEY"):
        return os.environ["RAPIDAPI_KEY"].strip()
    env = RAIZ / ".env"
    for linea in env.read_text().splitlines() if env.exists() else []:
        k, _, v = linea.partition("=")
        if k.strip() == "RAPIDAPI_KEY":
            return v.strip()
    sys.exit("Falta RAPIDAPI_KEY (variable de entorno o .env)")


def consultar(clave, texto):
    q = urllib.parse.urlencode({"query": texto, "country": "co", "num_pages": 1, "date_posted": "month"})
    req = urllib.request.Request(f"{API}?{q}", headers={"x-rapidapi-key": clave, "x-rapidapi-host": "jsearch.p.rapidapi.com"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r), r.headers.get("x-ratelimit-requests-remaining")


def resumir_industrias():
    """Reclasifica lo guardado (por si cambiaron las reglas) y cuenta por industria."""
    conteo, muestra, ciudades, por_ciudad = {}, 0, 0, {}
    for f in (DATA / "ofertas").glob("*.json"):
        d = json.loads(f.read_text())
        ofertas = d["ofertas"]
        for o in ofertas:
            o["i"] = industria(o["t"])
            if o["i"] == "Otros" and o.get("q"):
                o["i"] = o["q"]
            cod = por_ciudad.setdefault(o["i"], {})
            cod[f.stem] = cod.get(f.stem, 0) + 1
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        ciudades += bool(ofertas)
        for o in ofertas:
            conteo[o["i"]] = conteo.get(o["i"], 0) + 1
            muestra += 1
    todas = [n for n, _ in INDUSTRIAS] + ["Otros"]
    orden = {n: conteo.get(n, 0) for n in sorted(todas, key=lambda n: (-conteo.get(n, 0), n == "Otros"))}
    return {"muestra": muestra, "ciudades": ciudades, "industrias": orden, "por_ciudad": por_ciudad}


def main():
    clave = llave()
    base = json.loads((DATA / "ofertas.json").read_text())
    muni = json.loads((DATA / "municipios.json").read_text())
    por_cod = {m["c"]: m for m in muni["municipios"]}
    codigos = sorted(base["ciudades"], key=lambda c: -base["ciudades"][c])
    estado_f = DATA / "recoleccion.json"
    estado = json.loads(estado_f.read_text()) if estado_f.exists() else {"siguiente": 0, "registro": []}
    ciudades_hoy, sig_c = turno(codigos, estado.get("siguiente", 0), POR_CORRIDA - POR_INDUSTRIA)
    industrias_hoy, sig_i = turno(list(BUSQUEDAS), estado.get("siguiente_industria", 0), POR_INDUSTRIA)
    idx = indice_ciudades(muni["municipios"], base["ciudades"])

    (DATA / "ofertas").mkdir(exist_ok=True)
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    hechas, errores, restantes, total = [], [], None, 0
    for tipo, x in [("industria", i) for i in industrias_hoy] + [("ciudad", c) for c in ciudades_hoy]:
        nombre = x if tipo == "industria" else por_cod[x]["n"]
        texto = f"{BUSQUEDAS[x]} en Colombia" if tipo == "industria" else f"empleos en {nombre}, {muni['deptos'][por_cod[x]['d']]}"
        try:
            cuerpo, restantes = consultar(clave, texto)
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
    estado["registro"] = ([{"fecha": ahora, "busquedas": hechas, "ofertas": total, "errores": errores, "consultas_restantes": restantes}]
                          + estado["registro"])[:60]
    estado_f.write_text(json.dumps(estado, ensure_ascii=False, indent=1))
    print(f"{len(hechas)} búsquedas, {total} ofertas, {len(errores)} errores, consultas restantes del mes: {restantes}")
    if errores:
        print("errores:", *errores, sep="\n  ")
        sys.exit(1 if not hechas else 0)


def prueba():
    assert industria("Auxiliar de enfermería") == "Salud"
    assert industria("Conductor/a de Distribución y Reparto - Licencia C2") == "Logística y transporte"
    assert industria("Asesor comercial de libranza") == "Ventas y comercial"
    assert industria("Agente de servicio al cliente en español") == "Servicio al cliente"
    assert industria("Practicante de ingeniería industrial") == "Prácticas y aprendices"
    assert industria("Ingeniero DevOps Junior Azure DevOps") == "Tecnología"
    assert industria("Guarda de Seguridad") == "Seguridad y aseo"
    assert industria("Bilingual Agent - Weekends OFF!!") == "Servicio al cliente"
    assert industria("Ayudante de Almacén") == "Ventas y comercial"
    assert industria("Cali Sur") == "Otros"
    assert turno(list("abcdefgh"), 5, 6) == (list("fghabc"), 3)
    assert turno(list("ab"), 1, 6) == (["b", "a"], 1)
    assert oferta({"job_title": "X", "job_apply_link": "javascript:alert(1)"}) is None
    idx = indice_ciudades([{"c": "41206", "n": "Colombia"}, {"c": "11001", "n": "Bogotá D.C."}, {"c": "13001", "n": "Cartagena"}, {"c": "05615", "n": "Rionegro"}, {"c": "68615", "n": "Rionegro"}], {"05615": 1049})
    assert ciudad_de({"job_location": "Bogotá     •  a través de Computrabajo"}, idx) == "11001"
    assert ciudad_de({"job_location": "Cartagena de Indias, Bolívar"}, idx) == "13001"
    assert ciudad_de({"job_location": "Rionegro, Antioquia"}, idx) == "05615"
    assert ciudad_de({"job_location": "Colombia"}, idx) is None
    print("prueba ok")


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        prueba()
    elif "--industrias" in sys.argv:   # solo reclasifica lo guardado
        (DATA / "industrias.json").write_text(json.dumps(resumir_industrias(), ensure_ascii=False, indent=1))
    else:
        main()
