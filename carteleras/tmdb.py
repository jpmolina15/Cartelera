"""TMDb por la API oficial v3: tmdb_id, títulos, puntaje y director.

Credencial: el API Read Access Token (v4) en `Authorization: Bearer`, leído de
la variable de entorno TMDB_TOKEN. Nunca va en URLs, logs, HTML, JSON ni caché.
Este módulo no imprime URLs ni headers y no lee más variable que TMDB_TOKEN.

Pedidos por película nueva: 2 (un `search/movie` y un `movie/{id}` con
credits+translations). Excepción: con director del cine y más de un candidato
de título exacto (homónimas) se piden hasta 3 fichas para desempatar. Con la
película ya en caché (`data/tmdb-cache.json`) es 1 solo pedido (la ficha, para
traer el puntaje actualizado).

Regla de oro: sin match es mejor que match equivocado. No hay match por
subcadena: el título del cine (o el original) tiene que ser IGUAL, normalizado,
al título es-AR u original del search, o a cualquier traducción es-* o título
alternativo AR/MX/ES de la ficha (respaldo: fichas de los 3 primeros no exactos).
Sin director verificado se exige año ±1 contra el del cine; sólo los reestrenos
(consulta con el sufijo «N° ANIVERSARIO» sacado) aceptan el único exacto sin año,
o el que cae en (año del cine - N).
"""
import datetime
import json
import os
import pathlib
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import http
from .scores import mismo_director, norm

BASE = "https://api.themoviedb.org/3"
MIN_VOTOS = 20
RAIZ = pathlib.Path(__file__).resolve().parent.parent
CACHE_RUTA = RAIZ / "data" / "tmdb-cache.json"
EVENTO_GENERO = re.compile(r"recital|musical", re.I)
EVENTO_TITULO = re.compile(r"\b(WORLD TOUR|LIVE|CONCERT)\b", re.I)


# ---------------------------------------------------------------- cliente

class Cliente:
    """Pide JSON a la API. `pedir(ruta, params) -> (status, dict|None)`.

    Los tests reemplazan `pedir` por una función con respuestas guardadas.
    """

    def __init__(self, token, pedir=None):
        self.token = token
        self.invalido = False  # un 401 apaga TMDb por el resto de la corrida
        self.pedidos = 0
        if pedir is not None:
            self._pedir = pedir

    def pedir(self, ruta, params):
        if self.invalido:
            return 401, None
        self.pedidos += 1
        status, data = self._pedir(ruta, params)
        if status == 401:
            self.invalido = True
        return status, data

    def _pedir(self, ruta, params):
        url = f"{BASE}{ruta}?{urllib.parse.urlencode(params)}"
        status, cuerpo = http.get(
            url, timeout=20, retries=2, con_status=True,
            headers={"Authorization": f"Bearer {self.token}",
                     "Accept": "application/json"})
        try:
            return status, json.loads(cuerpo) if cuerpo else None
        except ValueError:
            return status, None


# ---------------------------------------------------------------- caché

def cargar_cache(ruta=CACHE_RUTA):
    try:
        d = json.loads(pathlib.Path(ruta).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_cache(cache, ruta=CACHE_RUTA):
    """Escribe sólo si cambió (evita ruido en git). Devuelve True si escribió."""
    ruta = pathlib.Path(ruta)
    nuevo = json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    try:
        if ruta.read_text(encoding="utf-8") == nuevo:
            return False
    except OSError:
        pass
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(nuevo, encoding="utf-8")
    return True


def _s(x):
    return "" if x is None else str(x).strip()


def entrada_vigente(e, f):
    """La entrada de caché sirve si es manual o si director y año del cine no cambiaron."""
    if not isinstance(e, dict) or not re.fullmatch(r"\d+", _s(e.get("tmdb_id"))):
        return False
    if e.get("verif") == "manual":
        return True
    # Solo invalida un dato que existía y cambió: que una fuente nueva sume el
    # director donde antes no había es más información, no otra película.
    def cambia(a, b):
        return bool(_s(a)) and bool(_s(b)) and _s(a) != _s(b)
    return not (cambia(e.get("director_cine"), f.get("director"))
                or cambia(e.get("anio_cine"), f.get("anio")))


# ---------------------------------------------------------------- helpers de título

def _variantes(t):
    """Consultas alternativas: sin sufijos de reposición ni paréntesis."""
    if not t:
        return []
    v = [t]
    c = re.split(r"\s[–—-]\s", t)[0].strip()
    c = re.sub(r"\s*\d+\s*[°º]?\s*(ANIVERSARIO|A[NÑ]OS DE MAGIA).*$", "", c, flags=re.I).strip()
    c = re.sub(r"\s*\(.*?\)\s*$", "", c).strip()
    if c and c.lower() != t.lower():
        v.append(c)
    return v


def consultas(f):
    out = []
    for t in (f.get("original"), f.get("titulo")):
        for v in _variantes(t):
            if v not in out:
                out.append(v)
    return out


def es_evento(f):
    return bool(EVENTO_GENERO.search(f.get("genero") or "")
                or EVENTO_TITULO.search(f.get("titulo") or ""))


def _anio(fecha):
    m = re.match(r"(\d{4})", _s(fecha))
    return m.group(1) if m else ""


def _anio_ok(a, b):
    try:
        return abs(int(a) - int(b)) <= 1
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------- API

def buscar(cl, q):
    """search/movie sin año (el año se filtra acá: el pedido es uno solo)."""
    status, d = cl.pedir("/search/movie", {"query": q, "language": "es-AR",
                                           "include_adult": "false", "page": 1})
    if status != 200 or not isinstance(d, dict):
        return []
    return [r for r in d.get("results") or [] if isinstance(r, dict) and r.get("id")]


def ficha(cl, mid):
    """movie/{id} en inglés + credits + translations -> dict plano o None."""
    status, d = cl.pedir(f"/movie/{mid}", {"language": "en-US",
                                           "append_to_response": "credits,translations,alternative_titles"})
    if status != 200 or not isinstance(d, dict) or not d.get("id"):
        return None
    crew = (d.get("credits") or {}).get("crew") or []
    dirs = list(dict.fromkeys(c["name"] for c in crew
                              if isinstance(c, dict) and c.get("job") == "Director" and c.get("name")))
    local, es = None, []  # es: títulos de todas las traducciones es-* (en orden de preferencia)
    trs = [t for t in (d.get("translations") or {}).get("translations") or []
           if isinstance(t, dict) and t.get("iso_639_1") == "es"]
    pref = {"AR": 0, "MX": 1, "ES": 2}
    for t in sorted(trs, key=lambda t: pref.get(t.get("iso_3166_1"), 3)):
        tit = _s((t.get("data") or {}).get("title"))
        if tit:
            es.append(tit)
    if es:
        local = es[0]
    alt = [_s(t.get("title")) for t in (d.get("alternative_titles") or {}).get("titles") or []
           if isinstance(t, dict) and t.get("iso_3166_1") in ("AR", "MX", "ES")]
    titulos = {norm(x) for x in [d.get("title"), d.get("original_title")] + es + alt} - {""}
    return {"tmdb_id": str(d["id"]), "titulo_en": _s(d.get("title")),
            "titulo_original": _s(d.get("original_title")), "titulo_local": local,
            "anio_tmdb": _anio(d.get("release_date")),
            "vote_average": d.get("vote_average"), "vote_count": d.get("vote_count") or 0,
            "directores": dirs, "titulos": titulos}


def _score(info):
    va, vc = info.get("vote_average"), info.get("vote_count") or 0
    if va is None or vc < MIN_VOTOS or not va:
        return None
    return round(float(va), 1)


def _resultado(info, verif, entrada=None):
    return {"tmdb_id": info["tmdb_id"], "titulo_original": info["titulo_original"],
            "titulo_local": info["titulo_local"], "titulo_en": info["titulo_en"],
            "anio_tmdb": info["anio_tmdb"], "score": _score(info),
            "votos": info.get("vote_count") or 0, "verif": verif}


# ---------------------------------------------------------------- matching

ANIV = re.compile(r"(\d+)\s*[°º]?\s*(?:ANIVERSARIO|A[NÑ]OS DE MAGIA)", re.I)


def _tit_busq(c):
    return {norm(c.get("title")), norm(c.get("original_title"))} - {""}


def _anio_reestreno(f):
    """Año de estreno original deducido de «N° ANIVERSARIO» (año del cine - N), o None."""
    m = ANIV.search(f.get("titulo") or "")
    try:
        return int(f.get("anio")) - int(m.group(1)) if m else None
    except (TypeError, ValueError):
        return None


class _Fichas:
    """Fichas ya pedidas para una película (no se repite el pedido)."""

    def __init__(self, cl):
        self.cl, self.d = cl, {}

    def __call__(self, mid):
        if mid not in self.d:
            self.d[mid] = ficha(self.cl, mid)
        return self.d[mid]


def _decidir(fichas, f, pool, qbase, traza):
    """Aplica las reglas a `pool` (candidatos de título exacto). -> (info, verif) | None."""
    if not pool:
        return None
    anio_cine = f.get("anio")

    def cerca(c):
        a = _anio(c.get("release_date"))
        try:
            return abs(int(a) - int(anio_cine))
        except (TypeError, ValueError):
            return 99

    def razon(c, txt):
        if traza is not None:
            traza.setdefault(c["id"], txt)
    ordenados = sorted(pool, key=cerca)  # estable: empate = orden de TMDb

    if es_evento(f):
        # Recitales, K-pop, óperas: sólo título exacto. Si hay varios, el año debe desempatar.
        if len(pool) > 1:
            ok = [c for c in ordenados if cerca(c) <= 1]
            if len(ok) != 1:
                for c in pool:
                    razon(c, "evento con varios títulos exactos y el año no desempata")
                return None
            ordenados = ok
        info = fichas(ordenados[0]["id"])
        return (info, "evento") if info else None

    if f.get("director"):
        # El director del cine tiene que coincidir con el de TMDb.
        for c in ordenados[:3]:
            info = fichas(c["id"])
            if info and mismo_director(f["director"], info["directores"]) is True:
                return info, "director"
            razon(c, f"director distinto (cine: {f['director']}; TMDb: "
                     f"{', '.join(info['directores']) if info and info['directores'] else 'sin dato'})")
        return None

    # Sin director verificado: año ±1 contra el del cine.
    ok = [c for c in ordenados if cerca(c) <= 1]
    if ok:
        info = fichas(ok[0]["id"])
        return (info, "titulo") if info else None
    # Excepción: reestreno (la consulta ganadora vino de una variante sin sufijo).
    # Vale el único candidato exacto, o el único cuyo año es (año del cine - N).
    via_var = [c for c in ordenados if not (_tit_busq(c) & qbase)]
    esperado = _anio_reestreno(f)
    elegido = None
    if esperado is not None:
        por_anio = [c for c in via_var if _anio_ok(_anio(c.get("release_date")), esperado)]
        if len(por_anio) == 1:
            elegido = por_anio[0]
    if elegido is None and len(via_var) == 1 and len(pool) == 1:
        elegido = via_var[0]
    if elegido is None:
        for c in pool:
            if c in via_var:
                razon(c, f"reestreno sin candidato único (año esperado {esperado}, TMDb {_anio(c.get('release_date')) or '?'})")
            else:
                razon(c, f"sin director verificado y año fuera de ±1 (cine {anio_cine}, TMDb {_anio(c.get('release_date')) or '?'})")
        return None
    info = fichas(elegido["id"])
    return (info, "titulo") if info else None


def elegir(cl, f, cands, qnorm, qbase=None, traza=None, fichas=None):
    """Elige el candidato de `cands` (resultados de search) para la película `f`.

    Devuelve (info_ficha, verif) o None. Sólo se consideran candidatos cuyo
    título (es-AR del search, original, o cualquier traducción es-* /
    título alternativo AR/MX/ES de la ficha) sea IGUAL, normalizado, a una
    consulta. `qbase` = consultas sin tocar; el resto son variantes de reestreno.
    """
    qbase = qnorm if qbase is None else qbase
    fichas = fichas or _Fichas(cl)
    exactos = [c for c in cands if _tit_busq(c) & qnorm]
    r = _decidir(fichas, f, exactos, qbase, traza)
    if r:
        return r
    # Respaldo: el título hispano suele estar sólo en es-MX/es-ES/alternativos.
    # Se miran las fichas de los primeros 3 candidatos no exactos.
    ids = {c["id"] for c in exactos}
    pool = []
    for c in [c for c in cands if c["id"] not in ids][:3]:
        info = fichas(c["id"])
        if info and info["titulos"] & qnorm:
            pool.append(c)
        elif traza is not None:
            traza.setdefault(c["id"], "título distinto en todas sus traducciones es-*")
    return _decidir(fichas, f, pool, qbase, traza)


def resolver_una(cl, f, entrada, traza=None, salida_cands=None):
    """-> (resultado|None, entrada_nueva|None, desde_cache: bool)"""
    if entrada_vigente(entrada, f):
        info = ficha(cl, _s(entrada["tmdb_id"]))
        if info:
            res = _resultado(info, entrada.get("verif") or "cache")
            if entrada.get("verif") == "manual":  # lo escrito a mano manda sobre TMDb
                for c in ("titulo_original", "titulo_local", "titulo_en", "anio_tmdb"):
                    if _s(entrada.get(c)):
                        res[c] = _s(entrada[c])
            return res, None, True
        if entrada.get("verif") == "manual":  # ficha caída: igual se usa lo guardado
            return _desde_entrada(entrada), None, True
        return None, None, True
    qs = consultas(f)
    qnorm = {norm(q) for q in qs} - {""}
    qbase = {norm(x) for x in (f.get("original"), f.get("titulo"))} - {""}
    cands, vistos = [], set()
    for q in qs[:3]:
        if cl.invalido:
            return None, None, False
        nuevos = [c for c in buscar(cl, q) if c["id"] not in vistos]
        vistos |= {c["id"] for c in nuevos}
        cands += nuevos
        if any({norm(c.get("title")), norm(c.get("original_title"))} & qnorm - {""}
               for c in nuevos):
            break
    if salida_cands is not None:
        salida_cands[:] = cands
    elegido = elegir(cl, f, cands, qnorm, qbase, traza)
    if not elegido:
        return None, None, False
    info, verif = elegido
    nueva = {"tmdb_id": info["tmdb_id"], "titulo_original": info["titulo_original"],
             "titulo_local": info["titulo_local"], "titulo_en": info["titulo_en"],
             "anio_tmdb": info["anio_tmdb"], "director_cine": _s(f.get("director")),
             "anio_cine": _s(f.get("anio")), "verif": verif,
             "fecha": datetime.date.today().isoformat()}
    return _resultado(info, verif), nueva, False


def diagnosticar(films, claves, token, pedir=None):
    """Para cada película sin match: top-3 de candidatos y razón del descarte.

    Hace pedidos extra (fichas de los candidatos). Devuelve líneas de texto;
    nunca incluye el token. Sólo para el modo --diagnostico.
    """
    cl = Cliente(token, pedir)
    out = []
    for k in claves:
        f = films[k]
        traza, cands = {}, []
        res, _, _ = resolver_una(cl, f, None, traza=traza, salida_cands=cands)
        if res:
            continue
        out.append(f"{f['titulo']}  [cine: director={f.get('director') or '-'} "
                   f"año={f.get('anio') or '-'} consultas={' | '.join(consultas(f)[:3])}]")
        if not cands:
            out.append("   sin candidatos en search/movie")
        for c in cands[:3]:
            info = ficha(cl, c["id"])
            dirs = ", ".join(info["directores"]) if info and info["directores"] else "sin dato"
            razon = traza.get(c["id"]) or "descartado"
            out.append(f"   #{c['id']} «{c.get('title')}» / «{c.get('original_title')}» "
                       f"({_anio(c.get('release_date')) or '?'}) dir: {dirs} -> {razon}")
    return out


def _desde_entrada(e):
    """Resultado sin puntaje armado sólo con lo guardado en caché."""
    return {"tmdb_id": _s(e.get("tmdb_id")), "titulo_original": _s(e.get("titulo_original")),
            "titulo_local": e.get("titulo_local"), "titulo_en": _s(e.get("titulo_en")),
            "anio_tmdb": _s(e.get("anio_tmdb")), "score": None, "votos": 0,
            "verif": e.get("verif") or "cache"}


def resolver(films, cache, token, pedir=None, workers=4):
    """Resuelve todas las películas. Muta `cache` con las entradas nuevas.

    Sin token (o con token inválido) no hay pedidos: se usan los ids de la
    caché, sin puntaje. Devuelve (resultados {clave: dict}, stats dict).
    """
    cl = Cliente(token, pedir) if token else None
    claves = list(films)

    def una(k):
        f, e = films[k], cache.get(k)
        if cl is None or cl.invalido:
            return (_desde_entrada(e), None, True) if entrada_vigente(e, f) else (None, None, False)
        return resolver_una(cl, f, e)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        salidas = list(ex.map(una, claves))
    res, hits, nuevas = {}, 0, 0
    for k, (r, nueva, cache_hit) in zip(claves, salidas):
        hits += 1 if cache_hit and r else 0
        if nueva:
            cache[k] = nueva
            nuevas += 1
        if r:
            res[k] = r
    stats = {"con_id": len(res), "total": len(claves),
             "verificadas": sum(1 for r in res.values() if r["verif"] in ("director", "manual")),
             "cache": hits, "nuevas": nuevas,
             "con_score": sum(1 for r in res.values() if r["score"] is not None),
             "sin_score_votos": sum(1 for r in res.values() if r["score"] is None and r["votos"] < MIN_VOTOS and cl and not cl.invalido),
             "sin_match": [films[k]["titulo"] for k in claves if k not in res],
             "sin_match_claves": [k for k in claves if k not in res],
             "pedidos": cl.pedidos if cl else 0,
             "invalido": bool(cl and cl.invalido)}
    return res, stats


def token_del_entorno():
    return (os.environ.get("TMDB_TOKEN") or "").strip()
