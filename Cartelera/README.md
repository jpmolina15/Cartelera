# Carteleras

Releva la cartelera semanal de cuatro salas de Buenos Aires y publica una web
con tres vistas: **Películas**, **Por cine** y **Calendario**.

- Cinemark Caballito — Av. La Plata 96
- Hoyts Abasto — Shopping Abasto
- Atlas Caballito — Av. Rivadavia 5071
- Cine Gaumont (Espacio INCAA Km 0) — Av. Rivadavia 1635

Sólo biblioteca estándar de Python 3. Sin dependencias, sin claves de API.

```bash
python3 run.py                      # releva todo y genera salida/cartelera.html
python3 run.py --sin-puntajes       # más rápido, sin consultar TMDb
python3 -m unittest discover -s tests -t .
```

`run.py` imprime un resumen al final (películas por sala, cuántas con puntaje)
y escribe `ATENCION sin_datos=<sala>` en stderr si alguna quedó en cero.

## De dónde sale cada dato

| Sala | Fuente | Cómo |
|---|---|---|
| Cinemark, Hoyts | `cinemark.com.ar` | JSON-LD renderizado del lado del servidor en `/cartelera/<slug>`; la ficha en el payload de Next.js de `/pelicula/<slug>` |
| Atlas | `atlascines.com` | API interna sin auth (`GetFechasDisponibles`, `GetCacheFuncionesComplejoPeliculaFecha`), complejo 191 |
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
ésas TMDb sigue siendo la única fuente.

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
