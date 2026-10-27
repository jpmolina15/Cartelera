"""run.main() con las fuentes nuevas y red falsa: ventana por fecha de BA, respaldo de Atlas,
dataset con alcance / cobertura / dias_con_datos."""
import contextlib
import datetime
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import run
from tests import _datos

HOY = datetime.date(2026, 10, 26)  # lunes


def _vacia_diaria():
    return {"cerrado_hoy": False, "peliculas": []}


class TestRunFuentes(unittest.TestCase):
    def _correr(self, relevar, hoy=HOY):
        tmp = pathlib.Path(tempfile.mkdtemp())
        out, err = io.StringIO(), io.StringIO()
        args = ["run.py", "--sin-puntajes", "--salida", str(tmp / "c.html"), "--json", str(tmp / "d.json")]
        d = _datos.crudos_4_salas()
        with mock.patch.object(run, "RELEVAR", relevar), mock.patch.object(run, "hoy_ba", return_value=hoy), \
                mock.patch.object(run.cinemark, "fichas", return_value=d["fichas"]), \
                mock.patch("sys.argv", args), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = run.main()
        return rc, json.loads((tmp / "d.json").read_text(encoding="utf-8")), out.getvalue(), err.getvalue(), tmp

    def _fuentes(self, **cambios):
        d = _datos.crudos_4_salas()
        base = {
            "cinemark": lambda cfg, hoy: d["ck"] if cfg["slug"] == "caballito" else {},
            "atlas": lambda cfg, hoy: d["atlas"],
            "unica": lambda cfg, hoy: (d["gaumont"] if "562" in cfg["url"] else {"encabezado": None, "peliculas": []})
            if cfg["modo"] == "semanal" else {
                "cerrado_hoy": False,
                "peliculas": [{"titulo": "PELI DIARIA", "horarios": [{"h": "18:00", "lang": "S"}]}]
                if "661" in cfg["url"] else []},
            "multiplex": lambda cfg, hoy: [{"complejo": "182", "dia": "2026-10-27", "h": "21:00", "fmt": "",
                                            "lang": "D", "titulo": "Peli Multiplex", "id": "1"}]
            if cfg["complejo"] == "Multiplex Belgrano" else [],
            "showcase": lambda cfg, hoy: [{"titulo": "Peli Showcase", "funciones": [{"h": "20:00", "fmt": "", "lang": "S"}]}],
        }
        base.update(cambios)
        return base

    def test_ventana_es_fecha_de_ba_mas_4_y_dataset_nuevo(self):
        rc, ds, out, err, _ = self._correr(self._fuentes())
        self.assertEqual(rc, 0)
        self.assertEqual(ds["days"], ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"])
        self.assertEqual(ds["hoy"], "2026-10-26")
        self.assertEqual(ds["salas"]["atlas-flores"]["dias_con_datos"], ["2026-10-26"])
        self.assertEqual((ds["salas"]["atlas-flores"]["alcance"], ds["salas"]["atlas-flores"]["cobertura"]),
                         ("dia", "parcial"))
        self.assertEqual(ds["salas"]["multiplex-belgrano"]["dias_con_datos"], ["2026-10-27"])
        self.assertEqual(ds["salas"]["showcase-belgrano"]["dias_con_datos"], ["2026-10-26"])
        self.assertTrue(ds["salas"]["atlas-flores"]["con_datos"])
        self.assertFalse(ds["salas"]["atlas-liniers"]["con_datos"])
        self.assertIn("atlas-liniers", ds["sin_datos"])
        self.assertIn("atlas-flores=1 dias=1 alcance=dia cobertura=parcial", out)
        self.assertIn("ATENCION sin_datos=", err)

    def test_cae_cinemark_y_el_resto_sale_igual(self):
        def roto(cfg, hoy):
            raise OSError("sin red")
        rc, ds, out, err, tmp = self._correr(self._fuentes(cinemark=roto))
        self.assertEqual(rc, 0)
        self.assertEqual(len(ds["days"]), 5)   # la ventana no depende de Cinemark
        self.assertIn("OSError", err)
        self.assertTrue(ds["salas"]["multiplex-belgrano"]["con_datos"])
        self.assertTrue((tmp / "c.html").stat().st_size > 1000)

    def test_ventana_cruza_mes(self):
        rc, ds, *_ = self._correr(self._fuentes(), hoy=datetime.date(2026, 10, 30))
        self.assertEqual(ds["days"][-1], "2026-11-03")

    def test_atlas_caballito_cae_a_unica_y_queda_parcial(self):
        fuentes = self._fuentes(atlas=lambda cfg, hoy: [])
        fuentes_unica = fuentes["unica"]
        fuentes["unica"] = lambda cfg, hoy: (
            {"cerrado_hoy": False, "peliculas": [{"titulo": "PELI RESPALDO", "horarios": [{"h": "17:00", "lang": "D"}]}]}
            if "419" in cfg["url"] else fuentes_unica(cfg, hoy))
        rc, ds, out, err, _ = self._correr(fuentes)
        s = ds["salas"]["atlas-caballito"]
        self.assertEqual((s["fuente"], s["alcance"], s["cobertura"]), ("unica", "dia", "parcial"))
        self.assertEqual(s["dias_con_datos"], ["2026-10-26"])
        self.assertIn("respaldo", out)

    def test_atlas_caballito_con_api_sigue_completa_y_semanal(self):
        rc, ds, *_ = self._correr(self._fuentes())
        s = ds["salas"]["atlas-caballito"]
        self.assertEqual((s["fuente"], s["alcance"], s["cobertura"]), ("atlas", "semana", "completa"))

    def test_cerrado_hoy_no_es_sin_datos(self):
        fuentes = self._fuentes()
        fuentes["unica"] = lambda cfg, hoy: {"cerrado_hoy": True, "peliculas": []} \
            if "719" in cfg["url"] else (fuentes_u(cfg, hoy))
        fuentes_u = self._fuentes()["unica"]
        rc, ds, out, err, _ = self._correr(fuentes)
        self.assertIn("cerrado_hoy=atlas-alcorta", out)
        self.assertNotIn("atlas-alcorta", err)

    def test_multiplex_error_se_informa_y_no_frena(self):
        def malo(cfg, hoy):
            raise ValueError("multiplex: la página no trae complejos")
        rc, ds, out, err, _ = self._correr(self._fuentes(multiplex=malo))
        self.assertEqual(rc, 0)
        self.assertIn("ERROR: multiplex-belgrano", err)
        self.assertIn("multiplex-belgrano", ds["sin_datos"])
        self.assertTrue(ds["salas"]["showcase-belgrano"]["con_datos"])

    def test_plantilla_trae_las_cadenas_y_dominios_nuevos(self):
        _, _, _, _, tmp = self._correr(self._fuentes())
        html = (tmp / "c.html").read_text(encoding="utf-8")
        for texto in ("multiplex.com.ar", "todoshowcase.com", "unica-cartelera.com.ar", "c-multiplex",
                      "c-showcase", "c-cinepolis", "c-cosmos"):
            self.assertIn(texto, html)


if __name__ == "__main__":
    unittest.main()
