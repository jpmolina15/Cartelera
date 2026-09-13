"""Conserva lo ya relevado de los días de la semana que quedaron atrás.

El sitio de Cinemark publica sólo cuatro o cinco días: la corrida del jueves
llega hasta el lunes y la del domingo completa el martes y el miércoles. Para
que la página cubra la semana entera, la del domingo tiene que sumar lo que la
del jueves ya relevó del jueves al sábado.

Dos límites que hacen que esto no sea reutilizar horarios viejos:

  * sólo se copian días de la semana en curso, así que un `datos.json` de la
    semana pasada no aporta nada;
  * sólo se copian días ya pasados, nunca uno que la corrida actual pueda
    relevar. Un cambio de horario de hoy en adelante siempre gana.
"""
import json
import pathlib


def leer(ruta):
    """El dataset de la corrida anterior, o None si no hay o está roto."""
    try:
        return json.loads(pathlib.Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def fusionar(previo, films, semana, hoy):
    """Suma a `films` las funciones ya relevadas de los días pasados de `semana`.

    Devuelve la cantidad de días que aportó el relevamiento anterior.
    """
    if not previo:
        return 0
    pasados = {d for d in semana if d < hoy}
    if not pasados:
        return 0

    sumados = set()
    for k, viejo in (previo.get("films") or {}).items():
        heredado = {c: {d: hs for d, hs in por_dia.items() if d in pasados}
                    for c, por_dia in (viejo.get("cines") or {}).items()}
        heredado = {c: v for c, v in heredado.items() if v}
        if not heredado:
            continue
        f = films.get(k)
        if f is None:
            # Película que terminó su corrida entre las dos pasadas: entra sólo
            # con los días que llegó a dar.
            f = films[k] = dict(viejo, cines={})
        for cine, por_dia in heredado.items():
            for dia, horarios in por_dia.items():
                f["cines"].setdefault(cine, {}).setdefault(dia, horarios)
                sumados.add(dia)
    return len(sumados)
