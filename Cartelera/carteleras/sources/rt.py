"""Rotten Tomatoes: tomatómetro (crítica) y puntaje del público.

Requiere headers de navegador completos; con un User-Agent pelado la búsqueda
responde vacío. Igual que en TMDb, el cruce se verifica contra el director:
el `ld+json` de la ficha lo trae, así que no hace falta confiar en el título.

IMDb y Letterboxd NO se pueden usar aunque el dominio esté permitido:
  - imdb.com responde 202 con un cuerpo de ~2 KB (challenge de bots)
  - letterboxd.com responde 403
Si alguna vez dejan de bloquear, este módulo es el molde a copiar.
"""
import html
import json
import re
import urllib.parse
import urllib.request

from ..scores import mismo_director, norm

BASE = "https://www.rottentomatoes.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Dest": "document",
}


def _get(url, timeout=30):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _buscar(q):
    s = _get(f"{BASE}/search?search={urllib.parse.quote(q)}")
    urls, vistos = [], set()
    for m in re.finditer(r'href="(https://www\.rottentomatoes\.com/m/[a-z0-9_]+)"', s):
        u = m.group(1)
        if u in vistos:
            continue
        vistos.add(u)
        urls.append(u)
        if len(urls) >= 6:
            break
    return urls


def _ficha(url):
    s = _get(url)
    if not s:
        return None

    def score(bloque):
        m = re.search(rf'"{bloque}":\{{(.{{0,400}})', s)
        if not m:
            return None
        sc = re.search(r'"score":"(\d+)"', m.group(1))
        return int(sc.group(1)) if sc else None

    directores, anio, titulo = [], "", ""
    for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', s, re.S):
        try:
            d = json.loads(html.unescape(b.strip()))
        except json.JSONDecodeError:
            continue
        if d.get("@type") != "Movie":
            continue
        directores = [p.get("name") for p in (d.get("director") or []) if p.get("name")]
        anio = (d.get("dateCreated") or "")[:4]
        titulo = d.get("name") or ""
        break
    if not titulo:
        t = re.search(r"<title>([^<|]+)", s)
        titulo = t.group(1).strip() if t else ""
    return {"critica": score("criticsScore"), "publico": score("audienceScore"),
            "directores": directores, "anio": anio, "titulo": titulo, "url": url}


def puntaje(f):
    """f: dict con titulo/original/anio/director -> dict o None."""
    consultas = []
    for t in (f.get("original"), f.get("titulo")):
        if t and t not in consultas:
            consultas.append(t)
    for q in consultas:
        for url in _buscar(q):
            info = _ficha(url)
            if not info or (info["critica"] is None and info["publico"] is None):
                continue
            if f.get("anio") and info["anio"] and abs(int(info["anio"]) - int(f["anio"])) > 1:
                continue
            dm = mismo_director(f.get("director"), info["directores"])
            titulo_ok = norm(info["titulo"]) == norm(q) or norm(q) in norm(info["titulo"])
            if dm is True or (dm is None and titulo_ok):
                return {"critica": info["critica"], "publico": info["publico"],
                        "url": info["url"], "match": info["titulo"],
                        "verif": "director" if dm else "titulo"}
    return None
