#!/usr/bin/env python3
"""Releva las salas del padron (data/salas.json) y genera la web.

    python3 run.py [--salida salida/cartelera.html] [--sin-puntajes] [--json salida/datos.json]

Sólo usa la biblioteca estándar. Imprime al final un resumen en una línea por
sala para que la rutina pueda contarlo en la notificación.
"""
import argparse
import datetime
import json
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from carteleras import http, tmdb, unify
from carteleras import salas as salas_mod
from carteleras.render import render
from carteleras.sources import atlas, cinemark, gaumont, rt

RAIZ = pathlib.Path(__file__).resolve().parent

# Despacho por fuente: cada sala del padron dice cual usa y con que parametros.
RELEVAR = {"cinemark": lambda cfg: cinemark.funciones(cfg["slug"]),
           "atlas": lambda cfg: atlas.cartelera(complejo=cfg["complejo"]),
           "gaumont": lambda cfg: gaumont.cartelera(url=cfg["url"])}


def ahora_ba():
    """Hora de Buenos Aires; respaldo UTC-3 fijo si no hay zoneinfo."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Argentina/Buenos_Aires")
    except Exception:
        tz = datetime.timezone(datetime.timedelta(hours=-3))
    return datetime.datetime.now(tz).strftime("%d/%m/%Y %H:%M")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(RAIZ / "salida" / "cartelera.html"))
    ap.add_argument("--json", default=str(RAIZ / "salida" / "datos.json"))
    ap.add_argument("--sin-puntajes", action="store_true")
    ap.add_argument("--cache-tmdb", default=str(tmdb.CACHE_RUTA),
                    help="caché de ids de TMDb (se commitea; sin datos sensibles)")
    args = ap.parse_args()
    pathlib.Path(args.salida).parent.mkdir(parents=True, exist_ok=True)

    try:
        salas = salas_mod.cargar()
    except salas_mod.PadronInvalido as e:
        print(f"ERROR: padron de salas invalido: {e}", file=sys.stderr)
        return 1

    t0 = time.time()
    crudos = []
    for sala in salas:
        print(f"relevando {sala['nombre']}...", flush=True)
        try:
            datos = RELEVAR[sala["fuente"]](sala["cfg"])
        except Exception as e:  # una sala que falla no frena a las demas
            print(f"ERROR: {sala['id']}: {type(e).__name__}: {e}", file=sys.stderr)
            datos = {} if sala["fuente"] == "cinemark" else []
        crudos.append((sala, datos))

    # La ventana de dias la define lo que publica Cinemark (suele ser 5).
    dias = sorted({d for sala, datos in crudos if sala["fuente"] == "cinemark"
                   for d in datos})[:5]
    if not dias:
        print("ERROR: sin dias para procesar, se aborta", file=sys.stderr)
        return 1

    slugs = {r.get("slug_pelicula")
             for sala, datos in crudos if sala["fuente"] == "cinemark"
             for pelis in datos.values() for r in pelis.values()}
    fichas = cinemark.fichas(slugs)

    films = unify.construir(crudos, fichas, dias)

    for f in films.values():
        f["score"] = f["tmdb"] = f["match"] = f["verif"] = None
        f["tmdb_id"] = f["titulo_original"] = f["titulo_local"] = None
        f["titulo_en"] = f["anio_tmdb"] = None
        f["rt"] = f["rt_pub"] = f["rt_url"] = None

    tstats, token = None, ""
    if not args.sin_puntajes:
        token = tmdb.token_del_entorno()
        if not token:
            print("ATENCION sin_clave=tmdb", file=sys.stderr)
        print("buscando datos y puntajes en TMDb (API)...", flush=True)
        cache = tmdb.cargar_cache(args.cache_tmdb)
        res, tstats = tmdb.resolver(films, cache, token)
        if tstats["invalido"]:
            print("ATENCION clave_invalida=tmdb", file=sys.stderr)
        for k, v in res.items():
            films[k].update(
                score=v["score"], tmdb=v["tmdb_id"], tmdb_id=v["tmdb_id"],
                match=v["titulo_local"] or v["titulo_en"], verif=v["verif"],
                titulo_original=v["titulo_original"], titulo_local=v["titulo_local"],
                titulo_en=v["titulo_en"], anio_tmdb=v["anio_tmdb"] or None)
        if token and not tstats["invalido"]:
            tmdb.guardar_cache(cache, args.cache_tmdb)
        print("buscando puntajes en Rotten Tomatoes...", flush=True)
        with ThreadPoolExecutor(max_workers=4) as ex:
            claves = list(films)
            for k, v in zip(claves, ex.map(lambda x: rt.puntaje(films[x]), claves)):
                if v:
                    films[k].update(rt=v["critica"], rt_pub=v["publico"], rt_url=v["url"])

    por_sala = {sala["id"]: sum(1 for f in films.values() if sala["id"] in f["cines"])
                for sala in salas}
    vacias = [c for c, v in por_sala.items() if v == 0]
    dataset = {"days": dias, "films": films, "relevado": ahora_ba(),
               "salas": {s["id"]: {"nombre": s["nombre"], "corto": s["corto"],
                                   "cadena": s["cadena"], "direccion": s["direccion"],
                                   "barrio": s["barrio"], "comuna": s["comuna"],
                                   "lat": s["lat"], "lon": s["lon"], "url": s["url"],
                                   "fuente": s["fuente"],
                                   "con_datos": por_sala[s["id"]] > 0}
                         for s in salas},
               "sin_datos": vacias}
    pathlib.Path(args.json).write_text(
        json.dumps(dataset, ensure_ascii=False, indent=1), encoding="utf-8")
    n = render(dataset, args.salida)

    con_puntaje = sum(1 for f in films.values() if f.get("score"))
    con_rt = sum(1 for f in films.values() if f.get("rt") is not None)
    print("\n--- resumen ---")
    print(f"dias={dias[0]}..{dias[-1]} peliculas={len(films)} "
          f"tmdb={con_puntaje} rt={con_rt}")
    if tstats:
        print(f"tmdb_id={tstats['con_id']}/{tstats['total']} verificadas={tstats['verificadas']} "
              f"cache={tstats['cache']} sin_score_votos={tstats['sin_score_votos']} "
              f"pedidos_tmdb={tstats['pedidos']}")
        if token and tstats["sin_match"]:
            print("sin_tmdb_id=" + " | ".join(tstats["sin_match"]))
    for c, v in por_sala.items():
        print(f"{c}={v}")
    print(f"html={args.salida} bytes={n}")
    print(f"pedidos_http={http.PEDIDOS} duracion={time.time() - t0:.0f}s")
    # Una sala en cero casi siempre significa que cambio el sitio o el dominio
    # quedo fuera de la lista blanca, no que no haya funciones.
    if vacias:
        print("ATENCION sin_datos=" + ",".join(vacias), file=sys.stderr)
    # Cero puntajes con películas en cartel es el mismo síntoma: el proveedor
    # cambió o empezó a responder un desafío de bots, no que nadie las votó.
    if not args.sin_puntajes and films:
        for prov, n_ok in (("tmdb", con_puntaje), ("rt", con_rt)):
            # Sin token (o token inválido) ya se avisó sin_clave / clave_invalida.
            if prov == "tmdb" and (not token or tstats["invalido"]):
                continue
            if n_ok == 0:
                print(f"ATENCION sin_puntajes={prov}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
