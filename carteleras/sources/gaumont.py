"""Cine Gaumont (Espacio INCAA Km 0).

El sitio del INCAA carga la cartelera por JS y no sirve nada útil al scrapear.
cinegaumont.ar, que es el oficial, suele estar fuera de la lista blanca del
entorno. La fuente que sí funciona es Única Cartelera, que publica la
programación semanal completa con ficha técnica.

IMPORTANTE: tiene que ser con 'www.'. El dominio pelado devuelve 403.

El Gaumont programa por semana y en prosa, no por día:
    "14.45 y 19.30 hs."
    "Viernes: 21.45 hs. Ciclo Noches de Terror"
    "14.30, 17.15 y 22 hs. (Viernes: 22 hs. y Martes: 17.15 hs. no hay función)"
    "16.30 hs. Ciclo Horizontes (Martes no hay función)"
`expandir_semana` convierte eso en horarios por día.
"""
import html
import json
import re
import unicodedata

from ..http import get

URL = "https://www.unica-cartelera.com.ar/cines/microcentro/562-complejo-cine-gaumont"

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
DIA_RE = r"(Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)"


def _sin_acentos(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower().strip()


def _hhmm(h, m):
    return "%02d:%s" % (int(h), m or "00")


def expandir_semana(texto, dias, dia_de_semana):
    """Devuelve {fecha_iso: [horas]} a partir de una línea de programación.

    dias: fechas ISO a cubrir.  dia_de_semana: {fecha_iso: 0..6 (lunes=0)}.
    """
    t = texto.replace("“", '"').replace("”", '"')
    parentesis = re.findall(r"\(([^)]*)\)", t)
    base = re.sub(r"\([^)]*\)", " ", t)

    # ¿la línea aplica a un solo día? ("Viernes: 21.45 hs. ...")
    solo = None
    m = re.match(r"\s*" + DIA_RE + r"\s*:", base)
    if m:
        solo = _sin_acentos(m.group(1))

    # Los horarios se listan con un único "hs" al final ("14.30, 17.15 y 22 hs."),
    # así que se recorta hasta el primer "hs" y recién ahí se buscan las horas.
    seg = re.sub(r"^\s*" + DIA_RE + r"\s*:", "", base)
    fin = re.search(r"\bhs", seg)
    if fin:
        seg = seg[:fin.end()]
    horas = [_hhmm(a, b) for a, b in re.findall(r"\b(\d{1,2})(?:[.:](\d{2}))?\b", seg)]

    # Excepciones: por día entero, o por día + horario puntual.
    excl_dia, excl_par = set(), set()
    for p in parentesis:
        if "no hay funci" not in p.lower():
            continue
        for m2 in re.finditer(
                DIA_RE + r"\s*:?\s*(?:(\d{1,2})(?:[.:](\d{2}))?\s*hs)?", p):
            d = _sin_acentos(m2.group(1))
            if m2.group(2):
                excl_par.add((d, _hhmm(m2.group(2), m2.group(3))))
            else:
                excl_dia.add(d)

    out = {}
    for f in dias:
        nombre = DIAS[dia_de_semana[f]]
        if solo and nombre != solo:
            continue
        if nombre in excl_dia:
            continue
        hs = [h for h in horas if (nombre, h) not in excl_par]
        if hs:
            out[f] = hs
    return out


def _texto_plano(pagina):
    limpio = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", pagina)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", limpio))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def cartelera():
    """[{titulo, origen, anio, duracion, director, reparto, sinopsis, horarios[]}]"""
    t = _texto_plano(get(URL))
    # El cuerpo arranca en el primer "(Pais-Anio/NN min)"; antes hay sólo menú.
    inicio = re.search(
        r"\n([A-ZÁÉÍÓÚÜÑ0-9][^\n]{1,60})\n\(([^)\n]*\d{4}[^)\n]*/\s*\d+ *min[^)\n]*)\)", t)
    if not inicio:
        return []
    cuerpo = t[inicio.start():]

    bloques = re.split(
        r"\n(?=[A-ZÁÉÍÓÚÜÑ0-9][^\n]{1,60}\n\([^)\n]*\d{4}[^)\n]*/\s*\d+ *min)", cuerpo)
    hora_re = re.compile(r"\b\d{1,2}([.:]\d{2})?\s*hs", re.I)

    films = []
    for b in bloques:
        L = [x.strip() for x in b.split("\n") if x.strip()]
        if len(L) < 2:
            continue
        cab = re.match(r"\(([^)]*)\)", L[1])
        if not cab:
            continue
        info = cab.group(1)
        dur = re.search(r"(\d+)\s*min", info)
        anio = re.search(r"(\d{4})", info)
        director = re.search(r"Dir\.?:\s*(.+)", b)
        reparto = re.search(r"Reparto\s*\n?:\s*(.+)", b)
        sinopsis = [x for x in L[2:]
                    if len(x) > 100 and not x.startswith(("Dir", "Reparto", ":"))]
        films.append({
            "titulo": L[0],
            "origen": info.split("-")[0].strip(),
            "anio": anio.group(1) if anio else None,
            "duracion": int(dur.group(1)) if dur else None,
            "director": director.group(1).strip(" .") if director else None,
            "reparto": reparto.group(1).strip(" .") if reparto else None,
            "sinopsis": sinopsis[0] if sinopsis else None,
            "horarios": [x for x in L if hora_re.search(x) and len(x) < 160],
        })
    return films
