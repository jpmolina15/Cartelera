"""Cinemark Caballito y Hoyts Abasto.

Las dos salas las opera Cinemark en Argentina y comparten sitio.
cinemarkhoyts.com.ar redirige a cinemark.com.ar; Hoyts Abasto es el slug 'abasto'.

Los horarios NO se piden por API: vienen en un bloque JSON-LD que el propio
sitio renderiza del lado del servidor en /cartelera/<slug>. La ficha de cada
película (duración, clasificación, género, sinopsis, elenco, idiomas) sale del
payload de Next.js en /pelicula/<slug>.
"""
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor

from ..http import get

BASE = "https://www.cinemark.com.ar"
SALAS = {"cinemark": "caballito", "hoyts": "abasto"}


def _jsonld(pagina):
    """Extrae el bloque MovieTheater por conteo de llaves.

    No sirve una regex sobre <script type=...>: el literal 'application/ld+json'
    aparece antes dentro de strings de JS y la captura arranca en el lugar
    equivocado.
    """
    s = html.unescape(pagina)
    i = s.find('{"@context":"https://schema.org","@type":"MovieTheater"')
    if i < 0:
        return None
    prof = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            prof += 1
        elif s[j] == "}":
            prof -= 1
            if prof == 0:
                try:
                    return json.loads(s[i:j + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _payload(pagina):
    """Concatena los chunks de self.__next_f.push del App Router de Next.js."""
    buf = ""
    for c in re.findall(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', pagina, re.S):
        try:
            buf += json.loads(c)
        except json.JSONDecodeError:
            pass
    return buf


def funciones(slug):
    """{fecha: {titulo: {'horas': set, 'formatos': set, 'slug_pelicula': str}}}"""
    d = _jsonld(get(f"{BASE}/cartelera/{slug}"))
    if not d:
        return {}
    out = {}
    for e in d.get("event", []):
        # startDate viene malformado: '2026-08-29T13:10:00.000Z-03:00'.
        # La 'Z' es un bug del sitio; el offset -03:00 indica que la hora de
        # pared ya es local de Buenos Aires, así que se toma tal cual.
        m = re.match(r"(\d{4}-\d\d-\d\d)T(\d\d:\d\d)", e.get("startDate", ""))
        if not m:
            continue
        dia, hora = m.groups()
        obra = e.get("workPresented") or {}
        titulo = obra.get("name")
        if not titulo:
            continue
        rec = out.setdefault(dia, {}).setdefault(
            titulo, {"horas": set(), "formatos": set(), "slug_pelicula": None})
        rec["horas"].add(hora)
        rec["formatos"].add(e.get("videoFormat") or "")
        url = (e.get("offers") or {}).get("url", "")
        sm = re.search(r"/pelicula/([a-z0-9\-]+)", url)
        if sm:
            rec["slug_pelicula"] = sm.group(1)
    return out


def _ficha(slug_pelicula):
    buf = _payload(get(f"{BASE}/pelicula/{slug_pelicula}"))
    if not buf:
        return None

    def uno(patron):
        m = re.search(patron, buf)
        return m.group(1) if m else None

    generos = re.search(r'"genres":\[(.*?)\]', buf)
    idiomas = re.search(r'"languages":\[(.*?)\]', buf)
    equipo = re.search(r'"actorsAndCrew":\[(.*?)\]', buf, re.S)
    sinopsis = re.search(r'"caption":"(.*?)","', buf, re.S)
    return {
        "duracion": uno(r'"duration":"([^"]{2,12})"'),
        "clasificacion": uno(r'"category":"([^"]{1,12})"'),
        "estreno": uno(r'"releaseDate":"([^"]{4,30})"'),
        "generos": re.findall(r'"([^"]+)"', generos.group(1)) if generos else [],
        # 'languages' lista los idiomas de la película, no de cada función.
        "idiomas": re.findall(r'"value":"([^"]+)"', idiomas.group(1)) if idiomas else [],
        "sinopsis": sinopsis.group(1).replace("\\n", " ").strip() if sinopsis else None,
        "equipo": [{"nombre": n.lstrip("* ").strip(), "rol": r}
                   for n, r in re.findall(
                       r'\{"name":"([^"]+)","role":"([^"]+)"\}', equipo.group(1))]
        if equipo else [],
    }


def fichas(slugs, workers=6):
    slugs = sorted({s for s in slugs if s})
    with ThreadPoolExecutor(max_workers=workers) as ex:
        pares = zip(slugs, ex.map(_ficha, slugs))
    return {s: f for s, f in pares if f}
