"""Única Cartelera (unica-cartelera.com.ar): Gaumont, Cosmos UBA, Atlas y Cinépolis Recoleta.

IMPORTANTE: tiene que ser con 'www.'. El dominio pelado devuelve 403. Las páginas
mezclan bytes latin-1 y UTF-8: `http.get` decodifica con errors="replace".

Hay dos formatos de página:

1. Semanal en prosa (Gaumont, Cosmos UBA): encabezado «SEMANA DEL JUEVES 22 AL
   MIÉRCOLES 28 DE OCTUBRE» y por película una línea de horarios sin fecha:
    "14.45 y 19.30 hs."
    "Viernes: 21.45 hs. Ciclo Noches de Terror"
    "14.30, 17.15 y 22 hs. (Viernes: 22 hs. y Martes: 17.15 hs. no hay función)"
    "16.30 hs. Ciclo Horizontes (Martes no hay función)"
   `expandir_semana` convierte eso en horarios por día y `rango_semana` lee el
   encabezado para no repartir horarios fuera de esa semana.

2. Diario (Atlas, Cinépolis): una tarjeta por película y una línea con los
   horarios DEL DÍA DE LA CONSULTA, con idioma: «17 y 19.30 hs. (Cast.)».
   Sin fechas: quien llama le asigna la fecha de Buenos Aires de la corrida.
   Parece listar solo parte de la cartelera (por eso la cobertura es «parcial»).
"""
import datetime
import html
import re
import unicodedata

from ..http import get

URL = "https://www.unica-cartelera.com.ar/cines/microcentro/562-complejo-cine-gaumont"
PAUSA = 1.0  # segundos entre pedidos a unica-cartelera.com.ar

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


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def rango_semana(encabezado, hoy):
    """(inicio, fin) como date a partir de «SEMANA DEL JUEVES 22 AL MIÉRCOLES 28 DE OCTUBRE».

    También entiende «DEL JUEVES 29 DE OCTUBRE AL MIÉRCOLES 4 DE NOVIEMBRE». El año no
    viene: se toma el que deje el fin de la semana más cerca de `hoy` (date).
    Devuelve None si no se lee o si el rango no parece una semana (1 a 8 días).
    """
    if not encabezado:
        return None
    t = _sin_acentos(encabezado)
    m = re.search(r"del\s+\w+\s+(\d{1,2})(?:\s+de\s+(\w+))?\s+al\s+\w+\s+(\d{1,2})\s+de\s+(\w+)", t)
    if not m:
        return None
    d1, mes1, d2, mes2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
    nombres = [_sin_acentos(x) for x in MESES]
    if mes2 not in nombres:
        return None
    m2 = nombres.index(mes2) + 1
    if mes1 is None:
        m1 = m2 if d1 <= d2 else (m2 - 1 or 12)
    elif mes1 in nombres:
        m1 = nombres.index(mes1) + 1
    else:
        return None
    mejor = None
    for anio in (hoy.year - 1, hoy.year, hoy.year + 1):
        try:
            fin = datetime.date(anio, m2, d2)
            ini = datetime.date(anio - (1 if m1 > m2 else 0), m1, d1)
        except ValueError:
            continue
        if not 1 <= (fin - ini).days <= 8:
            continue
        if mejor is None or abs((fin - hoy).days) < abs((mejor[1] - hoy).days):
            mejor = (ini, fin)
    return mejor


def semana_por_defecto(hoy):
    """Sin encabezado legible: desde `hoy` hasta el miércoles siguiente (inclusive si hoy es miércoles)."""
    return hoy, hoy + datetime.timedelta(days=(2 - hoy.weekday()) % 7)


def semanal(url=URL):
    """{'encabezado': str|None, 'peliculas': [...]} de una página semanal (Gaumont, Cosmos)."""
    return parsear_semanal(get(url, espaciar=PAUSA))


def cartelera(url=URL):
    """Compatibilidad: solo la lista de películas."""
    return semanal(url)["peliculas"]


def parsear_semanal(pagina):
    t = _texto_plano(pagina)
    enc = re.search(r"SEMANA\s+DEL\s+[^\n]{3,80}", t)
    return {"encabezado": enc.group(0).strip() if enc else None,
            "peliculas": _peliculas_semanal(t)}


def _peliculas_semanal(t):
    """[{titulo, origen, anio, duracion, director, reparto, sinopsis, horarios[]}]"""
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


# ---------------------------------------------------------------- diario

def _ordenar_horas(horas):
    return sorted(set(horas), key=lambda h: (int(h[:2]) < 5, h))


def parsear_horarios_dia(texto):
    """'17 hs. (Subt.); 14.30 y 19.30 hs. (Subt.)' -> [{'h': '14:30', 'lang': 'S'}, ...].

    Se parte por «;»; en cada grupo las horas llegan hasta «hs» y el idioma sale del
    paréntesis (Cast. -> D, Subt. -> S). Los avisos «(... cerrado)» no son horarios.
    """
    por_hora = {}
    for grupo in re.split(r";", texto or ""):
        parens = [p for p in re.findall(r"\(([^)]*)\)", grupo) if "cerrad" not in p.lower()]
        base = re.sub(r"\([^)]*\)", " ", grupo)
        fin = re.search(r"\bhs\b", base, re.I)
        if not fin:
            continue
        idi = _sin_acentos(" ".join(parens))
        cast, sub = "cast" in idi, "subt" in idi
        lang = "D" if cast and not sub else ("S" if sub and not cast else "")
        for a, b in re.findall(r"\b(\d{1,2})(?:[.:](\d{2}))?\b", base[:fin.start()]):
            if int(a) < 24:
                por_hora.setdefault(_hhmm(a, b), lang)
    return [{"h": h, "lang": por_hora[h]} for h in _ordenar_horas(por_hora)]


def dias_cerrado(pagina_texto):
    """Nombres de día (sin acentos, minúscula) de avisos como «(Martes y miércoles cerrado)»."""
    out = set()
    for m in re.finditer(r"\(([^()]*?)\bcerrad[oa]s?\b[^()]*\)", pagina_texto, re.I):
        for d in re.findall(DIA_RE, m.group(1), re.I):
            out.add(_sin_acentos(d))
    return out


def parsear_diario(pagina):
    """{'cerrado': {dias}, 'peliculas': [{titulo, origen, anio, duracion, director, sinopsis, horarios}]}"""
    peliculas = []
    partes = re.split(r'<h5 class="card-title">', pagina)[1:]
    for b in partes:
        fin_t = b.find("</h5>")
        titulo = html.unescape(re.sub(r"<[^>]+>", "", b[:fin_t])).strip()
        if not titulo or titulo.lower() == "buscar":
            continue
        resto = b[fin_t:]
        pos = resto.find('card-text text-center')
        antes = resto if pos < 0 else resto[:pos]
        horas = re.findall(r'<p class="card-text text-center"><b>(.*?)</b>', resto, re.S)
        linea = "; ".join(re.sub(r"<[^>]+>", " ", html.unescape(h)).strip() for h in horas)
        horarios = parsear_horarios_dia(linea)
        info = re.search(r"\(([^)<]*\d{4}[^)<]*/\s*\d+ *min[^)<]*)\)", antes)
        dur = re.search(r"(\d+)\s*min", info.group(1)) if info else None
        anio = re.search(r"(\d{4})", info.group(1)) if info else None
        dire = re.search(r"<b>\s*Dir\.?[:;,]?\s*(.*?)</b>", antes, re.S)
        lineas = [x.strip() for x in html.unescape(re.sub(r"(?s)<[^>]+>", "\n", antes)).split("\n")]
        sinop = [x for x in lineas if len(x) > 100 and not x.startswith(("Dir", "Reparto"))]
        peliculas.append({
            "titulo": titulo,
            "origen": info.group(1).split("-")[0].strip() if info else None,
            "anio": anio.group(1) if anio else None,
            "duracion": int(dur.group(1)) if dur else None,
            "director": re.sub(r"\s+", " ", html.unescape(dire.group(1))).strip(" .") if dire else None,
            "sinopsis": re.sub(r"\s+", " ", sinop[0]) if sinop else None,
            "horarios": horarios,
        })
    return {"cerrado": dias_cerrado(_texto_plano(pagina)), "peliculas": peliculas}


def diario(url, hoy=None):
    """Página diaria de una sala. `hoy` (date) permite marcar `cerrado_hoy`."""
    r = parsear_diario(get(url, espaciar=PAUSA))
    r["cerrado_hoy"] = bool(hoy and DIAS[hoy.weekday()] in r["cerrado"])
    return r
