"""Tests de los parseos frágiles. No tocan la red.

    python3 -m unittest discover -s tests -v

Cubren los tres errores que ya aparecieron una vez en producción:
  1. lista de horarios con un único "hs" al final
  2. excepciones del Gaumont por día y por día+horario
  3. títulos que cada cine escribe distinto
"""
import datetime
import unittest

from carteleras import fechas
from carteleras.sources.gaumont import expandir_semana
from carteleras.unify import clave, limpiar

# sáb 29 ago 2026 .. mié 2 sep 2026
DIAS = ["2026-08-29", "2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02"]
DOW = {d: datetime.date(*map(int, d.split("-"))).weekday() for d in DIAS}
SAB, DOM, LUN, MAR, MIE = DIAS


class TestGaumont(unittest.TestCase):
    def test_lista_con_un_solo_hs(self):
        # "14.30, 17.15 y 22 hs." -> los tres, no sólo el último
        r = expandir_semana("14.30, 17.15 y 22 hs.", DIAS, DOW)
        self.assertEqual(r[SAB], ["14:30", "17:15", "22:00"])

    def test_dos_horarios(self):
        r = expandir_semana("14.45 y 19.30 hs.", DIAS, DOW)
        self.assertEqual(r[SAB], ["14:45", "19:30"])

    def test_hora_sin_minutos(self):
        self.assertEqual(expandir_semana("17 hs.", DIAS, DOW)[SAB], ["17:00"])

    def test_excepcion_dia_entero(self):
        r = expandir_semana('16.30 hs. Ciclo "Horizontes" (Martes no hay función)', DIAS, DOW)
        self.assertNotIn(MAR, r)
        self.assertEqual(r[SAB], ["16:30"])

    def test_excepcion_por_dia_y_horario(self):
        # el martes pierde 17.15 pero conserva 14.30 y 22
        r = expandir_semana(
            "14.30, 17.15 y 22 hs. (Viernes: 22 hs. y Martes: 17.15 hs. no hay función)",
            DIAS, DOW)
        self.assertEqual(r[MAR], ["14:30", "22:00"])
        self.assertEqual(r[SAB], ["14:30", "17:15", "22:00"])

    def test_funcion_de_un_solo_dia(self):
        r = expandir_semana('Martes: 22 hs. Ciclo "Km.Cero"', DIAS, DOW)
        self.assertEqual(list(r), [MAR])

    def test_dia_fuera_de_la_ventana(self):
        # una función sólo de viernes no debe aparecer en sáb..mié
        self.assertEqual(expandir_semana("Viernes: 21.45 hs.", DIAS, DOW), {})


class TestSemana(unittest.TestCase):
    def test_arranca_el_jueves(self):
        # jue 10 sep 2026: la semana es la que empieza ese mismo día
        r = fechas.semana(datetime.date(2026, 9, 10))
        self.assertEqual(r[0], "2026-09-10")
        self.assertEqual(r[-1], "2026-09-16")
        self.assertEqual(len(r), 7)

    def test_el_miercoles_sigue_en_la_semana_anterior(self):
        # mié 16 sep cierra la semana del jueves 10, no abre la del 17
        self.assertEqual(fechas.semana(datetime.date(2026, 9, 16))[0], "2026-09-10")
        self.assertEqual(fechas.semana(datetime.date(2026, 9, 17))[0], "2026-09-17")

    def test_cruce_de_mes(self):
        r = fechas.semana(datetime.date(2026, 10, 3))
        self.assertEqual(r[0], "2026-10-01")
        self.assertEqual(r[-1], "2026-10-07")

    def test_ventana_descarta_los_dias_pasados(self):
        # dom 13 sep: quedan domingo a miércoles de esa semana
        self.assertEqual(fechas.ventana(datetime.date(2026, 9, 13)),
                         ["2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"])

    def test_ventana_completa_si_se_corre_el_jueves(self):
        self.assertEqual(fechas.ventana(datetime.date(2026, 9, 10)),
                         fechas.semana(datetime.date(2026, 9, 10)))


class TestClaves(unittest.TestCase):
    def test_acentos_y_puntuacion(self):
        self.assertEqual(clave("SPIDER-MAN: UN NUEVO DÍA"),
                         clave("SPIDER-MAN: UN NUEVO DIA"))
        self.assertEqual(clave("YO, NARCISO"), clave("YO,NARCISO"))
        self.assertEqual(clave("SÓLO POR UNA NOCHE"), clave("SOLO POR UNA NOCHE"))

    def test_alias_de_titulos_distintos(self):
        self.assertEqual(clave("HARRY POTTER Y LA PIEDRA FILOS"),
                         clave("HARRY POTTER 25° ANIVERSARIO"))
        self.assertEqual(clave("LA NOCHE DEL DEMONIO:ESTAN ENT"),
                         clave("LA NOCHE DEL DEMONIO 6"))

    def test_no_junta_peliculas_distintas(self):
        self.assertNotEqual(clave("TOY STORY 5"), clave("TOY STORY 4"))


class TestLimpiar(unittest.TestCase):
    def test_espacio_tras_coma(self):
        self.assertEqual(limpiar("Oreiro,profesora"), "Oreiro, profesora")

    def test_espacio_tras_punto(self):
        self.assertEqual(limpiar("plástico.Bajo"), "plástico. Bajo")

    def test_no_inventa_cortes_dentro_de_palabra(self):
        # "librosobre" no se puede arreglar sin adivinar: debe quedar igual
        self.assertEqual(limpiar("un librosobre el tema"), "un librosobre el tema")


if __name__ == "__main__":
    unittest.main()
