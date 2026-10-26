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
        self.assertEqual(len(lista), 8)
        self.assertEqual(len({s["id"] for s in lista}), 8)
        self.assertEqual({s["fuente"] for s in lista}, {"cinemark", "atlas", "gaumont"})

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
        self.assertEqual(len(lista), 7)

    def test_archivo_inexistente(self):
        with self.assertRaises(salas.PadronInvalido):
            salas.cargar("/no/existe/salas.json")
