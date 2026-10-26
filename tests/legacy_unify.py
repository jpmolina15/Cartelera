"""Copia del construir de main (4 salas fijas). Solo para el test de no regresion."""
import datetime
import re
from collections import defaultdict

from carteleras.unify import clave, limpiar


def _vacia(k, titulo):
    return {"key": k, "titulo": titulo, "duracion": None, "clasificacion": None,
            "genero": None, "director": None, "elenco": None, "sinopsis": None,
            "origen": None, "anio": None, "original": None, "cines": {}}


def construir(ck, ab, fichas_ck, atlas, gaumont, dias):
    """Devuelve (dias, {clave: pelicula})."""
    films = {}

    def slot(k, titulo):
        if k not in films:
            films[k] = _vacia(k, titulo)
        return films[k]

    # --- Cinemark y Hoyts ---
    for fuente, cine in ((ck, "cinemark"), (ab, "hoyts")):
        for dia, pelis in fuente.items():
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

    # --- Atlas (gana en textos: no pega palabras y trae elenco propio) ---
    for a in atlas:
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
            f["cines"].setdefault("atlas", {})[dia] = [
                {"h": r["hora"],
                 "fmt": "" if r["tec"] == "2D" else (r["tec"] or ""),
                 "lang": "D" if r["doblada"] else ("S" if r["subtitulada"] else "")}
                for r in filas]

    # --- Gaumont (programación semanal expandida a días) ---
    from carteleras.sources.gaumont import expandir_semana
    dow = {d: datetime.date(*map(int, d.split("-"))).weekday() for d in dias}
    for g in gaumont:
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
            f["cines"].setdefault("gaumont", {})[d] = [
                {"h": h, "fmt": "", "lang": ""} for h in sorted(set(hs))]

    for f in films.values():
        for campo in ("sinopsis", "director", "elenco", "genero"):
            f[campo] = limpiar(f[campo])
        f["cines"] = {c: v for c, v in f["cines"].items() if v}
    return {k: v for k, v in films.items() if v["cines"]}
