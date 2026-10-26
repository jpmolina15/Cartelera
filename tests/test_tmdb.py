"""TMDb por API: matching, caché, errores y anti-fuga del token. Nada sale a la red.

Las respuestas de tests/fixtures/tmdb/ tienen la forma documentada de la API v3
(search/movie y movie/{id}?append_to_response=credits,translations).
"""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
import urllib.error
from unittest import mock

import run
from carteleras import http, render, salas, tmdb
from tests import _datos

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "tmdb"
TOKEN_FALSO = "eyJTOKEN.FALSO.zzz-4815162342"

BUSQUEDAS = {  # consulta (normalizada) -> fixture
    "OPPENHEIMER": "search_oppenheimer", "THE ODYSSEY": "search_odyssey",
    "EL ULTIMO TREN A MENDOZA": "search_argentina", "LA CASA": "search_la_casa",
    "CARS": "search_cars", "ESTRELLAS WORLD TOUR": "search_evento",
    "CORTO LARGO": "search_pocos", "DUNE PART THREE": "search_dune"}


def _json(nombre):
    return json.loads((FIX / f"{nombre}.json").read_text(encoding="utf-8"))


class FalsaAPI:
    """Reemplaza Cliente._pedir: sirve fixtures y cuenta los pedidos por ruta."""

    def __init__(self, status=200):
        self.llamadas, self.status = [], status

    def __call__(self, ruta, params):
        self.llamadas.append((ruta, dict(params)))
        if self.status != 200:
            return self.status, _json("error_401")
        if ruta == "/search/movie":
            nombre = BUSQUEDAS.get(tmdb.norm(params["query"]))
            return (200, _json(nombre)) if nombre else (200, {"page": 1, "results": []})
        mid = ruta.rsplit("/", 1)[1]
        f = FIX / f"movie_{mid}.json"
        return (200, _json(f.stem)) if f.exists() else (404, None)

    def n(self, ruta=None):
        return sum(1 for r, _ in self.llamadas if ruta is None or r == ruta)


def pelicula(titulo, **kw):
    f = {"key": titulo, "titulo": titulo, "director": None, "anio": None,
         "original": None, "genero": None}
    f.update(kw)
    return f


def resolver(films, cache=None, api=None, token=TOKEN_FALSO):
    api = api or FalsaAPI()
    cache = {} if cache is None else cache
    res, st = tmdb.resolver(films, cache, token, pedir=api, workers=1)
    return res, st, cache, api


class TestMatching(unittest.TestCase):
    def test_match_limpio_y_dos_pedidos(self):
        films = {"OPPENHEIMER": pelicula("OPPENHEIMER", director="Christopher Nolan", anio="2023")}
        res, st, cache, api = resolver(films)
        r = res["OPPENHEIMER"]
        self.assertEqual((r["tmdb_id"], r["verif"], r["score"], r["anio_tmdb"]),
                         ("872585", "director", 8.1, "2023"))
        self.assertEqual(r["titulo_en"], "Oppenheimer")
        self.assertEqual(api.n(), 2)  # 1 search + 1 ficha
        self.assertEqual(cache["OPPENHEIMER"]["director_cine"], "Christopher Nolan")
        self.assertEqual(cache["OPPENHEIMER"]["tmdb_id"], "872585")

    def test_ficha_pide_ingles_credits_y_translations(self):
        _, _, _, api = resolver({"O": pelicula("OPPENHEIMER", director="Nolan")})
        ruta, params = [x for x in api.llamadas if x[0].startswith("/movie/")][0]
        self.assertEqual(params, {"language": "en-US", "append_to_response": "credits,translations"})
        busq = [p for r, p in api.llamadas if r == "/search/movie"][0]
        self.assertEqual(busq["language"], "es-AR")

    def test_homonimas_gana_la_del_director(self):
        films = {"THE ODYSSEY": pelicula("THE ODYSSEY", director="Christopher Nolan", anio="2026")}
        res, st, _, api = resolver(films)
        self.assertEqual(res["THE ODYSSEY"]["tmdb_id"], "900001")
        self.assertLessEqual(api.n(), 4)  # 1 search + hasta 3 fichas
        # título local: no hay es-AR, cae a es-MX
        self.assertEqual(res["THE ODYSSEY"]["titulo_local"], "La Odisea")

    def test_homonimas_con_otro_director_no_matchea(self):
        films = {"THE ODYSSEY": pelicula("THE ODYSSEY", director="Alguien Distinto", anio="2026")}
        res, *_ = resolver(films)
        self.assertEqual(res, {})

    def test_argentina_sin_director_titulo_exacto_y_anio(self):
        films = {"X": pelicula("EL ÚLTIMO TREN A MENDOZA", anio="2026")}
        res, st, _, api = resolver(films)
        self.assertEqual(res["X"]["tmdb_id"], "910001")
        self.assertEqual(res["X"]["verif"], "titulo")
        self.assertEqual(res["X"]["titulo_en"], "The Last Train to Mendoza")
        self.assertEqual(api.n(), 2)

    def test_sin_subcadena_la_casa(self):
        res, *_ = resolver({"LA CASA": pelicula("LA CASA", anio="2026")})
        self.assertEqual(res, {})

    def test_reestreno_unico_exacto_sin_anio(self):
        films = {"CARS": pelicula("CARS 20 ANIVERSARIO", anio="2026")}
        res, *_ = resolver(films)
        self.assertEqual(res["CARS"]["tmdb_id"], "920")
        self.assertEqual(res["CARS"]["anio_tmdb"], "2006")

    def test_evento_solo_titulo_exacto(self):
        films = {"E": pelicula("ESTRELLAS WORLD TOUR", genero="Recital", director="Otro Nombre")}
        res, *_ = resolver(films)
        self.assertEqual(res["E"]["verif"], "evento")
        # sin título exacto en TMDb: nada
        films = {"E": pelicula("ESTRELLAS WORLD TOUR EN VIVO", genero="Musical")}
        res, *_ = resolver(films)
        self.assertEqual(res, {})

    def test_score_solo_con_20_votos(self):
        res, st, *_ = resolver({"C": pelicula("CORTO LARGO", anio="2026")})
        self.assertEqual(res["C"]["tmdb_id"], "940001")
        self.assertIsNone(res["C"]["score"])
        self.assertEqual(st["sin_score_votos"], 1)

    def test_titulo_local_prefiere_es_ar(self):
        films = {"CARS": pelicula("CARS", anio="2006")}
        res, *_ = resolver(films)
        self.assertEqual(res["CARS"]["titulo_local"], "Cars: Ruedas")


class TestCache(unittest.TestCase):
    def test_cache_hit_un_solo_pedido_y_sin_busqueda(self):
        films = {"OPPENHEIMER": pelicula("OPPENHEIMER", director="Christopher Nolan", anio="2023")}
        _, _, cache, _ = resolver(films)
        res, st, _, api = resolver(films, cache)
        self.assertEqual(api.n("/search/movie"), 0)
        self.assertEqual(api.n(), 1)
        self.assertEqual(st["cache"], 1)
        self.assertEqual(res["OPPENHEIMER"]["score"], 8.1)  # puntaje fresco, no guardado

    def test_cache_sin_puntajes_guardados(self):
        films = {"OPPENHEIMER": pelicula("OPPENHEIMER", director="Christopher Nolan", anio="2023")}
        _, _, cache, _ = resolver(films)
        self.assertNotIn("score", json.dumps(cache))
        self.assertNotIn("vote", json.dumps(cache))

    def test_invalida_si_cambia_director_o_anio(self):
        films = {"THE ODYSSEY": pelicula("THE ODYSSEY", director="Christopher Nolan", anio="2026")}
        _, _, cache, _ = resolver(films)
        films["THE ODYSSEY"]["director"] = "Otro Director"
        res, st, cache2, api = resolver(films, cache)
        self.assertEqual(st["cache"], 0)
        self.assertGreater(api.n("/search/movie"), 0)
        self.assertEqual(res["THE ODYSSEY"]["tmdb_id"], "900002")

    def test_manual_no_se_sobreescribe(self):
        films = {"THE ODYSSEY": pelicula("THE ODYSSEY", director="Christopher Nolan", anio="2026")}
        cache = {"THE ODYSSEY": {"tmdb_id": "900002", "verif": "manual", "titulo_local": "A mano",
                                 "director_cine": "otro", "anio_cine": "1999"}}
        copia = json.loads(json.dumps(cache))
        res, st, cache, api = resolver(films, cache)
        self.assertEqual(res["THE ODYSSEY"]["tmdb_id"], "900002")  # no el 900001 del director
        self.assertEqual(res["THE ODYSSEY"]["titulo_local"], "A mano")
        self.assertEqual(api.n("/search/movie"), 0)
        self.assertEqual(cache, copia)
        self.assertEqual(st["verificadas"], 1)

    def test_guardar_solo_si_cambia(self):
        d = tempfile.mkdtemp()
        ruta = pathlib.Path(d) / "c.json"
        self.assertTrue(tmdb.guardar_cache({"A": {"tmdb_id": "1"}}, ruta))
        self.assertFalse(tmdb.guardar_cache({"A": {"tmdb_id": "1"}}, ruta))
        self.assertEqual(tmdb.cargar_cache(ruta), {"A": {"tmdb_id": "1"}})
        self.assertEqual(tmdb.cargar_cache(pathlib.Path(d) / "no.json"), {})


class TestErrores(unittest.TestCase):
    def test_sin_token_no_pide_y_usa_ids_de_cache(self):
        films = {"OPPENHEIMER": pelicula("OPPENHEIMER", director="Christopher Nolan", anio="2023")}
        _, _, cache, _ = resolver(films)
        api = FalsaAPI()
        res, st = tmdb.resolver(films, cache, "", pedir=api)
        self.assertEqual(api.n(), 0)
        self.assertEqual(res["OPPENHEIMER"]["tmdb_id"], "872585")
        self.assertIsNone(res["OPPENHEIMER"]["score"])

    def test_401_corta_y_marca_invalido(self):
        films = {f"P{i}": pelicula("OPPENHEIMER", director="Nolan") for i in range(5)}
        res, st, _, api = resolver(films, api=FalsaAPI(status=401))
        self.assertTrue(st["invalido"])
        self.assertEqual(res, {})
        self.assertLessEqual(api.n(), 1)  # workers=1: el primero corta al resto

    def test_http_429_espera_retry_after_y_reintenta(self):
        e429 = urllib.error.HTTPError("u", 429, "x", {"Retry-After": "1"}, io.BytesIO(b"{}"))
        ok = mock.MagicMock()
        ok.__enter__.return_value.read.return_value = b'{"a":1}'
        ok.__enter__.return_value.status = 200
        with mock.patch("urllib.request.urlopen", side_effect=[e429, e429, ok]) as u, \
                mock.patch("time.sleep") as sl:
            st, cuerpo = http.get("https://x.test/", con_status=True,
                                  headers={"Authorization": "Bearer t"})
        self.assertEqual((st, cuerpo), (200, '{"a":1}'))
        self.assertEqual(u.call_count, 3)  # intento original + 2 reintentos
        self.assertEqual([c.args[0] for c in sl.call_args_list], [1.0, 1.0])
        self.assertEqual(u.call_args.args[0].get_header("Authorization"), "Bearer t")

    def test_http_401_devuelve_status(self):
        e = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b'{"success":false}'))
        with mock.patch("urllib.request.urlopen", side_effect=e):
            self.assertEqual(http.get("https://x.test/", con_status=True), (401, '{"success":false}'))

    def test_get_clasico_sigue_igual(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError), mock.patch("time.sleep"):
            self.assertEqual(http.get("https://x.test/"), "")
            self.assertEqual(http.get("https://x.test/", con_status=True), (0, ""))


class TestCorridaCompleta(unittest.TestCase):
    """run.main() con salas y red falsas: sin token, con token inválido y anti-fuga."""

    def _correr(self, token, status=200):
        d = _datos.crudos_4_salas()
        tmp = pathlib.Path(tempfile.mkdtemp())
        api = FalsaAPI(status)
        env = {k: v for k, v in os.environ.items() if not k.startswith("TMDB_")}
        if token:
            env["TMDB_TOKEN"] = token
        relevar = {"cinemark": lambda cfg: d["ck"] if cfg["slug"] == "caballito" else {},
                   "atlas": lambda cfg: d["atlas"], "gaumont": lambda cfg: d["gaumont"]}
        vistos = {}

        def get_falso(url, **kw):
            vistos["headers"] = kw.get("headers")
            assert "api.themoviedb.org" in url
            self_url = url.split("?", 1)[0].replace(tmdb.BASE, "")
            from urllib.parse import parse_qsl, urlsplit
            st, data = api(self_url, dict(parse_qsl(urlsplit(url).query)))
            return st, json.dumps(data)

        out, err = io.StringIO(), io.StringIO()
        args = ["run.py", "--salida", str(tmp / "c.html"), "--json", str(tmp / "d.json"),
                "--cache-tmdb", str(tmp / "cache.json")]
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(run, "RELEVAR", relevar), \
                mock.patch.object(run.cinemark, "fichas", return_value=d["fichas"]), \
                mock.patch.object(run.rt, "puntaje", return_value=None), \
                mock.patch.object(http, "get", get_falso), \
                mock.patch("sys.argv", args), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = run.main()
        self.assertEqual(rc, 0)
        return tmp, out.getvalue(), err.getvalue(), api, vistos

    def test_sin_token_avisa_y_sigue(self):
        tmp, out, err, api, _ = self._correr("")
        self.assertIn("ATENCION sin_clave=tmdb", err)
        self.assertNotIn("sin_puntajes=tmdb", err)
        self.assertEqual(api.n(), 0)
        self.assertFalse((tmp / "cache.json").exists())
        self.assertIn("tmdb=0", out)
        self.assertTrue((tmp / "c.html").stat().st_size > 1000)

    def test_token_invalido_avisa(self):
        tmp, out, err, api, _ = self._correr(TOKEN_FALSO, status=401)
        self.assertIn("ATENCION clave_invalida=tmdb", err)
        self.assertFalse((tmp / "cache.json").exists())

    def test_con_token_completa_datos_y_no_filtra_el_token(self):
        tmp, out, err, api, vistos = self._correr(TOKEN_FALSO)
        self.assertEqual(vistos["headers"]["Authorization"], f"Bearer {TOKEN_FALSO}")
        datos = json.loads((tmp / "d.json").read_text(encoding="utf-8"))
        dune = datos["films"]["DUNE 3"]
        self.assertEqual((dune["tmdb_id"], dune["score"], dune["anio_tmdb"]), ("950001", 8.0, "2026"))
        self.assertEqual(dune["titulo_original"], "Dune Part Three")
        self.assertEqual(dune["titulo_en"], "Dune: Part Three")
        self.assertEqual(dune["titulo_local"], "Dune: Parte Tres")
        self.assertIn("tmdb_id=1/", out)
        html = (tmp / "c.html").read_text(encoding="utf-8")
        self.assertIn("letterboxd.com/tmdb/", html)
        self.assertIn("atribucion-tmdb", html)
        # anti-fuga: el token no aparece en stdout, stderr, HTML, JSON ni caché
        for nombre, texto in (("stdout", out), ("stderr", err), ("html", html),
                              ("json", (tmp / "d.json").read_text(encoding="utf-8")),
                              ("cache", (tmp / "cache.json").read_text(encoding="utf-8"))):
            self.assertNotIn(TOKEN_FALSO, texto, nombre)
            self.assertNotIn("Bearer", texto, nombre)


if __name__ == "__main__":
    unittest.main()
