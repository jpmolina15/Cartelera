"""SPEC-02: unica (semanal y diario), Multiplex, Showcase y su cruce en unify. Sin red.

Muestras reales guardadas en tests/fixtures/fuentes/ (las de Multiplex y Showcase, recortadas).
"""
import datetime
import pathlib
import unittest
from unittest import mock

from carteleras import salas, unify
from carteleras.sources import cinemark, multiplex, showcase, unica

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "fuentes"


def leer(nombre):
    return (FIX / nombre).read_text(encoding="utf-8", errors="replace")


def padron(sid):
    return {s["id"]: s for s in salas.cargar()}[sid]


class TestUnicaDiario(unittest.TestCase):
    def test_atlas_flores_dos_peliculas_con_idioma(self):
        r = unica.parsear_diario(leer("unica-atlas-flores_dia-idioma.html"))
        self.assertEqual([p["titulo"] for p in r["peliculas"]], ["¿QUERÉS SER MI HIJO?", "STREET FIGHTER"])
        self.assertEqual(r["peliculas"][0]["horarios"],
                         [{"h": "18:20", "lang": "D"}, {"h": "20:30", "lang": "D"}])
        self.assertEqual([x["h"] for x in r["peliculas"][1]["horarios"]], ["17:00", "19:30"])
        self.assertEqual(r["peliculas"][0]["duracion"], 95)
        self.assertEqual(r["peliculas"][0]["director"], "Hernán Guerschuny")

    def test_cinepolis_tres_horarios_en_dos_grupos(self):
        r = unica.parsear_diario(leer("unica-cinepolis-recoleta_dia-idioma.html"))
        ballena = r["peliculas"][0]
        self.assertEqual(ballena["titulo"], "LA CAÍDA DE LA BALLENA")
        self.assertEqual(ballena["horarios"], [{"h": "14:30", "lang": "S"}, {"h": "17:00", "lang": "S"},
                                               {"h": "19:30", "lang": "S"}])
        self.assertNotIn("Buscar", [p["titulo"] for p in r["peliculas"]])

    def test_linea_de_horarios_suelta(self):
        self.assertEqual(unica.parsear_horarios_dia("17 hs. (Subt.); 14.30 y 19.30 hs. (Subt.)"),
                         [{"h": "14:30", "lang": "S"}, {"h": "17:00", "lang": "S"}, {"h": "19:30", "lang": "S"}])
        self.assertEqual(unica.parsear_horarios_dia("12.20, 15 y 22.50 hs. (Cast.)")[2],
                         {"h": "22:50", "lang": "D"})
        self.assertEqual(unica.parsear_horarios_dia("21 hs."), [{"h": "21:00", "lang": ""}])

    def test_cerrado_hoy(self):
        html = ('<h5 class="card-title">PELI</h5><p class="card-text text-center"><b>17 hs. (Cast.)</b></p>'
                '<p>Atención (Martes y miércoles cerrado)</p>')
        r = unica.parsear_diario(html)
        self.assertEqual(r["cerrado"], {"martes", "miercoles"})
        martes, jueves = datetime.date(2026, 10, 27), datetime.date(2026, 10, 29)
        with mock.patch.object(unica, "get", return_value=html):
            self.assertTrue(unica.diario("u", martes)["cerrado_hoy"])
            self.assertFalse(unica.diario("u", jueves)["cerrado_hoy"])

    def test_cerrado_hoy_deja_la_sala_sin_datos_ese_dia(self):
        dias = ["2026-10-27", "2026-10-28"]
        datos = {"cerrado_hoy": True, "peliculas": [{"titulo": "PELI", "horarios": [{"h": "17:00", "lang": "D"}]}]}
        films = unify.construir([(padron("atlas-flores"), datos)], {}, dias, "2026-10-27")
        self.assertEqual(films, {})


class TestUnicaSemanal(unittest.TestCase):
    def setUp(self):
        self.r = unica.parsear_semanal(leer("unica-cosmos-uba_semanal.html"))

    def test_encabezado_y_rango(self):
        self.assertEqual(self.r["encabezado"], "SEMANA DEL JUEVES 22 AL MIÉRCOLES 28 DE OCTUBRE")
        self.assertEqual(unica.rango_semana(self.r["encabezado"], datetime.date(2026, 10, 26)),
                         (datetime.date(2026, 10, 22), datetime.date(2026, 10, 28)))
        self.assertEqual(len(self.r["peliculas"]), 7)

    def test_rango_cruza_mes_y_anio(self):
        e = "SEMANA DEL JUEVES 29 DE OCTUBRE AL MIÉRCOLES 4 DE NOVIEMBRE"
        self.assertEqual(unica.rango_semana(e, datetime.date(2026, 10, 30)),
                         (datetime.date(2026, 10, 29), datetime.date(2026, 11, 4)))
        e = "SEMANA DEL JUEVES 31 DE DICIEMBRE AL MIÉRCOLES 6 DE ENERO"
        self.assertEqual(unica.rango_semana(e, datetime.date(2026, 12, 28)),
                         (datetime.date(2026, 12, 31), datetime.date(2027, 1, 6)))
        self.assertIsNone(unica.rango_semana("SEMANA RARA", datetime.date(2026, 10, 26)))
        self.assertIsNone(unica.rango_semana(None, datetime.date(2026, 10, 26)))

    def _dias_con_horarios(self, datos, hoy, dias):
        films = unify.construir([(padron("cosmos-uba"), datos)], {}, dias, hoy)
        return sorted({d for f in films.values() for v in f["cines"].values() for d in v})

    def test_lunes_cruza_el_jueves_no_pasa_del_miercoles(self):
        # corrida un lunes (26/10), ventana lun..vie: jueves 29 y viernes 30 son otra semana.
        dias = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]
        con_encabezado = self._dias_con_horarios(self.r, "2026-10-26", dias)
        self.assertEqual(con_encabezado, ["2026-10-26", "2026-10-27", "2026-10-28"])
        # sin encabezado legible: hasta el miércoles siguiente a la corrida
        sin = dict(self.r, encabezado=None)
        self.assertEqual(self._dias_con_horarios(sin, "2026-10-26", dias), con_encabezado)
        # y con un encabezado ilegible, igual
        self.assertEqual(self._dias_con_horarios(dict(self.r, encabezado="SEMANA ???"), "2026-10-26", dias),
                         con_encabezado)

    def test_encabezado_viejo_no_repite_la_semana(self):
        # el jueves 29 la página todavía dice «22 al 28»: ningún horario después del miércoles
        dias = ["2026-10-29", "2026-10-30", "2026-10-31"]
        self.assertEqual(self._dias_con_horarios(self.r, "2026-10-29", dias), [])

    def test_sin_encabezado_corrida_en_miercoles(self):
        self.assertEqual(unica.semana_por_defecto(datetime.date(2026, 10, 28)),
                         (datetime.date(2026, 10, 28), datetime.date(2026, 10, 28)))
        self.assertEqual(unica.semana_por_defecto(datetime.date(2026, 10, 29))[1], datetime.date(2026, 11, 4))

    def test_gaumont_sigue_funcionando_como_alias(self):
        from carteleras.sources import gaumont
        self.assertIs(gaumont.expandir_semana, unica.expandir_semana)


class TestMultiplex(unittest.TestCase):
    def setUp(self):
        self.p = multiplex.parsear(leer("multiplex-recorte.html"))

    def test_complejo_por_etiqueta(self):
        self.assertEqual(self.p["complejos"]["Multiplex Belgrano"], "182")
        self.assertEqual(self.p["complejos"]["Multiplex Lavalle"], "184")

    def test_titulo_idioma_formato_y_deduplicado(self):
        belgrano = [f for f in self.p["funciones"] if f["complejo"] == "182"]
        ids = [f["id"] for f in self.p["funciones"]]
        self.assertEqual(len(ids), len(set(ids)))           # la función repetida en la muestra se deduplicó
        duna = [f for f in belgrano if f["titulo"] == "Duna: Parte Tres"]
        self.assertTrue(duna and all(f["lang"] == "S" for f in duna))
        self.assertEqual(duna[0]["fmt"], "COMFORT PLUS 2D")
        espanol = [f for f in self.p["funciones"] if f["titulo"] == "La Caja Del Demonio"]
        self.assertTrue(all(f["lang"] == "D" and f["fmt"] == "" for f in espanol))   # 2D común queda vacío

    def test_noche_de_cine_usa_dia_y_no_dia_real(self):
        # 00:05 de la madrugada del 16/12: el sitio la lista en la noche del 15 (dia) con dia_real 16.
        f = next(f for f in self.p["funciones"] if f["id"] == "225531")
        self.assertEqual((f["dia"], f["h"]), ("2026-12-15", "00:05"))

    def test_cartelera_por_nombre_de_complejo(self):
        with mock.patch.object(multiplex, "get", return_value=leer("multiplex-recorte.html")), \
                mock.patch.dict(multiplex._MEMO, clear=True):
            belgrano = multiplex.cartelera("Multiplex Belgrano", "https://m.test/")
            lavalle = multiplex.cartelera("Multiplex Lavalle", "https://m.test/")
            self.assertTrue(belgrano and all(f["complejo"] == "182" for f in belgrano))
            self.assertTrue(lavalle and all(f["complejo"] == "184" for f in lavalle))
            with self.assertRaises(ValueError):
                multiplex.cartelera("Multiplex Marte", "https://m.test/")

    def test_pagina_sin_complejos_es_error_no_vacio(self):
        with mock.patch.object(multiplex, "get", return_value="<html>Just a moment...</html>"), \
                mock.patch.dict(multiplex._MEMO, clear=True):
            with self.assertRaises(ValueError):
                multiplex.cartelera("Multiplex Belgrano", "https://m.test/")

    def test_unify_recorta_a_la_ventana_y_ordena_trasnoche_al_final(self):
        dias = ["2026-12-15", "2026-12-16"]
        datos = [f for f in self.p["funciones"] if f["complejo"] == "182"] + \
                [dict(f, dia="2027-01-30") for f in self.p["funciones"][:1] if f["complejo"] == "182"]
        films = unify.construir([(padron("multiplex-belgrano"), datos)], {}, dias, "2026-12-15")
        av = films["AVENGERS DOOMSDAY"]["cines"]["multiplex-belgrano"]
        self.assertEqual(sorted(av), dias)
        self.assertEqual([r["h"] for r in av["2026-12-15"]], ["00:05"])
        self.assertEqual(av["2026-12-15"][0]["lang"], "S")
        con_todo = unify.construir([(padron("multiplex-belgrano"), self.p["funciones"])], {}, ["2026-12-15"], "2026-12-15")
        duna = con_todo["DUNA PARTE TRES"]["cines"]["multiplex-belgrano"]["2026-12-15"]
        self.assertEqual([r["h"] for r in duna], ["12:50", "19:00"])
        self.assertNotIn("multiplex-lavalle", con_todo["DUNA PARTE TRES"]["cines"])


class TestShowcase(unittest.TestCase):
    def test_parseo(self):
        r = showcase.parsear(leer("showcase-belgrano-recorte.html"))
        self.assertEqual(len(r), 8)
        poder = next(p for p in r if p["titulo"] == "El poder de la red")
        self.assertEqual((poder["duracion"], poder["clasificacion"]), (112, "G"))
        self.assertEqual([f["h"] for f in poder["funciones"]], ["16:40", "19:15", "21:50"])
        mi_hijo = next(p for p in r if p["titulo"] == "¿Querés ser mi hijo?")
        self.assertEqual([(f["h"], f["lang"]) for f in mi_hijo["funciones"]], [("19:55", "D"), ("22:10", "D")])

    def test_dos_idiomas_en_el_mismo_menu(self):
        # Observado en la web real: un solo <p> con una linea por idioma («2D-Doblada 17:10» / «2D-Subtitulado ...»)
        r = showcase.parsear(leer("showcase-belgrano-recorte.html"))
        clay = next(p for p in r if p["titulo"] == "Clayface")
        self.assertEqual(sorted((f["h"], f["lang"]) for f in clay["funciones"]),
                         [("15:05", "S"), ("17:10", "D"), ("17:40", "S"), ("20:10", "S"), ("22:35", "S")])
        sf = next(p for p in r if p["titulo"] == "Street Fighter")
        self.assertEqual([(f["h"], f["lang"]) for f in sf["funciones"]], [("17:15", "D"), ("19:40", "S")])

    def test_idioma_castellano_es_doblada(self):
        r = showcase.parsear(leer("showcase-belgrano-recorte.html"))
        langs = {f["lang"] for p in r for f in p["funciones"]}
        self.assertEqual(langs, {"S", "D"})

    def test_formato_distinto_de_2d_se_conserva(self):
        html = ('movie-guide-title">Peli</h4><p>Duración: 100 minutos</p>'
                '<ul class="dropdown-menu ulSelector menu-text"><p>3D-Castellano 18:00</p><p>2D-Subtitulado 21:00</p></ul>')
        r = showcase.parsear(html)
        self.assertEqual(r[0]["funciones"], [{"h": "18:00", "fmt": "3D", "lang": "D"},
                                             {"h": "21:00", "fmt": "", "lang": "S"}])

    def test_unify_solo_hoy(self):
        r = showcase.parsear(leer("showcase-belgrano-recorte.html"))
        dias = ["2026-10-27", "2026-10-28", "2026-10-29"]
        films = unify.construir([(padron("showcase-belgrano"), r)], {}, dias, "2026-10-27")
        self.assertEqual(len(films), 8)
        for f in films.values():
            self.assertEqual(list(f["cines"]["showcase-belgrano"]), ["2026-10-27"])
        clay = films["CLAYFACE"]["cines"]["showcase-belgrano"]["2026-10-27"]
        self.assertEqual([r["h"] for r in clay], ["15:05", "17:10", "17:40", "20:10", "22:35"])
        # si la fecha de la corrida no está en la ventana, no inventa un día
        self.assertEqual(unify.construir([(padron("showcase-belgrano"), r)], {}, dias, "2026-11-30"), {})


class TestUnicaDiarioEnUnify(unittest.TestCase):
    def test_solo_la_fecha_de_la_corrida(self):
        r = unica.parsear_diario(leer("unica-atlas-flores_dia-idioma.html"))
        dias = ["2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31"]
        films = unify.construir([(padron("atlas-flores"), r)], {}, dias, "2026-10-27")
        self.assertEqual(len(films), 2)
        for f in films.values():
            self.assertEqual(list(f["cines"]["atlas-flores"]), ["2026-10-27"])
        sf = films["STREET FIGHTER"]["cines"]["atlas-flores"]["2026-10-27"]
        self.assertEqual(sf, [{"h": "17:00", "fmt": "", "lang": "D"}, {"h": "19:30", "fmt": "", "lang": "D"}])


class TestDespacho(unittest.TestCase):
    def test_fuente_desconocida_es_error_y_no_cae_en_gaumont(self):
        s = dict(padron("gaumont"), fuente="inventada")
        with self.assertRaises(ValueError):
            unify.construir([(s, [])], {}, ["2026-10-27"], "2026-10-27")
        with self.assertRaises(ValueError):
            unify.construir([(dict(padron("gaumont"), cfg={"url": "x", "modo": "raro"}), [])],
                            {}, ["2026-10-27"], "2026-10-27")


class TestSinopsisCinemark(unittest.TestCase):
    def test_descarta_precio_y_textos_cortos(self):
        self.assertIsNone(cinemark.sinopsis_valida("$28"))
        self.assertIsNone(cinemark.sinopsis_valida("$28 de entrada y mucho mas texto que pasa los cuarenta caracteres"))
        self.assertIsNone(cinemark.sinopsis_valida("Una de dibujos."))
        self.assertIsNone(cinemark.sinopsis_valida(None))
        largo = "Un desierto, otro planeta y una historia que sigue de donde la dejo la anterior."
        self.assertEqual(cinemark.sinopsis_valida(largo + "\\n"), largo)


if __name__ == "__main__":
    unittest.main()
