"""Padron de salas. No toca la red."""
import copy
import json
import pathlib
import tempfile
import unittest

from carteleras import salas


class TestPadron(unittest.TestCase):
    def test_padron_real_carga(self):
        lista = salas.cargar()
        self.assertEqual(len(lista), 17)
        self.assertEqual(len({s["id"] for s in lista}), 17)
        self.assertEqual({s["fuente"] for s in lista},
                         {"cinemark", "atlas", "unica", "multiplex", "showcase"})

    def test_alcance_y_cobertura_del_padron_real(self):
        por_id = {s["id"]: s for s in salas.cargar()}
        for sid in ("atlas-flores", "atlas-liniers", "atlas-alcorta", "atlas-patio-bullrich", "cinepolis-recoleta"):
            self.assertEqual((por_id[sid]["fuente"], por_id[sid]["alcance"], por_id[sid]["cobertura"]),
                             ("unica", "dia", "parcial"), sid)
        self.assertEqual((por_id["showcase-belgrano"]["alcance"], por_id["showcase-belgrano"]["cobertura"]),
                         ("dia", "completa"))
        for sid in ("multiplex-belgrano", "multiplex-lavalle", "cosmos-uba", "gaumont", "cinemark-palermo"):
            self.assertEqual(por_id[sid]["alcance"], "semana", sid)
        # Atlas Caballito: primero la API; unica solo de respaldo (y entonces dia / parcial)
        ac = por_id["atlas-caballito"]
        self.assertEqual((ac["fuente"], ac["cfg"]["complejo"], ac["alcance"], ac["cobertura"]),
                         ("atlas", 191, "semana", "completa"))
        self.assertEqual((ac["cfg"]["respaldo"]["fuente"], ac["cfg"]["respaldo"]["cobertura"]), ("unica", "parcial"))
        self.assertEqual(por_id["cosmos-uba"]["cfg"]["modo"], "semanal")
        self.assertEqual(por_id["gaumont"]["cfg"]["modo"], "semanal")

    def test_lavalle_780_es_una_sola_sala(self):
        lavalle = [s for s in salas.cargar() if "Lavalle 780" in s["direccion"]]
        self.assertEqual([s["id"] for s in lavalle], ["multiplex-lavalle"])

    def test_alcance_y_cobertura_invalidos(self):
        for campo, malo in (("alcance", "mes"), ("cobertura", "total")):
            with self.assertRaises(salas.PadronInvalido):
                salas.cargar(self._con(lambda b: b[0].update({campo: malo})))
        for campo in ("alcance", "cobertura"):
            with self.assertRaises(salas.PadronInvalido):
                salas.cargar(self._con(lambda b: b[0].pop(campo)))

    def _con(self, cambio):
        base = json.loads(salas.RUTA.read_text(encoding="utf-8"))
        cambio(base)
        d = tempfile.mkdtemp()
        ruta = pathlib.Path(d) / "salas.json"
        ruta.write_text(json.dumps(base), encoding="utf-8")
        return ruta

    def test_id_repetido(self):
        ruta = self._con(lambda b: b[1].update(id=b[0]["id"]))
        with self.assertRaises(salas.PadronInvalido):
            salas.cargar(ruta)

    def test_fuera_de_caba(self):
        ruta = self._con(lambda b: b[0].update(lat=-34.9))
        with self.assertRaises(salas.PadronInvalido):
            salas.cargar(ruta)
        ruta = self._con(lambda b: b[0].update(lon=-58.2))
        with self.assertRaises(salas.PadronInvalido):
            salas.cargar(ruta)

    def test_campo_faltante_y_comuna_no_entera(self):
        with self.assertRaises(salas.PadronInvalido):
            salas.cargar(self._con(lambda b: b[0].pop("barrio")))
        with self.assertRaises(salas.PadronInvalido):
            salas.cargar(self._con(lambda b: b[0].update(comuna="Comuna 5")))

    def test_inactiva_se_saca(self):
        lista = salas.cargar(self._con(lambda b: b[0].update(activa=False)))
        self.assertEqual(len(lista), 16)

    def test_archivo_inexistente(self):
        with self.assertRaises(salas.PadronInvalido):
            salas.cargar("/no/existe/salas.json")
