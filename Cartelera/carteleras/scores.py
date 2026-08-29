"""Puntajes de usuarios.

Hoy sólo TMDb: imdb.com, rottentomatoes.com y letterboxd.com están fuera de la
lista blanca del entorno. Si se habilitan, agregar acá un proveedor nuevo que
devuelva el mismo dict {'score', 'match', 'verif'} y sumarlo en `puntajes`.

El cruce se verifica contra el director que informa el cine: dos películas del
mismo año pueden compartir título (hay dos "The Odyssey" de 2026) y mostrar el
puntaje de la equivocada es peor que no mostrar ninguno.
"""
import html
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from .http import get, quote

BASE = "https://www.themoviedb.org"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())).strip()


def _buscar(q):
    s = get(f"{BASE}/search/movie?query={quote(q)}&language=es-AR")
    out, vistos = [], set()
    # Se recorren los href y no las tarjetas: cuando la búsqueda devuelve un
    # solo resultado no hay tarjeta siguiente que sirva de delimitador.
    for m in re.finditer(r'href="/movie/(\d+)[^"]*"', s):
        mid = m.group(1)
        if mid in vistos:
            continue
        vistos.add(mid)
        v = s[m.start():m.start() + 2200]
        alt = re.search(r'alt="([^"]*)"', v)
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", v))
        anio = re.search(r"\b(?:19|20)\d{2}\b", txt)
        out.append((mid, html.unescape(alt.group(1)) if alt else "",
                    anio.group(0) if anio else ""))
        if len(out) >= 8:
            break
    return out


def _ficha(mid):
    s = get(f"{BASE}/movie/{mid}?language=es-AR")
    pct = re.search(r'user_score_chart"?\s+data-percent="([\d.]+)"', s) \
        or re.search(r'data-percent="([\d.]+)"', s)
    directores = []
    for p in re.findall(r'<li class="profile">(.*?)</li>', s, re.S):
        nom = re.search(r'<a href="/person/[^"]*">([^<]+)</a>', p)
        rol = re.search(r'<p class="character">([^<]+)</p>', p)
        if nom and rol and "Director" in rol.group(1):
            directores.append(nom.group(1).strip())
    titulo = re.search(r"<title>([^<]+)</title>", s)
    anio = re.search(r'class="tag release_date">\(?(\d{4})', s)
    return {
        "pct": float(pct.group(1)) if pct else None,
        "directores": directores,
        "titulo": html.unescape(titulo.group(1)).split(" (")[0] if titulo else "",
        "anio": anio.group(1) if anio else "",
    }


def mismo_director(nuestro, suyos):
    """True / False / None (None = no podemos verificar, falta el dato)."""
    if not nuestro or not suyos:
        return None
    A = {norm(x) for x in re.split(r"[,y]| and ", nuestro) if len(norm(x)) > 2}
    B = {norm(x) for x in suyos}
    if A & B:
        return True
    return bool({a.split()[-1] for a in A if a} & {b.split()[-1] for b in B if b})


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


def _una(f):
    consultas = []
    for t in (f.get("original"), f.get("titulo")):
        for v in _variantes(t):
            if v not in consultas:
                consultas.append(v)

    def intentar(usar_anio):
        for q in consultas:
            probadas = 0
            for mid, titulo, anio in _buscar(q):
                if usar_anio and f.get("anio") and anio and abs(int(anio) - int(f["anio"])) > 1:
                    continue
                probadas += 1
                if probadas > 5:
                    break
                info = _ficha(mid)
                if info["pct"] is None:
                    continue
                dm = mismo_director(f.get("director"), info["directores"])
                titulo_ok = (norm(titulo) == norm(q) or norm(q) in norm(titulo)
                             or norm(titulo) in norm(q))
                if dm is True or (dm is None and titulo_ok):
                    sc = round(info["pct"] / 10, 1)
                    return {
                        "score": sc if sc > 0 else None,  # 0 = todavía sin votos
                        "tmdb": mid,
                        "match": info["titulo"],
                        "verif": "director" if dm else "titulo",
                    }
        return None

    # Sin el filtro de año no entran las reposiciones (Harry Potter 25°
    # aniversario se estrena en 2026 pero en TMDb figura como 2001).
    return intentar(True) or intentar(False)


def puntajes(peliculas, workers=4):
    """peliculas: {clave: dict con titulo/original/anio/director}"""
    claves = list(peliculas)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = ex.map(lambda k: _una(peliculas[k]), claves)
    return {k: v for k, v in zip(claves, res)}
