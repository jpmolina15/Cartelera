#!/usr/bin/env python3
"""Releva las cuatro salas y genera la web.

    python3 run.py [--salida salida/cartelera.html] [--sin-puntajes] [--json salida/datos.json]

Sólo usa la biblioteca estándar. Imprime al final un resumen en una línea por
sala para que la rutina pueda contarlo en la notificación.
"""
import argparse
import datetime
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

from carteleras import acumular, fechas, unify
from carteleras.render import render
from carteleras.scores import puntajes
from carteleras.sources import atlas, cinemark, gaumont, rt

RAIZ = pathlib.Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(RAIZ / "salida" / "cartelera.html"))
    ap.add_argument("--json", default=str(RAIZ / "salida" / "datos.json"))
    ap.add_argument("--sin-puntajes", action="store_true")
    ap.add_argument("--sin-acumular", action="store_true",
                    help="ignora lo relevado antes y publica sólo lo de hoy")
    args = ap.parse_args()
    pathlib.Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    # Se lee antes de relevar porque la corrida pisa este mismo archivo.
    previo = None if args.sin_acumular else acumular.leer(args.json)

    print("relevando Cinemark Caballito y Hoyts Abasto...", flush=True)
    ck = cinemark.funciones(cinemark.SALAS["cinemark"])
    ab = cinemark.funciones(cinemark.SALAS["hoyts"])
    if not ck and not ab:
        print("ERROR: ninguna de las dos salas de Cinemark devolvió funciones", file=sys.stderr)

    # Se releva la semana de cartelera, de jueves a miércoles, salteando los
    # días ya pasados: esos los aporta `acumular` con lo que se relevó antes.
    semana = fechas.semana()
    dias = fechas.ventana()

    slugs = {r.get("slug_pelicula")
             for fuente in (ck, ab) for pelis in fuente.values()
             for r in pelis.values()}
    fichas = cinemark.fichas(slugs)

    print("relevando Atlas Caballito...", flush=True)
    atl = atlas.cartelera()
    print("relevando Cine Gaumont...", flush=True)
    gau = gaumont.cartelera()

    films = unify.construir(ck, ab, fichas, atl, gau, dias)
    if not films:
        print("ERROR: ninguna sala devolvió funciones, se aborta", file=sys.stderr)
        return 1

    hoy = datetime.date.today().isoformat()
    heredados = acumular.fusionar(previo, films, semana, hoy)
    # La página cubre la semana entera; los días sin ninguna función no se
    # publican como pestaña vacía.
    dias = [d for d in semana
            if any(d in por for f in films.values() for por in f["cines"].values())]

    for f in films.values():
        f["score"] = f["tmdb"] = f["match"] = f["verif"] = None
        f["rt"] = f["rt_pub"] = f["rt_url"] = None

    if not args.sin_puntajes:
        print("buscando puntajes en TMDb...", flush=True)
        for k, v in puntajes(films).items():
            if v:
                films[k].update(score=v["score"], tmdb=v["tmdb"],
                                match=v["match"], verif=v["verif"])
        print("buscando puntajes en Rotten Tomatoes...", flush=True)
        with ThreadPoolExecutor(max_workers=4) as ex:
            claves = list(films)
            for k, v in zip(claves, ex.map(lambda x: rt.puntaje(films[x]), claves)):
                if v:
                    films[k].update(rt=v["critica"], rt_pub=v["publico"], rt_url=v["url"])

    ahora = datetime.datetime.now()
    dataset = {"days": dias, "films": films,
               "relevado": ahora.strftime("%d/%m/%Y %H:%M")}
    pathlib.Path(args.json).write_text(
        json.dumps(dataset, ensure_ascii=False, indent=1), encoding="utf-8")
    n = render(dataset, args.salida)

    por_cine = {c: sum(1 for f in films.values() if c in f["cines"])
                for c in ("cinemark", "hoyts", "atlas", "gaumont")}
    con_puntaje = sum(1 for f in films.values() if f.get("score"))
    con_rt = sum(1 for f in films.values() if f.get("rt") is not None)
    # Cinemark publica cuatro o cinco días: los últimos de la semana suelen
    # quedar con Atlas y el Gaumont hasta que los cargue.
    sin_ck = [d for d in dias
              if not any(f["cines"].get(c, {}).get(d)
                         for f in films.values() for c in ("cinemark", "hoyts"))]
    faltan = [d for d in semana if d not in dias]
    print("\n--- resumen ---")
    print(f"semana={semana[0]}..{semana[-1]} publicados={dias[0]}..{dias[-1]} "
          f"peliculas={len(films)} tmdb={con_puntaje} rt={con_rt}")
    for c, v in por_cine.items():
        print(f"{c}={v}")
    print(f"dias_heredados={heredados}")
    if sin_ck:
        print("dias_sin_cinemark=" + ",".join(sin_ck))
    if faltan:
        print("dias_sin_funciones=" + ",".join(faltan))
    print(f"html={args.salida} bytes={n}")
    # Una sala en cero casi siempre significa que cambió el sitio o el dominio
    # quedó fuera de la lista blanca, no que no haya funciones.
    vacias = [c for c, v in por_cine.items() if v == 0]
    if vacias:
        print("ATENCION sin_datos=" + ",".join(vacias), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
