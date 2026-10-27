// Pruebas de la watchlist de Letterboxd (bloque puro de templates/app.js). Todo sintético: ningún dato real.
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const zlib = require('node:zlib');
const CF = require(path.join(__dirname, '..', '..', 'templates', 'app.js'));
const WL = CF.WL;

// ---- zip sintético ----
function crc32(buf) {
  let c, crc = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) { c = (crc ^ buf[i]) & 0xFF; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xEDB88320 : c >>> 1; crc = (crc >>> 8) ^ c; }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}
function zip(entradas, {metodo = 8, flags = 0, extra = 0, zip64 = false, comentario = ''} = {}) {
  const partes = [], cds = []; let off = 0;
  for (const [nombre, contenido, met = metodo] of entradas) {
    const nom = Buffer.from(nombre), datos = Buffer.from(contenido);
    const comp = met === 8 ? zlib.deflateRawSync(datos) : datos;
    const lh = Buffer.alloc(30 + nom.length + extra);
    lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(flags, 6); lh.writeUInt16LE(met, 8);
    lh.writeUInt32LE(crc32(datos), 14); lh.writeUInt32LE(comp.length, 18); lh.writeUInt32LE(datos.length, 22);
    lh.writeUInt16LE(nom.length, 26); lh.writeUInt16LE(extra, 28); nom.copy(lh, 30);
    const cd = Buffer.alloc(46 + nom.length);
    cd.writeUInt32LE(0x02014b50, 0); cd.writeUInt16LE(20, 4); cd.writeUInt16LE(20, 6); cd.writeUInt16LE(flags, 8); cd.writeUInt16LE(met, 10);
    cd.writeUInt32LE(crc32(datos), 16); cd.writeUInt32LE(comp.length, 20); cd.writeUInt32LE(datos.length, 24);
    cd.writeUInt16LE(nom.length, 28); cd.writeUInt32LE(off, 42); nom.copy(cd, 46);
    partes.push(lh, comp); cds.push(cd); off += lh.length + comp.length;
  }
  const cdBuf = Buffer.concat(cds), com = Buffer.from(comentario);
  const e = Buffer.alloc(22 + com.length);
  e.writeUInt32LE(0x06054b50, 0); e.writeUInt16LE(entradas.length, 8); e.writeUInt16LE(entradas.length, 10);
  e.writeUInt32LE(cdBuf.length, 12); e.writeUInt32LE(zip64 ? 0xFFFFFFFF : off, 16); e.writeUInt16LE(com.length, 20); com.copy(e, 22);
  return new Blob([Buffer.concat([...partes, cdBuf, e])]);
}
const CSV = 'Date,Name,Year,Letterboxd URI\r\n2024-01-01,"Paris, Texas",1984,https://boxd.it/a\r\n2024-01-02,Cars,2006,https://boxd.it/b\r\n';

// ---- parser CSV ----
test('parseCSV: BOM, CRLF, comillas con comas, comillas escapadas y saltos adentro', () => {
  const r = WL.parseCSV('﻿Name,Year\r\n"Paris, Texas",1984\r\n"Dice ""hola""\nmundo",2000\r\n\r\n');
  assert.deepStrictEqual(r, [['Name', 'Year'], ['Paris, Texas', '1984'], ['Dice "hola"\nmundo', '2000']]);
});
test('filasDeCSV: Name o Title, año vacío, tmdbID', () => {
  assert.deepStrictEqual(WL.filasDeCSV('Title,Year\nSolaris,\n'), [{name: 'Solaris', year: null, tmdb: null}]);
  const f = WL.filasDeCSV('Name,Year,tmdbID\nX,2001,603\n,1999,5\n');
  assert.deepStrictEqual(f, [{name: 'X', year: 2001, tmdb: '603'}]);
  assert.throws(() => WL.filasDeCSV('Foo,Bar\n1,2\n'), /Name o Title/);
});
test('filasDeCSV: más de 20.000 filas se rechaza', () => {
  const t = 'Name,Year\n' + 'a,2000\n'.repeat(20001);
  assert.throws(() => WL.filasDeCSV(t), /20\.000/);
});

// ---- lector de archivos ----
test('leerArchivo: CSV suelto', async () => {
  const f = await WL.leerArchivo(new Blob([CSV]));
  assert.strictEqual(f.length, 2); assert.strictEqual(f[0].name, 'Paris, Texas');
});
test('leerArchivo: zip deflate; no lee profile.csv aunque esté antes', async () => {
  const z = zip([['profile.csv', 'Username,Email\r\nsecreto,x@y.z\r\n'], ['watchlist.csv', CSV]]);
  const orig = Blob.prototype.slice, leidos = [];
  Blob.prototype.slice = function (a, b) { leidos.push([a, b]); return orig.call(this, a, b); };
  let f;
  try { f = await WL.leerArchivo(z); } finally { Blob.prototype.slice = orig; }
  assert.strictEqual(f.length, 2);
  // ningún slice cubre el cuerpo de profile.csv (empieza en 0 + 30 + nombre)
  const lh = 30 + 'profile.csv'.length, finProfile = lh + zlib.deflateRawSync(Buffer.from('Username,Email\r\nsecreto,x@y.z\r\n')).length;
  for (const [a, b] of leidos) assert.ok(!(a < finProfile && b > lh && a >= lh), 'se leyó el cuerpo de profile.csv');
});
test('leerArchivo: zip stored, con comentario y extra en el header local', async () => {
  const f = await WL.leerArchivo(zip([['watchlist.csv', CSV]], {metodo: 0, extra: 7, comentario: 'hola'}));
  assert.strictEqual(f.length, 2);
});
test('leerArchivo: rechaza cifrado, zip64, método raro, sin watchlist y no-zip', async () => {
  await assert.rejects(WL.leerArchivo(zip([['watchlist.csv', CSV]], {flags: 1})), /cifrado/);
  await assert.rejects(WL.leerArchivo(zip([['watchlist.csv', CSV]], {zip64: true})), /zip64/);
  await assert.rejects(WL.leerArchivo(zip([['watchlist.csv', CSV, 12]])), /compresión/);
  await assert.rejects(WL.leerArchivo(zip([['profile.csv', 'a,b\n1,2\n'], ['otra/watchlist.csv', CSV]])), /raíz/);
  await assert.rejects(WL.leerArchivo(new Blob(['PK\x03\x04basura'])), /\.zip/);
});
test('leerArchivo: topes (CSV de más de 5 MB)', async () => {
  await assert.rejects(WL.leerArchivo(new Blob([Buffer.alloc(5 * 1024 * 1024 + 1, 97)])), /grande/);
  const grande = 'Name,Year\n' + 'a'.repeat(6 * 1024 * 1024);
  await assert.rejects(WL.leerArchivo(zip([['watchlist.csv', grande]])), /grande/);
});
test('mensaje: un error ajeno no filtra su texto', () => {
  assert.ok(!/boom/.test(WL.mensaje(new Error('boom'))));
});

// ---- cruce ----
const film = (titulo, id, anio, extra = {}) => Object.assign({titulo, tmdb_id: id, anio_tmdb: anio,
  titulo_original: titulo, titulo_local: null, titulo_en: null}, extra);
const fila = (name, year, tmdb = null) => ({name, year, tmdb});
const cruz = (filas, films) => WL.cruzarWatchlist(filas, films);

test('norm: tildes, signos, &, artículo inicial, unicode', () => {
  assert.strictEqual(WL.norm('¡Amélie!'), 'amelie');
  assert.strictEqual(WL.norm('The Lord of the Rings'), 'lord of the rings');
  assert.strictEqual(WL.norm('Tom & Jerry'), WL.norm('Tom y Jerry'));
  assert.strictEqual(WL.norm('El Padrino'), 'padrino');
  assert.strictEqual(WL.norm('엔하이픈'), '엔하이픈'.normalize('NFD'));
  assert.strictEqual(WL.norm('!!'), '');
});
test('cruce: remake Suspiria 1977 vs 2018', () => {
  const films = [film('Suspiria', '1', '2018')];
  assert.strictEqual(cruz([fila('Suspiria', 1977)], films).matches.length, 0);
  assert.strictEqual(cruz([fila('Suspiria', 2018)], films).matches.length, 1);
});
test('cruce: título traducido (Name en inglés, catálogo local) y año ±1', () => {
  const films = [film('El padrino', '2', '1972', {titulo_en: 'The Godfather', titulo_local: 'El padrino'})];
  const r = cruz([fila('The Godfather', 1973)], films);
  assert.deepStrictEqual(r.ids, ['2']); assert.strictEqual(r.matches[0].titulo, 'El padrino');
  assert.strictEqual(cruz([fila('The Godfather', 1975)], films).ids.length, 0);
});
test('cruce: reestreno Cars 2006 usa anio_tmdb, no el año del cine', () => {
  const films = [film('Cars', '3', '2006', {anio: '2026'})];
  assert.strictEqual(cruz([fila('Cars', 2006)], films).ids.length, 1);
  assert.strictEqual(cruz([fila('Cars', 2026)], films).ids.length, 0);
});
test('cruce: fila sin año, película sin tmdb_id, título corto o vacío', () => {
  const films = [film('Cars', '3', '2006'), film('Sin ficha', null, '2020'), film('X', '9', '2020'), film('!!', '10', '2020')];
  assert.strictEqual(cruz([fila('Cars', null)], films).ids.length, 0);
  assert.strictEqual(cruz([fila('Sin ficha', 2020)], films).ids.length, 0);
  assert.strictEqual(cruz([fila('X', 2020), fila('!!', 2020)], films).ids.length, 0);
});
test('cruce: ambigüedad no marca; el año exacto gana sobre ±1', () => {
  const dos = [film('Dune', '4', '2021'), film('Dune', '5', '2021')];
  assert.strictEqual(cruz([fila('Dune', 2021)], dos).ids.length, 0);
  const cerca = [film('Dune', '4', '2021'), film('Dune', '5', '2022')];
  assert.deepStrictEqual(cruz([fila('Dune', 2021)], cerca).ids, ['4']);
  const solo1 = [film('Dune', '4', '2020'), film('Dune', '5', '2022')];
  assert.strictEqual(cruz([fila('Dune', 2021)], solo1).ids.length, 0);
});
test('cruce: hangul (ENHYPEN/HYBE) no cruza con filas del mismo año', () => {
  const films = [film('엔하이픈 콘서트', '6', '2025', {titulo_original: '엔하이픈 콘서트'})];
  const r = cruz([fila('하이브 콘서트', 2025), fila('БТС', 2025), fila('!!!', 2025)], films);
  assert.strictEqual(r.ids.length, 0);
  assert.strictEqual(cruz([fila('엔하이픈 콘서트', 2025)], films).ids.length, 1);
});
test('cruce: sufijos de formato solo del lado del catálogo; mismo tmdb_id en dos tarjetas cuenta una', () => {
  const films = [film('Avatar 3D', '7', '2009'), film('Avatar', '7', '2009')];
  const r = cruz([fila('Avatar', 2009)], films);
  assert.deepStrictEqual(r.ids, ['7']);
  assert.strictEqual(cruz([fila('Avatar 3D', 2009)], [film('Avatar', '7', '2009')]).ids.length, 0);
});
test('cruce: tmdbID directo, y conteo de no cruzadas', () => {
  const films = [film('Cars', '3', '2006')];
  const r = cruz([fila('Cualquiera', null, '3'), fila('Nada', 1999), fila('Otro', null, '999')], films);
  assert.deepStrictEqual(r.ids, ['3']); assert.strictEqual(r.noCruzadas.length, 2); assert.strictEqual(r.filas, 3);
});

// ---- filtro y guardado ----
test('filtro guardadas: entra en pasaPelicula y contarFiltros; no se persiste', () => {
  const fl = CF.crearFiltros(); assert.strictEqual(fl.guardadas, null);
  const f = {titulo: 'A', tmdb_id: '3'}, g = {titulo: 'B', tmdb_id: null};
  fl.guardadas = {'3': true};
  assert.strictEqual(CF.contarFiltros(fl), 1);
  const res = CF.filtrarFunciones(Object.assign({cines: {s: {'2026-10-27': [{h: '20:00'}]}}}, f), ['s'], fl, {});
  assert.strictEqual(res.n, 1);
  assert.strictEqual(CF.filtrarFunciones(Object.assign({cines: {s: {'2026-10-27': [{h: '20:00'}]}}}, g), ['s'], fl, {}).n, 0);
  assert.strictEqual(CF.sanearFiltros({guardadas: {'3': true}}, {}).guardadas, null);
});
test('sanearGuardadas: solo enteros', () => {
  assert.deepStrictEqual(WL.sanearGuardadas({ids: [1, '2', 3.5, null, -4, 7], fecha: '2026-10-27'}), {ids: [1, 7], fecha: '2026-10-27'});
  assert.strictEqual(WL.sanearGuardadas('x'), null);
  assert.strictEqual(WL.sanearGuardadas({ids: 'no'}), null);
});
