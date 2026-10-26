# Carteleras

Releva la cartelera semanal de las salas de CABA del padrón `data/salas.json` y
publica una web con tres vistas: **Películas**, **Por cine** y **Calendario**.

Salas hoy (8): Cinemark Caballito, Hoyts Abasto, Hoyts DOT, Cinemark Palermo,
Cinemark Puerto Madero, Cinemark Parque Brown, Atlas Caballito y Cine Gaumont
(Espacio INCAA Km 0). Cada sala tiene id, barrio, comuna, coordenadas, cadena
(define el color), `fuente` (módulo de `carteleras/sources/`) y `cfg` (parámetros
para ese módulo). `activa: false` saca una sala de la corrida sin borrarla.
`carteleras/salas.py` valida el padrón y `run.py` aborta si es inválido.
Para agregar una sala de una fuente existente alcanza con una entrada nueva en el JSON.

Sólo biblioteca estándar de Python 3. Sin dependencias, sin claves de API.

```bash
python3 run.py                      # releva todo y genera salida/cartelera.html + salida/datos.json
python3 run.py --salida salida/cartelera-caba.html --json salida/datos-caba.json   # para probar sin pisar lo de la rutina
python3 run.py --sin-puntajes       # más rápido, sin consultar TMDb
python3 -m unittest discover -s tests -t .
node --test tests/js/*.test.js     # funciones puras de filtros (bloque al principio de templates/app.js)
```

Tests (ninguno sale a la red): `test_parsers.py` (parsers frágiles),
`test_salas.py` (padrón), `test_unify_salas.py` (cruce por sala y no regresión
contra `tests/legacy_unify.py`, el `construir` de `main` con 4 salas fijas),
`test_cinemark_fixture.py` (JSON-LD real recortado en `tests/fixtures/`).

`run.py` imprime un resumen al final (películas por sala, cuántas con puntaje,
pedidos HTTP y duración) y escribe en stderr `ATENCION sin_datos=<ids de sala>`
si alguna quedó en cero, o `ATENCION sin_puntajes=<tmdb|rt>` si un proveedor de
puntajes no devolvió ninguno.

## De dónde sale cada dato

| Sala | Fuente | Cómo |
|---|---|---|
| Cinemark y Hoyts (6 salas) | `cinemark.com.ar` | JSON-LD renderizado del lado del servidor en `/cartelera/<slug>` (una página por sala, en serie); la ficha en el payload de Next.js de `/pelicula/<slug>` (máx. 4 en paralelo) |
| Atlas | `atlascines.com` | API interna sin auth (`GetFechasDisponibles`, `GetCacheFuncionesComplejoPeliculaFecha`), complejo 191 (`cfg.complejo` en el padrón) |
| Gaumont | `www.unica-cartelera.com.ar` | Programación semanal en prosa, parseada por `expandir_semana` |
| Puntajes | `themoviedb.org` | Búsqueda + ficha, **verificando el director** |
| Puntajes | `rottentomatoes.com` | Tomatómetro y público; requiere headers de navegador completos |

## Dominios que el entorno tiene que permitir

```
*.cinemark.com.ar
*.atlascines.com
*.unica-cartelera.com.ar     <- con www; el dominio pelado devuelve 403
*.themoviedb.org
*.rottentomatoes.com
*.frame.claudeusercontent.com <- para releer el artifact antes de republicarlo
```

**IMDb y Letterboxd no se pueden usar aunque el dominio esté permitido.** No es
un problema de lista blanca sino de los sitios: `imdb.com` responde 202 con un
cuerpo de ~2 KB (desafío de bots) y `letterboxd.com` responde 403. Habría que
usar una API con clave, y hoy el proyecto no usa ninguna. Las películas
argentinas del Gaumont además casi no figuran en Rotten Tomatoes, así que para
ésas TMDb era la única fuente.

**Desde la corrida del 06/10/2026 TMDb cayó en la misma bolsa.**
`themoviedb.org` empezó a responder 403 con el interstitial de Cloudflare
("Just a moment..."), tanto en la búsqueda como en la ficha, y no alcanza con
mandar headers completos de navegador como en Rotten Tomatoes: se probó y
sigue dando 403. `api.themoviedb.org` responde 401 porque pide clave. Mientras
dure, la web sale sólo con los puntajes de Rotten Tomatoes y las películas
argentinas del Gaumont quedan sin ninguno. Salir de esto implica una API con
clave, que es una decisión de diseño que hoy el proyecto no tomó.

**WebFetch está bloqueado aunque el tráfico directo pase.** Por eso todo el
código usa `urllib` y no WebFetch.

## Cosas que se rompen y cómo se arreglan

**Una película aparece duplicada.** Cada cine la nombra distinto y la
normalización no alcanzó. Agregar una entrada a `ALIAS` en
`carteleras/unify.py`. Ya están cargados los dos casos conocidos: *Harry
Potter 25° Aniversario* y *La noche del demonio 6*.

**Una sala aparece en cero.** Casi nunca es que no haya funciones: o cambió la
estructura del sitio, o el dominio se cayó de la lista blanca. `run.py` lo
avisa por stderr.

**Un proveedor de puntajes queda en cero.** Mismo síntoma y misma causa: el
sitio cambió o empezó a servir un desafío de bots. `run.py` avisa con
`ATENCION sin_puntajes=<proveedor>`. Conviene verificarlo a mano antes de tocar
los parsers: si `urllib` ya recibe un 403 o un cuerpo de "Just a moment...",
el problema no está en las expresiones regulares.

**Los horarios del Gaumont salen mal.** Es la fuente más frágil porque viene en
prosa. Los tests de `tests/test_parsers.py` cubren los tres casos que ya
fallaron una vez; agregar el nuevo caso ahí antes de tocar el parser.

**Otras rarezas conocidas, ya contempladas:**

- Cinemark emite `startDate` con zona horaria malformada (`...Z-03:00`). La `Z`
  es un bug del sitio: la hora de pared ya es local de Buenos Aires.
- Atlas trunca los títulos a 30 caracteres en el listado.
- Cinemark pega palabras en las sinopsis (`un librosobre`); Atlas se come el
  espacio tras las comas. Se prefiere el texto de Atlas y se corrige sólo lo
  que se puede corregir sin adivinar.
- Cinemark y Hoyts **no informan idioma por función**, sólo los idiomas
  disponibles por película: la letra D/S sólo se muestra si hay uno solo.
- La ventana de días la define lo que publica Cinemark, no es una elección.

## Prompt de la rutina

```
Actualizar la cartelera semanal de cuatro cines de Buenos Aires.

1. Ejecutar en el repo clonado:
       python3 run.py
   Usa urllib, NO WebFetch (WebFetch está bloqueado en este entorno).
   Leer el resumen que imprime al final.

2. Si el resumen trae "ATENCION sin_datos=<sala>", NO abortar: publicar
   igual con las salas que sí se relevaron y decir cuáles faltaron y por qué.
   Nunca inventar horarios ni reutilizar los de la semana pasada.

3. Publicar salida/cartelera.html en el artifact YA EXISTENTE, sin crear
   uno nuevo:
   - primero leerlo con action "read" y esta url:
     https://claude.ai/code/artifact/48264826-0395-45e1-a12b-3c4d86dd2d8d
   - después republicar sobre esa MISMA url pasándola como `url`.

4. Avisar con PushNotification dentro de <routine_summary>. Primera oración:
   cuántas películas hay y si hubo estrenos. Después: el link a la página,
   los títulos mejor puntuados y cualquier sala que haya quedado sin datos.
```

El paso 3 no es opcional: si se publica sin pasar `url`, se crea una página
nueva con otra dirección y el link anclado queda congelado en la versión vieja.
