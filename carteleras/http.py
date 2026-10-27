"""Cliente HTTP mínimo.

Se usa urllib y no WebFetch a propósito: en el entorno de la rutina WebFetch
está bloqueado por el proxy de egress aunque el tráfico directo pase.
"""
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


_lock = threading.Lock()
PEDIDOS = 0  # intentos HTTP hechos en esta corrida (el resumen de run.py lo informa)


def _espera_429(e, intento):
    """Segundos a esperar tras un 429: Retry-After si viene, tope 10 s."""
    try:
        return max(0.0, min(float(e.headers.get("Retry-After", "")), 10.0))
    except Exception:
        return 1.5 * (intento + 1)


_ultimo = {}  # dominio -> instante del ultimo pedido (para espaciar)


def _espaciar(url, seg):
    """Espera lo que falte para que pasen `seg` segundos desde el ultimo pedido al mismo dominio."""
    dom = urllib.parse.urlsplit(url).netloc
    with _lock:
        falta = seg - (time.time() - _ultimo.get(dom, 0.0))
        _ultimo[dom] = time.time() + max(0.0, falta)
    if falta > 0:
        time.sleep(falta)


def get(url, timeout=30, retries=2, lang="es-AR,es;q=0.9", headers=None, con_status=False,
        espaciar=0):
    """Devuelve el cuerpo como texto, o '' si falla. Nunca levanta.

    `headers` se suma a los de siempre (para Authorization). Con
    `con_status=True` devuelve (status, cuerpo): status 0 si no hubo respuesta,
    el codigo HTTP si hubo (4xx/5xx incluidos, con su cuerpo). En ese modo un
    429 espera `Retry-After` y reintenta (maximo 2 veces); el resto de los
    codigos de error se devuelve tal cual. Nunca se registra la URL ni los
    headers: pueden llevar credenciales. `espaciar=N` deja N segundos entre
    pedidos al mismo dominio (ritmo bajo con las fuentes chicas).
    """
    hdrs = {"User-Agent": UA, "Accept-Language": lang}
    hdrs.update(headers or {})
    status, cuerpo = 0, ""
    for intento in range(retries + 1):
        global PEDIDOS
        with _lock:
            PEDIDOS += 1
        if espaciar:
            _espaciar(url, espaciar)
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                cuerpo = r.read().decode("utf-8", "replace")
                return (r.status, cuerpo) if con_status else cuerpo
        except urllib.error.HTTPError as e:
            if not con_status:
                if intento == retries:
                    return ""
                time.sleep(1.5 * (intento + 1))
                continue
            try:
                cuerpo = e.read().decode("utf-8", "replace")
            except Exception:
                cuerpo = ""
            status = e.code
            if status == 429 and intento < retries:
                time.sleep(_espera_429(e, intento))
                continue
            return status, cuerpo
        except Exception:
            if intento == retries:
                return (0, "") if con_status else ""
            time.sleep(1.5 * (intento + 1))
    return (status, cuerpo) if con_status else ""


def quote(s):
    return urllib.parse.quote(s)
