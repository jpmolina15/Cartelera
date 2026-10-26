"""_jsonld y funciones sobre un bloque JSON-LD real de /cartelera/caballito (recortado)."""
import json
import unittest
from unittest import mock

from carteleras.sources import cinemark
from tests._datos import FIX


def _pagina():
    bloque = json.loads((FIX / "cinemark_jsonld_caballito.json").read_text(encoding="utf-8"))
    return ("<html><script>var x='application/ld+json';</script><script type=\"application/ld+json\">"
            + json.dumps(bloque, ensure_ascii=False, separators=(",", ":")) + "</script></html>")


class TestCinemarkJsonLd(unittest.TestCase):
    def test_jsonld(self):
        d = cinemark._jsonld(_pagina())
        self.assertEqual(d["@type"], "MovieTheater")
        self.assertEqual(len(d["event"]), 8)

    def test_funciones_con_get_simulado(self):
        pedidos = []

        def falso(url, *a, **k):
            pedidos.append(url)
            return _pagina()
        with mock.patch.object(cinemark, "get", falso):
            out = cinemark.funciones("caballito")
        self.assertEqual(pedidos, ["https://www.cinemark.com.ar/cartelera/caballito"])
        self.assertTrue(out)
        dia = sorted(out)[0]
        self.assertRegex(dia, r"^\d{4}-\d\d-\d\d$")
        for pelis in out.values():
            for t, r in pelis.items():
                self.assertTrue(r["horas"])
                self.assertTrue(all(len(h) == 5 for h in r["horas"]))
                self.assertTrue(r["slug_pelicula"])

    def test_pagina_sin_bloque(self):
        with mock.patch.object(cinemark, "get", lambda *a, **k: "<html></html>"):
            self.assertEqual(cinemark.funciones("x"), {})
