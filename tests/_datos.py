"""Carga de fixtures de tests (sin red)."""
import json
import pathlib

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"


def crudos_4_salas():
    d = json.loads((FIX / "crudos_4_salas.json").read_text(encoding="utf-8"))

    def pasar(fuente):  # JSON no tiene sets: horas y formatos se arman como en cinemark.funciones
        return {dia: {t: {"horas": set(r["horas"]), "formatos": set(r["formatos"]),
                          "slug_pelicula": r["slug_pelicula"]} for t, r in pelis.items()}
                for dia, pelis in fuente.items()}
    d["ck"], d["ab"] = pasar(d["ck"]), pasar(d["ab"])
    return d
