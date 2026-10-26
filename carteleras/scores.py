"""Utilidades de cruce de películas entre fuentes.

El puntaje de TMDb ahora sale de la API oficial (`carteleras/tmdb.py`); el
scraping de themoviedb.org se sacó porque da 403 desde el 6/10/2026. Acá queda
lo que comparten TMDb y Rotten Tomatoes: normalizar títulos y verificar el
director que informa el cine.

El cruce se verifica contra el director: dos películas del mismo año pueden
compartir título (hay dos "The Odyssey" de 2026) y mostrar el puntaje de la
equivocada es peor que no mostrar ninguno.
"""
import re
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())).strip()


def mismo_director(nuestro, suyos):
    """True / False / None (None = no podemos verificar, falta el dato)."""
    if not nuestro or not suyos:
        return None
    A = {norm(x) for x in re.split(r",| y | and | & ", nuestro) if len(norm(x)) > 2}
    B = {norm(x) for x in suyos}
    if A & B:
        return True
    return bool({a.split()[-1] for a in A if a} & {b.split()[-1] for b in B if b})
