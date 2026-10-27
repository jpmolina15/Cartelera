"""Cruce de todas las salas del padron en un único índice de películas.

Cada fuente escribe los títulos distinto ("SPIDER-MAN: UN NUEVO DÍA" vs
"...DIA", "YO, NARCISO" vs "YO,NARCISO") y Atlas además los trunca a 30
caracteres. `clave()` normaliza acentos y puntuación; lo que la normalización
no puede resolver son los casos en que dos cines usan nombres realmente
distintos para la misma película, y para eso está ALIAS.

SI UNA PELÍCULA APARECE DUPLICADA EN LA WEB, casi siempre se arregla agregando
una entrada a ALIAS.
"""
import datetime
import re
import unicodedata
from collections import defaultdict

# Título normalizado de una fuente -> título normalizado canónico.
ALIAS = {
    "HARRY POTTER Y LA PIEDRA FILOS": "HARRY POTTER 25 ANIVERSARIO",
    "LA NOCHE DEL DEMONIO ESTAN ENT": "LA NOCHE DEL DEMONIO 6",
    # El título entero, del que sale el truncado de Atlas de arriba.
    "LA NOCHE DEL DEMONIO ESTAN ENTRE NOSOTROS": "LA NOCHE DEL DEMONIO 6",
    # Hoyts la estrena como "Colony: Zona Cero"; Atlas la lista "Zona Cero".
    "COLONY ZONA CERO": "ZONA CERO",
    # Reposiciones: Atlas las lista con el título pelado; Cinemark y Hoyts le
    # agregan el sufijo del aniversario, el año o la aclaración.
    "AVENGERS ENDGAME": "AVENGERS ENDGAME RE ESTRENO",
    "CARS": "CARS 20 ANIVERSARIO",
    "VERTIGO 2": "VERTIGO 2 PUNTO MUERTO",
    "LOS JUEGOS DEL HAMBRE": "LOS JUEGOS DEL HAMBRE 2012",
    "JUEGOS DEL HAMBRE EN LLAMAS": "LOS JUEGOS DEL HAMBRE EN LLAMAS 2013",
    "JUEGOS DEL HAMBRE SINSAJO PT 1": "LOS JUEGOS DEL HAMBRE SINSAJO 1 2014",
    "JUEGOS DEL HAMBRE SINSAJO PT 2": "LOS JUEGOS DEL HAMBRE SINSAJO 2 2015",
    # El recital de Queen: Atlas lo acorta, Hoyts usa el título completo.
    "QUEEN LIVE IN BUDAPEST": "QUEEN BUDAPEST",
    # Atlas trunca a 30 caracteres.
    "TADEO EL EXPLORADOR Y LA LAMPA": "TADEO EL EXPLORADOR Y LA LAMPARA",
    "HECHIZO DE AMOR LA MAGIA CONT": "HECHIZO DE AMOR LA MAGIA CONTINUA",
    # Atlas escribe "OASIS,DON'T..." y Cinemark "OASIS: DON´T...": el apóstrofo
    # raro de Cinemark deja un "DON T" suelto que la normalización no junta.
    "OASIS DONT LOOK BACK IN ANGER": "OASIS DON T LOOK BACK IN ANGER",
    # El Gaumont escribe mal el gentilicio ("cordobeces" por "cordobeses").
    "CORDOBECES LA PELICULA": "CORDOBESES LA PELICULA",
}


def normalizar(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())).strip()


def clave(t):
    n = normalizar(t)
    return ALIAS.get(n, n)


def limpiar(t):
    """Arregla sólo espaciado seguro.

    Cinemark pega palabras ("un librosobre") y Atlas se come el espacio tras
    las comas ("Oreiro,profesora"). Lo segundo se puede corregir con una regla;
    lo primero requeriría adivinar dónde va el corte, así que se deja como está.
    """
    if not t:
        return t
    t = re.sub(r",(?=\S)", ", ", t)
    t = re.sub(r"\.(?=[A-ZÁÉÍÓÚÑ])", ". ", t)
    return re.sub(r"\s+", " ", t).strip()


def _vacia(k, titulo):
    return {"key": k, "titulo": titulo, "duracion": None, "clasificacion": None,
            "genero": None, "director": None, "elenco": None, "sinopsis": None,
            "origen": None, "anio": None, "original": None, "cines": {}}


ORDEN_FUENTES = ("cinemark", "atlas", "unica", "multiplex", "showcase")


def _cinemark(slot, sala, datos, fichas_ck, dias):
    cine = sala["id"]
    for dia, pelis in datos.items():
        if dia not in dias:
            continue
        for titulo, r in pelis.items():
            f = slot(clave(titulo), titulo)
            ficha = fichas_ck.get(r.get("slug_pelicula")) or {}
            if ficha:
                f["duracion"] = f["duracion"] or ficha.get("duracion")
                f["clasificacion"] = f["clasificacion"] or ficha.get("clasificacion")
                f["genero"] = f["genero"] or (", ".join(ficha.get("generos") or []) or None)
                f["sinopsis"] = f["sinopsis"] or ficha.get("sinopsis")
                f["anio"] = f["anio"] or (ficha.get("estreno") or "")[:4] or None
                dirs = [c["nombre"] for c in ficha.get("equipo", []) if c["rol"] == "Director"]
                act = [c["nombre"] for c in ficha.get("equipo", []) if c["rol"] == "Actor"]
                f["director"] = f["director"] or (", ".join(dict.fromkeys(dirs)) or None)
                f["elenco"] = f["elenco"] or (", ".join(act[:4]) or None)
            idiomas = ficha.get("idiomas") or []
            # Cinemark no informa idioma por función, sólo los disponibles
            # por película: la letra sólo es fiable si hay uno solo.
            lang = "D" if idiomas == ["CAST"] else ("S" if idiomas == ["SUB"] else "")
            fmts = sorted(x for x in r["formatos"] if x and x != "2D")
            f["cines"].setdefault(cine, {})[dia] = [
                {"h": h, "fmt": ", ".join(fmts), "lang": lang} for h in sorted(r["horas"])]


def _atlas(slot, sala, datos, dias):
    # Atlas gana en textos: no pega palabras y trae elenco propio.
    cine = sala["id"]
    for a in datos:
        f = slot(clave(a["titulo"]), a["titulo"])
        f["duracion"] = f["duracion"] or (f"{a['duracion']} min" if a.get("duracion") else None)
        if a.get("clasificacion"):
            f["clasificacion"] = f["clasificacion"] or re.sub(r"\(.*", "", a["clasificacion"]).strip()
        f["genero"] = f["genero"] or a.get("genero")
        f["director"] = (", ".join(a["directores"]) if a.get("directores") else None) or f["director"]
        f["elenco"] = (", ".join(a["actores"][:4]) if a.get("actores") else None) or f["elenco"]
        f["sinopsis"] = a.get("sinopsis") or f["sinopsis"]
        f["original"] = a.get("original") or f["original"]
        f["anio"] = f["anio"] or ((a.get("estreno") or "")[-4:] or None)
        for dia, filas in a["funciones"].items():
            if dia not in dias:
                continue
            f["cines"].setdefault(cine, {})[dia] = [
                {"h": r["hora"],
                 "fmt": "" if r["tec"] == "2D" else (r["tec"] or ""),
                 "lang": "D" if r["doblada"] else ("S" if r["subtitulada"] else "")}
                for r in filas]


def _unica_semanal(slot, sala, datos, dias, hoy):
    """Programación semanal en prosa (Gaumont, Cosmos) expandida a días.

    Solo reparte dentro de la semana que dice el encabezado («SEMANA DEL JUEVES 22 AL
    MIÉRCOLES 28 DE OCTUBRE»). Sin encabezado legible, hasta el miércoles siguiente a
    la fecha de corrida: nunca se repite una semana.
    """
    from .sources.unica import expandir_semana, rango_semana, semana_por_defecto
    cine = sala["id"]
    peliculas = datos["peliculas"] if isinstance(datos, dict) else datos
    enc = datos.get("encabezado") if isinstance(datos, dict) else None
    hoy_d = _fecha(hoy)
    rango = rango_semana(enc, hoy_d) or semana_por_defecto(hoy_d)
    ini, fin = (r.isoformat() for r in rango)
    dias = [d for d in dias if ini <= d <= fin]
    dow = {d: _fecha(d).weekday() for d in dias}
    for g in peliculas:
        f = slot(clave(g["titulo"]), g["titulo"])
        f["duracion"] = f["duracion"] or (f"{g['duracion']} min" if g.get("duracion") else None)
        f["director"] = f["director"] or g.get("director")
        f["elenco"] = f["elenco"] or g.get("reparto")
        f["sinopsis"] = f["sinopsis"] or g.get("sinopsis")
        f["origen"] = g.get("origen")
        f["anio"] = f["anio"] or g.get("anio")
        por_dia = defaultdict(list)
        for linea in g["horarios"]:
            for d, hs in expandir_semana(linea, dias, dow).items():
                por_dia[d] += hs
        for d, hs in por_dia.items():
            f["cines"].setdefault(cine, {})[d] = [
                {"h": h, "fmt": "", "lang": ""} for h in sorted(set(hs))]


def _unica_diario(slot, sala, datos, dias, hoy):
    """Una línea por película con los horarios del día de la corrida (con idioma)."""
    if datos.get("cerrado_hoy") or hoy not in dias:
        return
    cine = sala["id"]
    for g in datos["peliculas"]:
        if not g["horarios"]:
            continue
        f = slot(clave(g["titulo"]), g["titulo"])
        f["duracion"] = f["duracion"] or (f"{g['duracion']} min" if g.get("duracion") else None)
        f["director"] = f["director"] or g.get("director")
        f["sinopsis"] = f["sinopsis"] or g.get("sinopsis")
        f["origen"] = f["origen"] or g.get("origen")
        f["anio"] = f["anio"] or g.get("anio")
        f["cines"].setdefault(cine, {})[hoy] = [
            {"h": r["h"], "fmt": "", "lang": r["lang"]} for r in g["horarios"]]


def _showcase(slot, sala, datos, dias, hoy):
    """HTML del día de la consulta: formato e idioma por función."""
    if hoy not in dias:
        return
    cine = sala["id"]
    for g in datos:
        f = slot(clave(g["titulo"]), g["titulo"])
        if g.get("duracion"):
            f["duracion"] = f["duracion"] or f"{g['duracion']} min"
        f["clasificacion"] = f["clasificacion"] or g.get("clasificacion")
        f["sinopsis"] = f["sinopsis"] or g.get("sinopsis")
        f["cines"].setdefault(cine, {})[hoy] = [
            {"h": r["h"], "fmt": r["fmt"], "lang": r["lang"]}
            for r in sorted(g["funciones"], key=lambda r: horaComparable(r["h"]))]


def _multiplex(slot, sala, datos, dias, hoy):
    """Funciones por noche de cine (`dia`), ya deduplicadas por id; recorta a la ventana."""
    cine = sala["id"]
    for fn in datos:
        if fn["dia"] not in dias:
            continue
        f = slot(clave(fn["titulo"]), fn["titulo"])
        f["cines"].setdefault(cine, {}).setdefault(fn["dia"], []).append(
            {"h": fn["h"], "fmt": fn["fmt"], "lang": fn["lang"]})
    for f in list(slot.films.values()):
        for dia, rows in f["cines"].get(cine, {}).items():
            rows.sort(key=lambda r: (horaComparable(r["h"]), r["fmt"], r["lang"]))


def horaComparable(h):
    """Minutos del día; 00:00-04:59 cuentan como 24-28 h (trasnoche), igual que en la plantilla."""
    hh, mm = (int(x) for x in h.split(":")[:2])
    return (hh + 24 if hh < 5 else hh) * 60 + mm


def _fecha(iso):
    return datetime.date(*map(int, iso.split("-")))


# (fuente, modo) -> funcion. Sin `else`: una fuente desconocida es un error, no un Gaumont.
def _despachar(sala):
    f, modo = sala["fuente"], (sala.get("cfg") or {}).get("modo")
    tabla = {("cinemark", None): "cinemark", ("atlas", None): "atlas",
             ("unica", "semanal"): "unica_semanal", ("unica", "diario"): "unica_diario",
             ("multiplex", None): "multiplex", ("showcase", None): "showcase"}
    try:
        return tabla[(f, modo)]
    except KeyError:
        raise ValueError(f"sala {sala.get('id')}: no se como unificar fuente={f!r} modo={modo!r}")


def construir(crudos, fichas_ck, dias, hoy=None):
    """crudos: [(sala_del_padron, datos_crudos)]. Devuelve {clave: pelicula}.

    `hoy` es la fecha de Buenos Aires de la corrida (ISO); por defecto, el primer dia de
    la ventana. Las fuentes «solo hoy» (Showcase, unica diario) cuelgan sus horarios de
    ahi, y las semanales (Gaumont, Cosmos) no pasan de su semana.
    Se procesa por fuente (ORDEN_FUENTES) y dentro de cada una en el orden de `crudos`
    (el del padron): "el primero que trae un dato gana".
    """
    films = {}
    hoy = hoy or (dias[0] if dias else None)

    def slot(k, titulo):
        if k not in films:
            films[k] = _vacia(k, titulo)
        return films[k]
    slot.films = films

    por_tipo = [(_despachar(sala), sala, datos) for sala, datos in crudos]
    for fuente in ORDEN_FUENTES:
        for tipo, sala, datos in por_tipo:
            if sala["fuente"] != fuente:
                continue
            if tipo == "cinemark":
                _cinemark(slot, sala, datos, fichas_ck, dias)
            elif tipo == "atlas":
                _atlas(slot, sala, datos, dias)
            elif tipo == "unica_semanal":
                _unica_semanal(slot, sala, datos, dias, hoy)
            elif tipo == "unica_diario":
                _unica_diario(slot, sala, datos, dias, hoy)
            elif tipo == "multiplex":
                _multiplex(slot, sala, datos, dias, hoy)
            elif tipo == "showcase":
                _showcase(slot, sala, datos, dias, hoy)

    for f in films.values():
        for campo in ("sinopsis", "director", "elenco", "genero"):
            f[campo] = limpiar(f[campo])
        f["cines"] = {c: v for c, v in f["cines"].items() if v}
    return {k: v for k, v in films.items() if v["cines"]}
