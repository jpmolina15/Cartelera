"""Showcase Belgrano (todoshowcase.com/cartelera/belgrano).

HTML del lado del servidor, sin fechas: lista lo del día de la consulta. Por película:
título (`movie-guide-title`), «Duración: 113 minutos», «Calificación: R-13» y, en el
primer menú, una línea por formato e idioma: «2D-Subtitulado 19:15 21:50». El segundo
menú es la sinopsis. Quien llama le asigna la fecha de Buenos Aires de la corrida.
"""
import html
import re

from ..http import get

URL = "https://www.todoshowcase.com/cartelera/belgrano"
_LANG = {"subtitulado": "S", "subtitulada": "S", "castellano": "D", "doblado": "D", "doblada": "D"}


def _texto(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", s))).strip()


def parsear(pagina):
    """[{titulo, duracion, clasificacion, sinopsis, funciones: [{h, fmt, lang}]}]"""
    out = []
    for b in re.split(r'movie-guide-title">', pagina)[1:]:
        titulo = _texto(b[:b.find("</h4>")])
        if not titulo:
            continue
        dur = re.search(r"Duraci[oó]n:\s*(\d+)\s*min", b)
        cal = re.search(r"Calificaci[oó]n:\s*([^<\n]+)", b)
        menus = re.findall(r'<ul class="dropdown-menu[^"]*"[^>]*>(.*?)</ul>', b, re.S)
        funciones = []
        for linea in re.findall(r"<p>(.*?)</p>", menus[0] if menus else "", re.S):
            m = re.match(r"\s*(.+?)-\s*([A-Za-záéíóú]+)\s+((?:\d{1,2}:\d{2}\s*)+)$", _texto(linea))
            if not m:
                continue
            fmt = m.group(1).strip().upper()
            lang = _LANG.get(m.group(2).strip().lower(), "")
            for h in re.findall(r"\d{1,2}:\d{2}", m.group(3)):
                funciones.append({"h": h.zfill(5), "fmt": "" if fmt == "2D" else fmt, "lang": lang})
        sinop = _texto(menus[1]) if len(menus) > 1 else ""
        if funciones:
            out.append({"titulo": titulo,
                        "duracion": int(dur.group(1)) if dur else None,
                        "clasificacion": cal.group(1).strip() if cal else None,
                        "sinopsis": sinop or None, "funciones": funciones})
    return out


def cartelera(url=URL):
    return parsear(get(url))
