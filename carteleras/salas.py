"""Padron de salas: data/salas.json es la unica lista de salas del proyecto."""
import json
import pathlib

RUTA = pathlib.Path(__file__).resolve().parent.parent / "data" / "salas.json"

OBLIGATORIOS = ("id", "nombre", "corto", "cadena", "direccion", "barrio", "comuna",
                "lat", "lon", "fuente", "cfg", "url")
LAT = (-34.71, -34.53)
LON = (-58.54, -58.33)


class PadronInvalido(ValueError):
    pass


def validar(lista):
    if not isinstance(lista, list) or not lista:
        raise PadronInvalido("el padron tiene que ser una lista no vacia")
    ids = set()
    for i, s in enumerate(lista):
        if not isinstance(s, dict):
            raise PadronInvalido(f"sala #{i}: no es un objeto")
        for campo in OBLIGATORIOS:
            if campo not in s or s[campo] in (None, ""):
                raise PadronInvalido(f"sala {s.get('id', '#' + str(i))}: falta el campo '{campo}'")
        if s["id"] in ids:
            raise PadronInvalido(f"id repetido: {s['id']}")
        ids.add(s["id"])
        if not isinstance(s["comuna"], int) or isinstance(s["comuna"], bool):
            raise PadronInvalido(f"sala {s['id']}: comuna tiene que ser un entero")
        try:
            lat, lon = float(s["lat"]), float(s["lon"])
        except (TypeError, ValueError):
            raise PadronInvalido(f"sala {s['id']}: lat/lon no numericas")
        if not (LAT[0] <= lat <= LAT[1] and LON[0] <= lon <= LON[1]):
            raise PadronInvalido(f"sala {s['id']}: coordenadas fuera de CABA ({lat}, {lon})")


def cargar(ruta=RUTA):
    """Devuelve las salas activas, en el orden del archivo. Levanta PadronInvalido."""
    try:
        lista = json.loads(pathlib.Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PadronInvalido(f"no se pudo leer {ruta}: {e}")
    validar(lista)
    return [s for s in lista if s.get("activa", True)]
