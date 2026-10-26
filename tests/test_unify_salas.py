"""unify.construir con el padron: ids de sala y no regresion contra el construir de main."""
import unittest

from carteleras import salas, unify
from tests import _datos, legacy_unify

RENOMBRE = {"cinemark": "cinemark-caballito", "hoyts": "hoyts-abasto",
            "atlas": "atlas-caballito", "gaumont": "gaumont"}


def _por_id():
    return {s["id"]: s for s in salas.cargar()}


class TestUnifySalas(unittest.TestCase):
    def setUp(self):
        self.d = _datos.crudos_4_salas()
        self.padron = _por_id()

    def _crudos(self):
        return [(self.padron["cinemark-caballito"], self.d["ck"]),
                (self.padron["hoyts-abasto"], self.d["ab"]),
                (self.padron["atlas-caballito"], self.d["atlas"]),
                (self.padron["gaumont"], self.d["gaumont"])]

    def test_misma_pelicula_en_cuatro_salas(self):
        films = unify.construir(self._crudos(), self.d["fichas"], self.d["dias"])
        dune = films["DUNE 3"]
        self.assertEqual(set(dune["cines"]), set(RENOMBRE.values()))
        self.assertEqual(len([k for k in films if k.startswith("DUNE")]), 1)

    def test_dos_salas_cinemark_con_ids_del_padron(self):
        crudos = [(self.padron["cinemark-caballito"], self.d["ck"]),
                  (self.padron["cinemark-palermo"], self.d["ab"])]
        films = unify.construir(crudos, self.d["fichas"], self.d["dias"])
        self.assertEqual(set(films["DUNE 3"]["cines"]), {"cinemark-caballito", "cinemark-palermo"})
        self.assertEqual(set(films["SOLO CINEMARK"]["cines"]), {"cinemark-caballito"})

    def test_no_regresion_contra_main(self):
        nuevo = unify.construir(self._crudos(), self.d["fichas"], self.d["dias"])
        viejo = legacy_unify.construir(self.d["ck"], self.d["ab"], self.d["fichas"],
                                       self.d["atlas"], self.d["gaumont"], self.d["dias"])
        for f in viejo.values():
            f["cines"] = {RENOMBRE[c]: v for c, v in f["cines"].items()}
        self.assertEqual(nuevo, viejo)
        self.assertTrue(len(viejo) >= 3)

    def test_dia_fuera_de_ventana_no_entra(self):
        films = unify.construir(self._crudos(), self.d["fichas"], self.d["dias"])
        self.assertNotIn("FUERA DE VENTANA", films)
