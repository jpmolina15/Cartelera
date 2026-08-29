"""Atlas Caballito (complejo 191).

Atlas expone una API interna sin autenticación. El flujo por película es:
  GetComplejosParaPelicula -> ¿está en Caballito?
  GetFechasDisponibles     -> qué días tiene función
  GetCacheFuncionesComplejoPeliculaFecha -> horarios de ese día
  GetDetallePelicula       -> duración, sinopsis, clasificación
  /Peliculas?codPelicula=  -> elenco y directores (sólo en el HTML)

Es la única de las cuatro fuentes que informa doblada/subtitulada por función.
"""
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor

from ..http import get, quote

BASE = "https://www.atlascines.com"
CABALLITO = 191


def _api(path):
    txt = get(BASE + path)
    if not txt:
        return None
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


def _grupos(r):
    """GetCache... devuelve una lista; FiltrarFunciones... devuelve un dict.

    Tratar sólo el caso dict hace que la lista se descarte en silencio.
    """
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("funciones", [])
    return []


def _bloque(texto, etiqueta, siguiente):
    m = re.search(rf"\n\s*{etiqueta}\s*\n(.*?)\n\s*(?:{siguiente})\s*\n", texto, re.S)
    if not m:
        return []
    return [x.strip() for x in m.group(1).split("\n") if x.strip()][:6]


def _elenco(cod):
    pagina = get(f"{BASE}/Peliculas?codPelicula={cod}&codComplejo={CABALLITO}")
    limpio = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", pagina)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", limpio))
    t = re.sub(r"[ \t]+", "  ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    genero = re.search(r"\n\s*Género\s*\n\s*([^\n]+)", t)
    return {
        "actores": _bloque(t, "Actores", "Directores|Duración"),
        "directores": _bloque(t, "Directores", "Duración|Clasificación"),
        "genero": genero.group(1).strip() if genero else None,
    }


def _pelicula(cod):
    comp = _api(f"/Peliculas/GetComplejosParaPelicula?codPelicula={cod}")
    if not comp or not any(c.get("codComplejo") == CABALLITO for c in comp):
        return None

    funciones = {}
    for f in _api(f"/Peliculas/GetFechasDisponibles?codComplejo={CABALLITO}&codPelicula={cod}") or []:
        r = _api(f"/Peliculas/GetCacheFuncionesComplejoPeliculaFecha"
                 f"?complejoId={CABALLITO}&codPelicula={cod}&fecha={quote(f)}")
        vistas = {}
        for g in _grupos(r):
            for fn in g.get("funciones", []):
                vistas[fn.get("horaComienzoOriginal")] = {
                    "hora": fn.get("horaComienzoOriginal"),
                    "tec": g.get("tecnologiaNombre"),
                    "doblada": bool(fn.get("doblada")),
                    "subtitulada": bool(fn.get("subtitulada")),
                }
        if vistas:
            funciones[f[:10]] = [vistas[h] for h in sorted(vistas)]

    if not funciones:
        return None

    det = _api(f"/Peliculas/GetDetallePelicula?codPelicula={cod}") or {}
    extra = _elenco(cod)
    return {
        "cod": cod,
        # Ojo: 'titulo' viene truncado a ~30 caracteres en el listado.
        "titulo": det.get("titulo"),
        "original": det.get("tituloOriginal"),
        "duracion": det.get("duracion"),
        "clasificacion": det.get("clasificacion"),
        "sinopsis": det.get("sinopsis"),
        "estreno": det.get("estreno"),
        "genero": extra["genero"] or det.get("genero"),
        "actores": extra["actores"],
        "directores": extra["directores"],
        "funciones": funciones,
    }


def cartelera(workers=8):
    pagina = get(f"{BASE}/Cartelera")
    # Los data-cod menores a 400 son complejos (191-198), no películas.
    codigos = sorted({int(c) for c in re.findall(r'data-cod[a-z]*="(\d+)"', pagina, re.I)
                      if int(c) > 400})
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = [r for r in ex.map(_pelicula, codigos) if r]
    res.sort(key=lambda x: x["titulo"] or "")
    return res
