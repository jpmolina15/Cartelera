"""--publicar: documento completo en DIR/index.html, aborto si no hay funciones, vercel.json valido."""
import contextlib
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import run
from tests import _datos
from tests.test_run_fuentes import HOY, TestRunFuentes

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ANTES, DESPUES = run.ENVOLTURA_ANTES, run.ENVOLTURA_DESPUES


class TestPublicar(unittest.TestCase):
    def _correr(self, relevar):
        tmp = pathlib.Path(tempfile.mkdtemp())
        d = _datos.crudos_4_salas()
        args = ["run.py", "--sin-puntajes", "--salida", str(tmp / "c.html"), "--json", str(tmp / "d.json"),
                "--publicar", str(tmp / "pub")]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(run, "RELEVAR", relevar), mock.patch.object(run, "hoy_ba", return_value=HOY), \
                mock.patch.object(run.cinemark, "fichas", return_value=d["fichas"]), \
                mock.patch("sys.argv", args), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = run.main()
        return rc, tmp, err.getvalue()

    def test_publicar_envuelve_el_mismo_cuerpo(self):
        rc, tmp, err = self._correr(TestRunFuentes()._fuentes())
        self.assertEqual(rc, 0)
        doc = (tmp / "pub" / "index.html").read_text(encoding="utf-8")
        salida = (tmp / "c.html").read_text(encoding="utf-8")
        self.assertTrue(doc.startswith("<!doctype html>"))
        self.assertIn('name="viewport"', doc)
        self.assertIn('name="robots" content="noindex"', doc)
        self.assertEqual(doc[len(ANTES):-len(DESPUES)], salida)
        self.assertNotIn("no_publicado", err)

    def test_sin_funciones_no_publica(self):
        vacias = {k: (lambda cfg, hoy, k=k: {} if k == "cinemark" else [] if k in ("atlas", "multiplex", "showcase")
                      else ({"encabezado": None, "peliculas": []} if cfg["modo"] == "semanal"
                            else {"cerrado_hoy": False, "peliculas": []}))
                  for k in ("cinemark", "atlas", "unica", "multiplex", "showcase")}
        rc, tmp, err = self._correr(vacias)
        self.assertEqual(rc, 0)
        self.assertFalse((tmp / "pub" / "index.html").exists())
        self.assertIn("ATENCION no_publicado", err)

    def test_vercel_json_valido(self):
        cfg = json.loads((RAIZ / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["outputDirectory"], "public")
        self.assertIsNone(cfg["buildCommand"])
        self.assertTrue(cfg["cleanUrls"])
        self.assertEqual(cfg["git"]["deploymentEnabled"], {"main": True, "*": False})
        claves = {h["key"] for h in cfg["headers"][0]["headers"]}
        self.assertIn("Content-Security-Policy", claves)

    def test_vercelignore_lista_blanca(self):
        lineas = (RAIZ / ".vercelignore").read_text().split()
        self.assertEqual(lineas, ["/*", "!public", "!vercel.json"])


if __name__ == "__main__":
    unittest.main()
