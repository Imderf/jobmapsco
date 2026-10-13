"""Genera data/municipios.json, data/departamentos.geo.json y data/ofertas.json desde data/raw/.

Fuentes crudas:
- raw/divipola.json: MinSalud Divipola (datos.gov.co pqwj-3fi4), 1.122 municipios con lat/lon
- raw/departamentos.geo.json: polígonos de los 33 departamentos (gist john-guerra, base DANE)

Uso: python3 -I scripts/preparar_datos.py
"""
import json
import unicodedata
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

DEPTOS = {
    "05": "Antioquia", "08": "Atlántico", "11": "Bogotá D.C.", "13": "Bolívar", "15": "Boyacá",
    "17": "Caldas", "18": "Caquetá", "19": "Cauca", "20": "Cesar", "23": "Córdoba",
    "25": "Cundinamarca", "27": "Chocó", "41": "Huila", "44": "La Guajira", "47": "Magdalena",
    "50": "Meta", "52": "Nariño", "54": "Norte de Santander", "63": "Quindío", "66": "Risaralda",
    "68": "Santander", "70": "Sucre", "73": "Tolima", "76": "Valle del Cauca", "81": "Arauca",
    "85": "Casanare", "86": "Putumayo", "88": "San Andrés y Providencia", "91": "Amazonas",
    "94": "Guainía", "95": "Guaviare", "97": "Vaupés", "99": "Vichada",
}

# El centroide de Bogotá cae en Sumapaz (zona rural); la columna va en la ciudad.
CENTRO_URBANO = {"11001": (4.65, -74.10)}

# Línea base manual: Computrabajo, 2026-10-13 (encabezado de cada página de ciudad).
# Se reemplaza en el ciclo 3 por el recolector con Jooble + JSearch.
LINEA_BASE = [
    ("Bogotá", "11", 29530), ("Medellín", "05", 10643), ("Cali", "76", 5363),
    ("Barranquilla", "08", 2390), ("Bucaramanga", "68", 1888), ("Pereira", "66", 1413),
    ("Cartagena", "13", 1189), ("Funza", "25", 1179), ("Rionegro", "05", 1049),
    ("Mosquera", "25", 861), ("Manizales", "17", 839), ("Yumbo", "76", 705),
    ("Villavicencio", "50", 682), ("Ibagué", "73", 631), ("Cúcuta", "54", 521),
    ("Neiva", "41", 447), ("Santa Marta", "47", 430), ("Armenia", "63", 427),
    ("Pasto", "52", 304), ("Montería", "23", 256), ("Tunja", "15", 236),
    ("Popayán", "19", 233), ("Girón", "68", 224), ("Valledupar", "20", 222),
    ("Dosquebradas", "66", 187), ("Yopal", "85", 165), ("Sincelejo", "70", 121),
    ("Pitalito", "41", 114), ("Riohacha", "44", 114), ("Duitama", "15", 111),
    ("Malambo", "08", 105), ("Ipiales", "52", 67), ("La Dorada", "17", 66),
    ("Aguachica", "20", 48), ("Acacías", "50", 46), ("Melgar", "73", 45),
    ("Santander de Quilichao", "19", 44), ("Turbaco", "13", 29), ("Cereté", "23", 28),
    ("Ciénaga", "47", 25), ("Fonseca", "44", 20), ("Ocaña", "54", 20),
    ("Calarcá", "63", 15), ("Villanueva", "85", 12), ("Corozal", "70", 7),
]
# Totales por departamento del mismo corte (incluyen municipios que no están en LINEA_BASE).
LINEA_BASE_DEPTOS = {
    "11": 29531, "05": 15720, "76": 7791, "25": 6022, "68": 2808, "08": 2690, "66": 1654,
    "13": 1299, "17": 1040, "73": 872, "50": 840, "41": 629, "54": 594, "15": 551, "47": 491,
    "63": 490, "52": 451, "19": 386, "20": 339, "23": 336, "85": 215, "44": 188, "70": 148,
}


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn" and (c.isalnum() or c == " ")).strip()


def buscar(municipios, nombre, depto):
    """Código DIVIPOLA por nombre dentro del departamento: exacto primero, luego contenido."""
    candidatos = [m for m in municipios if m["d"] == depto]
    n = norm(nombre)
    exactos = [m for m in candidatos if norm(m["n"]) == n]
    if exactos:
        return exactos[0]["c"]
    parciales = [m for m in candidatos if n in norm(m["n"]).split(" de ")[-1] or norm(m["n"]).startswith(n) or norm(m["n"]).endswith(n)]
    assert len(parciales) == 1, f"{nombre} ({depto}): {[m['n'] for m in parciales]}"
    return parciales[0]["c"]


def redondear(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 3), round(coords[1], 3)]
    return [redondear(c) for c in coords]


def dentro(pt, r):
    x, y, c = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(r, r[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def puntos(colombia):
    """Globo de puntos para la entrada: tierra cada 1,2° (sin Colombia) y Colombia cada 0,4°, en [lon, lat, ...]."""
    import math
    tierra = []
    for f in json.load(open(DATA / "raw/tierra-110m.geo.json", encoding="utf-8"))["features"]:
        r = f["geometry"]["coordinates"][0]
        xs, ys = [p[0] for p in r], [p[1] for p in r]
        tierra.append((min(xs), min(ys), max(xs), max(ys), r))
    en = lambda pt, anillos: any(dentro(pt, a) for a in anillos)
    en_tierra = lambda pt: any(x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1 and dentro(pt, r) for x0, y0, x1, y1, r in tierra)
    def rejilla(paso, lat0, lat1, lon0, lon1, cond):
        out, lat = [], lat0
        while lat <= lat1:
            dlon = paso / max(math.cos(math.radians(lat)), .2)   # mismo espacio entre puntos a cualquier latitud
            lon = lon0
            while lon <= lon1:
                if cond((lon, lat)): out += [round(lon, 2), round(lat, 2)]
                lon += dlon
            lat += paso
        return out
    # misma rejilla para todo el mundo: Colombia solo cambia de color (va aparte para pintarla azul)
    todos = rejilla(1.2, -56, 78, -180, 180, lambda p: en(p, colombia) or en_tierra(p))
    mundo, co = [], []
    for i in range(0, len(todos), 2):
        (co if en((todos[i], todos[i + 1]), colombia) else mundo).extend(todos[i:i + 2])
    print(f"puntos: {len(mundo) // 2} de tierra, {len(co) // 2} de Colombia")
    return {"t": mundo, "co": co}


def mascara(geo):
    """Mundo con Colombia recortada: los bordes que usa un solo departamento forman el contorno del país."""
    from collections import Counter, defaultdict
    usos = Counter()
    for f in geo["features"]:
        g = f["geometry"]
        for r in (g["coordinates"] if g["type"] == "Polygon" else [r for p in g["coordinates"] for r in p]):
            usos.update(frozenset((tuple(a), tuple(b))) for a, b in zip(r, r[1:]) if a != b)
    vecinos = defaultdict(set)
    for s, n in usos.items():
        if n == 1:
            a, b = tuple(s)
            vecinos[a].add(b); vecinos[b].add(a)
    anillos = []
    while vecinos:
        inicio = p = next(iter(vecinos)); r = [inicio]
        while vecinos.get(p):
            q = vecinos[p].pop(); vecinos[q].discard(p)
            r.append(q); p = q
            if q == inicio: break
        for k in [k for k in vecinos if not vecinos[k]]: del vecinos[k]
        if len(r) > 3 and r[0] == r[-1]: anillos.append(r)
    area = lambda r: sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:])) / 2
    anillos.sort(key=lambda r: -abs(area(r)))
    # quedan el contorno principal y las islas (San Andrés); las astillas internas de bordes que no calzan se descartan
    huecos = [anillos[0]] + [r for r in anillos[1:] if not dentro(r[0], anillos[0])]
    huecos = [r if area(r) < 0 else r[::-1] for r in huecos]              # huecos en sentido horario
    mundo = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]  # exterior antihorario
    assert len(huecos) >= 1 and abs(area(huecos[0])) > 50, "el contorno de Colombia no cerró"
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [mundo] + [[list(p) for p in r] for r in huecos]}}]}


def main():
    municipios = []
    for r in json.load(open(DATA / "raw/divipola.json", encoding="utf-8")):
        cod = r["idmupio"].zfill(5)  # la fuente pierde el cero inicial (5001 → 05001)
        lat, lon = CENTRO_URBANO.get(cod, (float(r["mpiolatitud"]), float(r["mpiolongitud"])))
        municipios.append({"c": cod, "n": r["nommpio"], "d": r["iddepto"], "lat": round(lat, 4), "lon": round(lon, 4)})
    assert len(municipios) == 1122, len(municipios)
    assert all(m["d"] in DEPTOS for m in municipios)

    geo = json.load(open(DATA / "raw/departamentos.geo.json", encoding="utf-8"))
    for f in geo["features"]:
        cod = f["properties"]["DPTO"]
        f["properties"] = {"c": cod, "n": DEPTOS[cod]}
        f["geometry"]["coordinates"] = redondear(f["geometry"]["coordinates"])

    m = mascara(geo)
    json.dump(m, open(DATA / "mascara.geo.json", "w", encoding="utf-8"), separators=(",", ":"))
    json.dump(puntos(m["features"][0]["geometry"]["coordinates"][1:]), open(DATA / "puntos.json", "w"), separators=(",", ":"))

    ofertas = {buscar(municipios, n, d): v for n, d, v in LINEA_BASE}
    assert len(ofertas) == len(LINEA_BASE), "dos ciudades cayeron en el mismo código"

    json.dump({"deptos": DEPTOS, "municipios": municipios}, open(DATA / "municipios.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(geo, open(DATA / "departamentos.geo.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({
        "actualizado": "2026-10-13",
        "fuente": "Computrabajo (línea base manual)",
        "ciudades": ofertas,
        "deptos": LINEA_BASE_DEPTOS,
    }, open(DATA / "ofertas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(municipios)} municipios, {len(geo['features'])} departamentos, {len(ofertas)} ciudades con ofertas")
    for n, d, _ in LINEA_BASE:
        c = buscar(municipios, n, d)
        print(f"  {n:24} -> {c} {next(m['n'] for m in municipios if m['c'] == c)}")


if __name__ == "__main__":
    main()
