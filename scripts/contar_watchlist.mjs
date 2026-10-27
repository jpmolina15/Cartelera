// Uso: node scripts/contar_watchlist.mjs <export.zip|watchlist.csv> <salida/datos-caba.json>
// Imprime SOLO: filas leídas, matches (título de cartel + año TMDb) y cuántas no se cruzaron.
// No imprime nombres de archivo ni títulos de la watchlist que no cruzaron.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const CF = require(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'templates', 'app.js'));
const [, , archivo, datos] = process.argv;
if (!archivo || !datos) { console.error('Uso: node scripts/contar_watchlist.mjs <zip|csv> <datos-caba.json>'); process.exit(2); }
try {
  const films = JSON.parse(readFileSync(datos, 'utf-8')).films;
  const filas = await CF.WL.leerArchivo(new Blob([readFileSync(archivo)]));
  const r = CF.WL.cruzarWatchlist(filas, films);
  console.log(`filas leídas: ${filas.length}`);
  console.log(`matches: ${r.matches.length}`);
  for (const m of r.matches) console.log(`  ${m.titulo} (${m.anio})`);
  console.log(`no cruzadas: ${r.noCruzadas.length}`);
} catch (e) {
  console.error('Error: ' + CF.WL.mensaje(e));
  process.exit(1);
}
