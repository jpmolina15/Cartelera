// Pruebas del bloque puro de templates/app.js. Correr: node --test tests/js/
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const CF = require(path.join(__dirname, '..', '..', 'templates', 'app.js'));

const SALAS = {
  'cinemark-palermo': {nombre: 'Cinemark Palermo', cadena: 'cinemark', barrio: 'Palermo', lat: -34.5880, lon: -58.4106},
  'hoyts-abasto': {nombre: 'Hoyts Abasto', cadena: 'hoyts', barrio: 'Balvanera', lat: -34.60395, lon: -58.41067},
  'cinemark-caballito': {nombre: 'Cinemark Caballito', cadena: 'cinemark', barrio: 'Almagro', lat: -34.61636, lon: -58.42887},
  'hoyts-dot': {nombre: 'Hoyts DOT', cadena: 'hoyts', barrio: 'Saavedra', lat: -34.54505, lon: -58.48765},
  'atlas': {nombre: 'Atlas', cadena: 'atlas', barrio: 'Almagro', lat: -34.6170, lon: -58.4400, con_datos: false},
};
const IDS = Object.keys(SALAS);
const row = (h, lang = '', fmt = '') => ({h, lang, fmt});
const film = (extra = {}) => Object.assign({
  titulo: 'Amélie', original: 'Le fabuleux destin', director: 'Jean-Pierre Jeunet', genero: 'Comedia, Drama',
  clasificacion: 'SP', rt: 90,
  cines: {
    'cinemark-palermo': {'2026-10-26': [row('11:00'), row('15:30', 'S', 'DBOX + 2D'), row('20:00', 'D'), row('00:30', '', '4D + 2D, XD + 2D')],
                         '2026-10-27': [row('18:00')]},
    'hoyts-abasto': {'2026-10-26': [row('19:00', 'S')]},
  }}, extra);
const hs = (res, id, d) => (res.cines[id] && res.cines[id][d] || []).map(r => r.h);
const F0 = () => CF.crearFiltros();

test('distanciaKm: tabla fija entre salas', () => {
  const d = (a, b) => CF.distanciaKm(SALAS[a].lat, SALAS[a].lon, SALAS[b].lat, SALAS[b].lon);
  assert.strictEqual(d('cinemark-palermo', 'cinemark-palermo'), 0);
  assert.strictEqual(d('cinemark-palermo', 'hoyts-abasto'), 1.8);
  assert.strictEqual(d('cinemark-palermo', 'cinemark-caballito'), 3.6);
  assert.strictEqual(d('hoyts-abasto', 'hoyts-dot'), 9.6);
  assert.strictEqual(d('hoyts-abasto', 'cinemark-palermo'), d('cinemark-palermo', 'hoyts-abasto'));
  // 1 grado de latitud ~ 111,2 km
  assert.strictEqual(CF.distanciaKm(0, 0, 1, 0), 111.2);
});

test('normFmt', () => {
  assert.deepStrictEqual(CF.normFmt('DBOX + 2D'), ['DBOX']);
  assert.deepStrictEqual(CF.normFmt('4D + 2D, XD + 2D'), ['4D', 'XD']);
  assert.deepStrictEqual(CF.normFmt('PREMIER + 2D'), ['PREMIER']);
  assert.deepStrictEqual(CF.normFmt('3d'), ['3D']);
  assert.deepStrictEqual(CF.normFmt(''), ['2D / común']);
  assert.deepStrictEqual(CF.normFmt(null), ['2D / común']);
  assert.deepStrictEqual(CF.normFmt('DBOX + 2D, dbox'), ['DBOX']);
});

test('horaComparable: trasnoche cuenta como 24-28', () => {
  assert.strictEqual(CF.horaComparable('19:30'), 1170);
  assert.strictEqual(CF.horaComparable('00:30'), 24 * 60 + 30);
  assert.strictEqual(CF.horaComparable('04:59'), 28 * 60 + 59);
  assert.strictEqual(CF.horaComparable('05:00'), 300);
  assert.ok(CF.horaComparable('23:50') < CF.horaComparable('00:10'));
  assert.ok(isNaN(CF.horaComparable('')));
  assert.ok(isNaN(CF.horaComparable(null)));
});

test('filtrarSalas: barrios, cerca (orden por distancia), cadena, sin datos', () => {
  let f = F0();
  assert.deepStrictEqual(CF.filtrarSalas(SALAS, f).map(x => x.id), IDS);
  assert.strictEqual(CF.filtrarSalas(SALAS, f).find(x => x.id === 'atlas').sinDatos, true);
  f.zona = {modo: 'barrios', barrios: ['Almagro'], centro: null, radio: 3};
  assert.deepStrictEqual(CF.filtrarSalas(SALAS, f).map(x => x.id), ['cinemark-caballito', 'atlas']);
  f.zona = {modo: 'barrios', barrios: [], centro: null, radio: 3};
  assert.strictEqual(CF.filtrarSalas(SALAS, f).length, 5);   // sin barrios marcados = todos
  const c = SALAS['cinemark-palermo'];
  f.zona = {modo: 'cerca', barrios: [], centro: {lat: c.lat, lon: c.lon}, radio: 2};
  const r = CF.filtrarSalas(SALAS, f);
  assert.deepStrictEqual(r.map(x => x.id), ['cinemark-palermo', 'hoyts-abasto']);
  assert.deepStrictEqual(r.map(x => x.dist), [0, 1.8]);
  f.zona.radio = 1;
  assert.deepStrictEqual(CF.filtrarSalas(SALAS, f).map(x => x.id), ['cinemark-palermo']);
  f.zona.centro = {lat: -34.70, lon: -58.30}; // lejos de todo: 0 salas
  assert.strictEqual(CF.filtrarSalas(SALAS, f).length, 0);
  f.zona = {modo: 'cerca', barrios: [], centro: null, radio: 3};
  assert.strictEqual(CF.filtrarSalas(SALAS, f).length, 5);   // sin punto elegido no recorta
  f = F0(); f.cadenas = ['hoyts'];
  assert.deepStrictEqual(CF.filtrarSalas(SALAS, f).map(x => x.id), ['hoyts-abasto', 'hoyts-dot']);
});

test('centroBarrio: promedio de las salas del barrio', () => {
  const c = CF.centroBarrio(SALAS, 'Almagro');
  assert.ok(Math.abs(c.lat - (-34.61668)) < 1e-4 && Math.abs(c.lon - (-58.43443)) < 1e-4);
  assert.strictEqual(CF.centroBarrio(SALAS, 'Nada'), null);
});

test('filtrarFunciones: sin filtros devuelve todo', () => {
  const r = CF.filtrarFunciones(film(), IDS, F0(), {dia: null});
  assert.strictEqual(r.n, 6);
  const r1 = CF.filtrarFunciones(film(), IDS, F0(), {dia: '2026-10-26'});
  assert.strictEqual(r1.n, 5);
});

test('filtrarFunciones: zona, idioma, formato, horario', () => {
  const f = film(), ctx = {dia: '2026-10-26'};
  assert.strictEqual(CF.filtrarFunciones(f, ['hoyts-abasto'], F0(), ctx).n, 1);
  let fl = F0(); fl.idioma = 'S';
  let r = CF.filtrarFunciones(f, IDS, fl, ctx);
  assert.deepStrictEqual(hs(r, 'cinemark-palermo', '2026-10-26'), ['15:30']);
  assert.deepStrictEqual(hs(r, 'hoyts-abasto', '2026-10-26'), ['19:00']);
  fl = F0(); fl.idioma = 'D';   // sin dato de idioma no aparece
  assert.deepStrictEqual(hs(CF.filtrarFunciones(f, IDS, fl, ctx), 'cinemark-palermo', '2026-10-26'), ['20:00']);
  fl = F0(); fl.fmts = ['XD'];
  assert.deepStrictEqual(hs(CF.filtrarFunciones(f, IDS, fl, ctx), 'cinemark-palermo', '2026-10-26'), ['00:30']);
  fl = F0(); fl.fmts = ['2D / común'];
  assert.strictEqual(CF.filtrarFunciones(f, IDS, fl, ctx).n, 3);
  fl = F0(); fl.desde = '19:00';   // noche incluye trasnoche
  assert.deepStrictEqual(hs(CF.filtrarFunciones(f, IDS, fl, ctx), 'cinemark-palermo', '2026-10-26'), ['20:00', '00:30']);
  fl = F0(); fl.desde = '12:00'; fl.hasta = '18:59';   // tarde
  assert.deepStrictEqual(hs(CF.filtrarFunciones(f, IDS, fl, ctx), 'cinemark-palermo', '2026-10-26'), ['15:30']);
  fl = F0(); fl.hasta = '12:00';   // la trasnoche no entra en «hasta 12:00»
  assert.deepStrictEqual(hs(CF.filtrarFunciones(f, IDS, fl, ctx), 'cinemark-palermo', '2026-10-26'), ['11:00']);
});

test('filtrarFunciones: «desde ahora» solo corta las funciones de hoy', () => {
  const fl = F0(); fl.ahora = true;
  const ctx = {dia: null, hoy: '2026-10-26', ahoraMin: 16 * 60};
  const r = CF.filtrarFunciones(film(), IDS, fl, ctx);
  assert.deepStrictEqual(hs(r, 'cinemark-palermo', '2026-10-26'), ['20:00', '00:30']);
  assert.deepStrictEqual(hs(r, 'cinemark-palermo', '2026-10-27'), ['18:00']);   // otro día: intacto
  fl.ahora = false;
  assert.strictEqual(CF.filtrarFunciones(film(), IDS, fl, ctx).n, 6);
});

test('filtrarFunciones: buscar, género, clasificación, puntaje', () => {
  const ctx = {dia: null};
  let fl = F0(); fl.q = 'AMELIE';
  assert.ok(CF.filtrarFunciones(film(), IDS, fl, ctx).n > 0);
  fl.q = 'fabuleux destin'; assert.ok(CF.filtrarFunciones(film(), IDS, fl, ctx).n > 0);
  fl.q = 'jeunet'; assert.ok(CF.filtrarFunciones(film(), IDS, fl, ctx).n > 0);
  fl.q = 'matrix'; assert.strictEqual(CF.filtrarFunciones(film(), IDS, fl, ctx).n, 0);
  fl = F0(); fl.generos = ['Drama'];
  assert.ok(CF.filtrarFunciones(film(), IDS, fl, ctx).n > 0);
  fl.generos = ['Terror']; assert.strictEqual(CF.filtrarFunciones(film(), IDS, fl, ctx).n, 0);
  assert.strictEqual(CF.filtrarFunciones(film({genero: null}), IDS, fl, ctx).n, 0);   // sin género: solo sin chips
  assert.ok(CF.filtrarFunciones(film({genero: null}), IDS, F0(), ctx).n > 0);
  fl = F0(); fl.clas = '0';   // todo público
  assert.strictEqual(CF.filtrarFunciones(film({clasificacion: 'SP'}), IDS, fl, ctx).n, 0);
  assert.ok(CF.filtrarFunciones(film({clasificacion: 'ATP'}), IDS, fl, ctx).n > 0);
  fl.clas = '1'; assert.ok(CF.filtrarFunciones(film({clasificacion: 'SP'}), IDS, fl, ctx).n > 0);
  assert.strictEqual(CF.filtrarFunciones(film({clasificacion: 'R-13'}), IDS, fl, ctx).n, 0);
  assert.strictEqual(CF.filtrarFunciones(film({clasificacion: null}), IDS, fl, ctx).n, 0);   // sin dato: solo «Todas»
  fl.clas = '2'; assert.ok(CF.filtrarFunciones(film({clasificacion: 'R-13'}), IDS, fl, ctx).n > 0);
  fl = F0(); fl.rt70 = true;
  assert.ok(CF.filtrarFunciones(film({rt: 70}), IDS, fl, ctx).n > 0);
  assert.strictEqual(CF.filtrarFunciones(film({rt: 69}), IDS, fl, ctx).n, 0);
  assert.strictEqual(CF.filtrarFunciones(film({rt: null}), IDS, fl, ctx).n, 0);
});

test('contarFiltros y sanearFiltros', () => {
  const f = F0();
  assert.strictEqual(CF.contarFiltros(f), 0);
  f.q = 'x'; f.fmts = ['3D', 'XD']; f.ahora = true; f.desde = '10:00';
  assert.strictEqual(CF.contarFiltros(f), 3);   // buscar, formato, horario (cuenta una vez)
  const s = CF.sanearFiltros({q: 5, idioma: 'zzz', fmts: ['3D', 7], zona: {modo: 'cerca', radio: 4, centro: {tipo: 's', ref: 'nope'}}}, SALAS);
  assert.strictEqual(s.q, ''); assert.strictEqual(s.idioma, 'todas'); assert.deepStrictEqual(s.fmts, ['3D']);
  assert.strictEqual(s.zona.modo, 'cerca'); assert.strictEqual(s.zona.radio, 3); assert.strictEqual(s.zona.centro, null);
  const p = CF.sanearFiltros({zona: {modo: 'cerca', centro: {tipo: 'p', lat: -34.60395123, lon: -58.41067999, label: 'Av. Corrientes 3247'}}}, SALAS);
  assert.deepStrictEqual([p.zona.centro.lat, p.zona.centro.lon, p.zona.centro.label], [-34.604, -58.411, 'Tu dirección']);   // sin la dirección escrita
  assert.strictEqual(CF.sanearFiltros(null, SALAS).zona.modo, 'todos');
});

test('ahoraBA y diaInicial', () => {
  // 2026-10-27 01:30 UTC = 2026-10-26 22:30 en Buenos Aires (UTC-3)
  assert.deepStrictEqual(CF.ahoraBA(new Date('2026-10-27T01:30:00Z')), {hoy: '2026-10-26', min: 22 * 60 + 30});
  assert.deepStrictEqual(CF.ahoraBA(new Date('2026-10-26T03:00:00Z')), {hoy: '2026-10-26', min: 0});
  const days = ['2026-10-26', '2026-10-27', '2026-10-28'];
  assert.deepStrictEqual(CF.diaInicial(days, '2026-10-27'), {dia: '2026-10-27', vencida: false});
  assert.deepStrictEqual(CF.diaInicial(days, '2026-10-30'), {dia: '2026-10-28', vencida: true});
  assert.deepStrictEqual(CF.diaInicial(days, '2026-10-20'), {dia: '2026-10-26', vencida: false});
  assert.deepStrictEqual(CF.diaInicial([], '2026-10-20'), {dia: null, vencida: false});
});

test('parseUsig: primer resultado de CABA', () => {
  const j = {direccionesNormalizadas: [
    {cod_partido: 'moreno', coordenadas: {x: -58.5, y: -34.5}},
    {cod_partido: 'caba', direccion: 'CORRIENTES AV. 3247, CABA', coordenadas: {srid: 4326, x: '-58.410672', y: '-34.603955'}}]};
  assert.deepStrictEqual(CF.parseUsig(j), {lat: -34.604, lon: -58.411, texto: 'CORRIENTES AV. 3247, CABA'});
  assert.strictEqual(CF.parseUsig({direccionesNormalizadas: [{cod_partido: 'moreno', coordenadas: {x: 1, y: 2}}]}), null);
  assert.strictEqual(CF.parseUsig({}), null);
  assert.strictEqual(CF.parseUsig(null), null);
});

test('rank', () => {
  assert.deepStrictEqual(['G', 'ATP', 'SP', 'R-13', 'R-17', null].map(CF.rank), [0, 0, 1, 2, 4, 99]);
});
