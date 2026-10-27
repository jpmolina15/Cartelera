"""Multiplex (multiplex.com.ar): Belgrano y Lavalle.

La home embebe la programación de todos los complejos (~55 días) como JSON en el
atributo `data-funciones='[...]'` de cada `funcion-item` (uno por película):

    {"complejo":"182","dia":"10.26.2026","dia_real":"10.26.2026","hora":"21:50",
     "formato":"2D","idioma":"Subtitulada","pelicula_id":"195","id":"6887"}

- El complejo se identifica por la etiqueta de `<input name="complejo">`
  («Multiplex Belgrano» = 182, «Multiplex Lavalle» = 184), no por el orden.
- El título sale del `<h4>` del `funcion-item` (no hace falta /wp-json).
- `dia` es la «noche de cine» (las 00:xx cuentan en la noche anterior); `dia_real`
  no se usa.
- Una misma función puede repetirse: se deduplica por `id`.
- `fmt` queda crudo («2D XTREMO», «4D(3D) INFINITY VISION»...), salvo el 2D común
  que queda vacío; `normFmt` de la plantilla lo lleva a su base. Idioma:
  Español -> D, Subtitulada -> S.
"""
import html
import json
import re

from ..http import get

URL = "https://multiplex.com.ar/"
_MEMO = {}  # url -> pagina parseada: las dos salas salen de la misma home de 1,4 MB


def _iso(mdy):
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})$", mdy or "")
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def _lang(i):
    i = (i or "").strip().lower()
    return "S" if i.startswith("subt") else ("D" if i.startswith(("espa", "cast")) else "")


def parsear(pagina):
    """{'complejos': {etiqueta: id}, 'funciones': [{complejo, dia, h, fmt, lang, titulo, id}]}"""
    complejos = {}
    for cid, nombre in re.findall(r'name="complejo"\s+value="(\d+)"[^>]*>\s*([^<]*?)\s*<', pagina):
        complejos[html.unescape(nombre).strip()] = cid
    funciones, vistos = [], set()
    for trozo in re.split(r"<div class='funcion-item", pagina)[1:]:
        m = re.match(r"[^>]*?data-funciones='(.*?)'>", trozo, re.S)
        if not m:
            continue
        try:
            lista = json.loads(html.unescape(m.group(1)))
        except json.JSONDecodeError:
            continue
        t = re.search(r"<h4[^>]*>(.*?)</h4>", trozo, re.S)
        titulo = html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip() if t else ""
        if not titulo:
            continue
        for f in lista:
            fid, dia = f.get("id"), _iso(f.get("dia"))
            if fid in vistos or not dia or not re.match(r"\d{1,2}:\d{2}$", f.get("hora") or ""):
                continue
            vistos.add(fid)
            fmt = re.sub(r"\s+", " ", f.get("formato") or "").strip().upper()
            funciones.append({"complejo": str(f.get("complejo")), "dia": dia,
                              "h": f["hora"].zfill(5), "fmt": "" if fmt == "2D" else fmt,
                              "lang": _lang(f.get("idioma")), "titulo": titulo, "id": fid})
    return {"complejos": complejos, "funciones": funciones}


def cartelera(nombre, url=URL):
    """Funciones del complejo cuya etiqueta es `nombre`. Levanta ValueError si la página
    no trae complejos (sin red o desafío de Cloudflare) o no está esa etiqueta."""
    if url not in _MEMO:
        _MEMO[url] = parsear(get(url))
    p = _MEMO[url]
    if not p["complejos"]:
        raise ValueError("multiplex: la página no trae complejos (sin red o desafío de bots)")
    if nombre not in p["complejos"]:
        raise ValueError(f"multiplex: no hay un complejo llamado {nombre!r} (hay {sorted(p['complejos'])})")
    cid = p["complejos"][nombre]
    return [f for f in p["funciones"] if f["complejo"] == cid]
