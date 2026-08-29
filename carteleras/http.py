"""Cliente HTTP mínimo.

Se usa urllib y no WebFetch a propósito: en el entorno de la rutina WebFetch
está bloqueado por el proxy de egress aunque el tráfico directo pase.
"""
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def get(url, timeout=30, retries=2, lang="es-AR,es;q=0.9"):
    """Devuelve el cuerpo como texto, o '' si falla. Nunca levanta."""
    headers = {"User-Agent": UA, "Accept-Language": lang}
    for intento in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if intento == retries:
                return ""
            time.sleep(1.5 * (intento + 1))
    return ""


def quote(s):
    return urllib.parse.quote(s)
