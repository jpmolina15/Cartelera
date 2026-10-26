// ===== Bloque puro (sin DOM): filtros de zona, película y función. Se prueba con `node --test tests/js/`. =====
var CF=(function(){
  var COMUN='2D / común';
  function sinAcentos(s){return String(s==null?'':s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();}
  function rank(c){
    if(!c) return 99;
    var v=String(c).toUpperCase().replace(/[\s()]/g,'');
    if(/^(G|ATP)/.test(v)) return 0;
    if(/^SP/.test(v)) return 1;
    if(/13/.test(v)) return 2;
    if(/16/.test(v)) return 3;
    if(/(17|18)/.test(v)) return 4;
    return 50;
  }
  // Haversine en línea recta, redondeada a 0,1 km.
  function distanciaKm(lat1,lon1,lat2,lon2){
    var R=6371, r=Math.PI/180, dl=(lat2-lat1)*r, dn=(lon2-lon1)*r;
    var h=Math.pow(Math.sin(dl/2),2)+Math.cos(lat1*r)*Math.cos(lat2*r)*Math.pow(Math.sin(dn/2),2);
    return Math.round(2*R*Math.asin(Math.sqrt(h))*10)/10;
  }
  // 'DBOX + 2D' -> ['DBOX']; '4D + 2D, XD + 2D' -> ['4D','XD']; '' -> ['2D / común'].
  function normFmt(fmt){
    var out=[];
    String(fmt==null?'':fmt).split(',').forEach(function(p){
      var t=p.replace(/\s*\+\s*2D\s*$/i,'').trim().toUpperCase();
      if(!t||t==='2D') t=COMUN;
      if(out.indexOf(t)<0) out.push(t);});
    if(!out.length) out.push(COMUN);
    return out;
  }
  // Minutos desde las 00:00 del día de la función; 00:00-04:59 cuentan como 24-28 h (trasnoche). NaN si no hay hora.
  function horaComparable(h){
    var m=/^(\d{1,2}):(\d{2})/.exec(String(h==null?'':h).trim());
    if(!m) return NaN;
    var hh=+m[1], mm=+m[2];
    return (hh<5?hh+24:hh)*60+mm;
  }
  function crearFiltros(){
    return {q:'',desde:'',hasta:'',ahora:false,idioma:'todas',fmts:[],generos:[],clas:'todas',rt70:false,cadenas:[],
      zona:{modo:'todos',barrios:[],centro:null,radio:3}};
  }
  function centroBarrio(salas,barrio){
    var n=0,la=0,lo=0;
    Object.keys(salas).forEach(function(id){var s=salas[id];
      if(s.barrio===barrio&&typeof s.lat==='number'&&typeof s.lon==='number'){n++;la+=s.lat;lo+=s.lon;}});
    return n?{lat:Math.round(la/n*1e5)/1e5,lon:Math.round(lo/n*1e5)/1e5}:null;
  }
  function arr(a){return Array.isArray(a)?a.filter(function(x){return typeof x==='string';}):[];}
  // Valida lo que vino de localStorage: ignora lo que no tenga la forma esperada.
  function sanearFiltros(o,salas){
    var f=crearFiltros(); if(!o||typeof o!=='object') return f;
    if(typeof o.q==='string') f.q=o.q.slice(0,80);
    if(/^\d{1,2}:\d{2}$/.test(o.desde||'')) f.desde=o.desde;
    if(/^\d{1,2}:\d{2}$/.test(o.hasta||'')) f.hasta=o.hasta;
    if(o.idioma==='S'||o.idioma==='D') f.idioma=o.idioma;
    f.fmts=arr(o.fmts); f.generos=arr(o.generos); f.cadenas=arr(o.cadenas);
    if(['0','1','2'].indexOf(o.clas)>=0) f.clas=o.clas;
    f.rt70=o.rt70===true;
    var z=o.zona;
    if(z&&typeof z==='object'){
      if(z.modo==='barrios'||z.modo==='cerca') f.zona.modo=z.modo;
      f.zona.barrios=arr(z.barrios);
      if([1,2,3,5,10].indexOf(z.radio)>=0) f.zona.radio=z.radio;
      var c=z.centro;
      if(c&&typeof c==='object'){
        if(c.tipo==='s'&&salas[c.ref]&&typeof salas[c.ref].lat==='number')
          f.zona.centro={tipo:'s',ref:c.ref,lat:salas[c.ref].lat,lon:salas[c.ref].lon};
        else if(c.tipo==='b'){var cb=centroBarrio(salas,c.ref); if(cb) f.zona.centro={tipo:'b',ref:c.ref,lat:cb.lat,lon:cb.lon};}
        else if(c.tipo==='p'&&typeof c.lat==='number'&&typeof c.lon==='number'&&Math.abs(c.lat)<=90&&Math.abs(c.lon)<=180)
          f.zona.centro={tipo:'p',lat:Math.round(c.lat*1e3)/1e3,lon:Math.round(c.lon*1e3)/1e3,
            label:c.label==='Tu ubicación'?'Tu ubicación':'Tu dirección'};
      }
    }
    return f;
  }
  // Cantidad de filtros de película/función activos (la zona y el día no cuentan).
  function contarFiltros(f){
    var n=0;
    if(f.q&&f.q.trim()) n++;
    if(f.desde||f.hasta||f.ahora) n++;
    if(f.idioma&&f.idioma!=='todas') n++;
    if(f.fmts.length) n++;
    if(f.generos.length) n++;
    if(f.clas&&f.clas!=='todas') n++;
    if(f.rt70) n++;
    if(f.cadenas.length) n++;
    return n;
  }
  // Salas que entran por zona (barrios o punto+radio) y cadena. Devuelve [{id,dist,sinDatos}];
  // con modo «cerca» y punto elegido se ordena por distancia.
  function filtrarSalas(salas,f,orden){
    var ids=orden||Object.keys(salas), z=f.zona||{modo:'todos'}, out=[];
    var cerca=z.modo==='cerca'&&z.centro&&typeof z.centro.lat==='number';
    ids.forEach(function(id){
      var s=salas[id]; if(!s) return;
      if(f.cadenas&&f.cadenas.length&&f.cadenas.indexOf(s.cadena)<0) return;
      var dist=null;
      if(z.modo==='barrios'&&z.barrios&&z.barrios.length&&z.barrios.indexOf(s.barrio)<0) return;
      if(cerca){
        if(typeof s.lat!=='number'||typeof s.lon!=='number') return;
        dist=distanciaKm(z.centro.lat,z.centro.lon,s.lat,s.lon);
        if(dist>z.radio) return;
      }
      out.push({id:id,dist:dist,sinDatos:s.con_datos===false});});
    if(cerca) out.sort(function(a,b){return a.dist-b.dist;});
    return out;
  }
  function pasaPelicula(f,fl){
    if(fl.q&&fl.q.trim()){
      var hay=sinAcentos([f.titulo,f.original,f.director].join(' '));
      var ok=sinAcentos(fl.q).split(/\s+/).filter(Boolean).every(function(t){return hay.indexOf(t)>=0;});
      if(!ok) return false;
    }
    if(fl.generos&&fl.generos.length){
      var gs=String(f.genero||'').split(',').map(function(x){return x.trim();}).filter(Boolean);
      if(!gs.some(function(g){return fl.generos.indexOf(g)>=0;})) return false;
    }
    if(fl.clas&&fl.clas!=='todas'){
      var r=rank(f.clasificacion);
      if(r>+fl.clas) return false;
    }
    if(fl.rt70&&!(f.rt!=null&&f.rt>=70)) return false;
    return true;
  }
  // Funciones de una película que cumplen todo. ids: salas permitidas (ya filtradas por zona/cadena).
  // ctx: {dia:'YYYY-MM-DD'|null (null = todos los días), hoy, ahoraMin}.
  // Devuelve {cines:{id:{dia:[funciones]}}, n}. «Desde ahora» solo corta las funciones de hoy.
  function filtrarFunciones(f,ids,fl,ctx){
    var res={cines:{},n:0}; ctx=ctx||{};
    if(!pasaPelicula(f,fl)) return res;
    var desde=horaComparable(fl.desde), hasta=horaComparable(fl.hasta);
    var idioma=fl.idioma&&fl.idioma!=='todas'?fl.idioma:null, fm=fl.fmts||[];
    ids.forEach(function(id){
      var dias=f.cines&&f.cines[id]; if(!dias) return;
      Object.keys(dias).forEach(function(d){
        if(ctx.dia&&d!==ctx.dia) return;
        var rows=dias[d].filter(function(r){
          if(idioma&&r.lang!==idioma) return false;
          if(fm.length&&!normFmt(r.fmt).some(function(x){return fm.indexOf(x)>=0;})) return false;
          var c=horaComparable(r.h);
          if(!isNaN(desde)&&!(c>=desde)) return false;
          if(!isNaN(hasta)&&!(c<=hasta)) return false;
          if(fl.ahora&&ctx.hoy&&d===ctx.hoy&&ctx.ahoraMin!=null&&!(c>=ctx.ahoraMin)) return false;
          return true;});
        if(rows.length){(res.cines[id]=res.cines[id]||{})[d]=rows; res.n+=rows.length;}
      });});
    return res;
  }
  // Fecha y hora de Buenos Aires para un Date.
  function ahoraBA(dt){
    var p={};
    new Intl.DateTimeFormat('en-CA',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',
      day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(dt).forEach(function(x){p[x.type]=x.value;});
    return {hoy:p.year+'-'+p.month+'-'+p.day,min:(+p.hour%24)*60+(+p.minute)};
  }
  // Día en que se abre: hoy si está en la ventana; si ya pasó todo, el último (vencida=true).
  function diaInicial(days,hoy){
    if(!days.length) return {dia:null,vencida:false};
    if(days.indexOf(hoy)>=0) return {dia:hoy,vencida:false};
    if(hoy>days[days.length-1]) return {dia:days[days.length-1],vencida:true};
    for(var i=0;i<days.length;i++) if(days[i]>hoy) return {dia:days[i],vencida:false};
    return {dia:days[0],vencida:false};
  }
  // Respuesta de USIG: primer resultado de CABA con coordenadas -> {lat,lon,texto} (3 decimales) o null.
  function parseUsig(j){
    var a=j&&j.direccionesNormalizadas; if(!Array.isArray(a)) return null;
    for(var i=0;i<a.length;i++){
      var d=a[i]; if(!d||d.cod_partido!=='caba'||!d.coordenadas) continue;
      var lat=parseFloat(d.coordenadas.y), lon=parseFloat(d.coordenadas.x);
      if(isFinite(lat)&&isFinite(lon)) return {lat:Math.round(lat*1e3)/1e3,lon:Math.round(lon*1e3)/1e3,texto:d.direccion||''};
    }
    return null;
  }
  // Enlaces de la tarjeta: sólo si tmdb_id es un entero (nunca un link armado por título).
  function enlacesHTML(f){
    var id=f&&f.tmdb_id; if(id==null||!/^\d+$/.test(String(id))) return '';
    id=String(id);
    return '<div class="enlaces"><a href="https://letterboxd.com/tmdb/'+id+'/" target="_blank" rel="noopener noreferrer">Ver en Letterboxd</a>'+
      '<a href="https://www.themoviedb.org/movie/'+id+'" target="_blank" rel="noopener noreferrer">TMDb</a></div>';
  }
  return {enlacesHTML:enlacesHTML,COMUN:COMUN,sinAcentos:sinAcentos,rank:rank,distanciaKm:distanciaKm,normFmt:normFmt,horaComparable:horaComparable,
    crearFiltros:crearFiltros,sanearFiltros:sanearFiltros,contarFiltros:contarFiltros,centroBarrio:centroBarrio,
    filtrarSalas:filtrarSalas,filtrarFunciones:filtrarFunciones,ahoraBA:ahoraBA,diaInicial:diaInicial,parseUsig:parseUsig};
})();
if(typeof module!=='undefined'&&module.exports) module.exports=CF;

if(typeof window!=='undefined'&&window.__DATA__){(function(){
  var D=window.__DATA__, DAYS=D.days, F=D.films;
  var SALAS=D.salas||{};
  var CADENAS={cinemark:'Cinemark',hoyts:'Hoyts',atlas:'Atlas',incaa:'INCAA'};
  var CLS={cinemark:'c-cinemark',hoyts:'c-hoyts',atlas:'c-atlas',incaa:'c-incaa'};
  var DOMINIOS={cinemark:'cinemark.com.ar',atlas:'atlascines.com',gaumont:'unica-cartelera.com.ar'};
  function cc(c){return CLS[SALAS[c].cadena]||'c-otro';}
  // Orden: por cadena y nombre.
  var ORD=Object.keys(SALAS).sort(function(a,b){
    var x=SALAS[a],y=SALAS[b];
    return (x.cadena||'').localeCompare(y.cadena||'','es')||x.nombre.localeCompare(y.nombre,'es');});
  function abrev(c){var t=SALAS[c].corto;if(t.length<=14)return t;
    var w=t.split(' ');w[0]=w[0].slice(0,3)+'.';return w.join(' ');}
  var DOW=['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
  var MES=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  function scoreHTML(f){
    var out='';
    if(f.rt!=null)     out+='<span class="score rt"><b>'+f.rt+'%</b><s>Tomatómetro</s></span>';
    if(f.rt_pub!=null) out+='<span class="score"><b>'+f.rt_pub+'%</b><s>Público RT</s></span>';
    if(f.score!=null)  out+='<span class="score"><b>'+f.score.toFixed(1)+'</b><s>TMDb</s></span>';
    if(!out) out='<span class="score none"><b>—</b><s>sin puntaje</s></span>';
    return '<span class="scores">'+out+'</span>';
  }
  function orden(a,b){
    var ra=(a.rt==null?-1:a.rt), rb=(b.rt==null?-1:b.rt);
    if(ra!==rb) return rb-ra;
    var ta=(a.score==null?-1:a.score), tb=(b.score==null?-1:b.score);
    if(ta!==tb) return tb-ta;
    return a.titulo.localeCompare(b.titulo,'es');
  }
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function lbl(d){var p=d.split('-'),dt=new Date(+p[0],+p[1]-1,+p[2]);
    return [DOW[(dt.getDay()+6)%7], (+p[2])+' '+MES[+p[1]-1]];}
  function $(id){return document.getElementById(id);}
  function km(x){return String(x).replace('.',',')+' km';}
  var list=Object.keys(F).map(function(k){return F[k];});
  // Tolera que falte un nodo: antes, un id que la plantilla no traía cortaba
  // el script entero y la página salía en blanco.
  function setTxt(id,t){var e=$(id); if(e) e.textContent=t;}
  setTxt('nfilms',list.length);
  setTxt('relevado',D.relevado||'—');
  if(DAYS.length){var U=lbl(DAYS[DAYS.length-1]); setTxt('hasta',U[0]+' '+U[1]);}
  // El pie no promete una fuente que esta semana no haya dado ningún puntaje:
  // TMDb viene bloqueando el scrapeo y entonces no se la menciona.
  (function(){
    var hayTMDb=list.some(function(f){return f.score!=null;});
    var hayRT=list.some(function(f){return f.rt!=null||f.rt_pub!=null;});
    var partes=[];
    if(hayRT) partes.push('tomatómetro y público de Rotten Tomatoes');
    if(hayTMDb) partes.push('puntaje de usuarios de TMDb sobre 10');
    var txt=partes.length?('Puntajes: '+partes.join(', y ')+'.')
                         :'Puntajes: ninguna fuente respondió en este relevamiento.';
    txt+=hayTMDb
      ? ' IMDb sirve un desafío de bots y Letterboxd rechaza el acceso, así que no se pueden incluir.'
      : ' TMDb, IMDb y Letterboxd no se pudieron consultar: sirven un desafío de bots o rechazan el acceso.';
    setTxt('nota-puntajes',txt);
    var at=$('atribucion-tmdb'); if(at&&list.some(function(f){return f.tmdb_id!=null;})) at.hidden=false;
  })();

  // ---------- estado ----------
  var LS='cartelera-caba-filtros-v1';
  function cargar(){
    try{var r=window.localStorage.getItem(LS); if(r) return CF.sanearFiltros(JSON.parse(r),SALAS);}catch(e){}
    return CF.crearFiltros();
  }
  function guardar(){
    try{var o=JSON.parse(JSON.stringify(S.f)); delete o.ahora; window.localStorage.setItem(LS,JSON.stringify(o));}catch(e){}
  }
  function ctxAhora(){return CF.ahoraBA(new Date());}
  var A0=ctxAhora(), INI=CF.diaInicial(DAYS,A0.hoy);
  var HOY_EN_VENTANA=DAYS.indexOf(A0.hoy)>=0;
  var S={dia:INI.dia,pane:'peliculas',f:cargar()};
  S.f.ahora=HOY_EN_VENTANA;   // «desde ahora» no se guarda: arranca activo si hoy está en la ventana.
  // Puntaje RT: el control solo existe si al menos 10 películas tienen rt.
  var HAY_RT=list.filter(function(f){return f.rt!=null;}).length>=10;
  if(!HAY_RT) S.f.rt70=false;

  // ---------- opciones que salen de los datos ----------
  var optFmt=[],optGen=[];
  (function(){
    var fs={},gs={};
    list.forEach(function(f){
      String(f.genero||'').split(',').forEach(function(g){g=g.trim(); if(g) gs[g]=1;});
      Object.keys(f.cines||{}).forEach(function(c){Object.keys(f.cines[c]).forEach(function(d){
        f.cines[c][d].forEach(function(r){CF.normFmt(r.fmt).forEach(function(x){fs[x]=1;});});});});});
    optFmt=Object.keys(fs).sort(function(a,b){
      return a===CF.COMUN?-1:b===CF.COMUN?1:a.localeCompare(b,'es');});
    optGen=Object.keys(gs).sort(function(a,b){return a.localeCompare(b,'es');});
  })();
  var optCad=[];
  (function(){var seen={};
    Object.keys(CADENAS).forEach(function(k){if(ORD.some(function(c){return SALAS[c].cadena===k;})){seen[k]=1;optCad.push(k);}});
    ORD.forEach(function(c){var k=SALAS[c].cadena; if(k&&!seen[k]){seen[k]=1;optCad.push(k);}});})();
  var BARRIOS={};
  ORD.forEach(function(c){var b=SALAS[c].barrio; if(b) BARRIOS[b]=(BARRIOS[b]||0)+1;});
  var barrioList=Object.keys(BARRIOS).sort(function(a,b){return a.localeCompare(b,'es');});

  // ---------- armado de la barra ----------
  function chipsHTML(opts,sel){
    return opts.map(function(o){var on=sel.indexOf(o.v)>=0;
      return '<button type="button" class="fchip'+(on?' on':'')+'" aria-pressed="'+on+'" data-v="'+esc(o.v)+'">'+esc(o.t)+'</button>';}).join('');}
  function toggleEn(arr,v){var i=arr.indexOf(v); if(i>=0)arr.splice(i,1); else arr.push(v);}
  function delegar(id,arr){
    var el=$(id); if(!el) return;
    el.addEventListener('click',function(ev){
      var b=ev.target.closest?ev.target.closest('.fchip'):null; if(!b) return;
      toggleEn(arr(),b.getAttribute('data-v')); cambio();});
  }
  function centroOpciones(){
    var h='<option value="">Elegí un punto…</option><optgroup label="Una sala">'+
      ORD.map(function(c){return '<option value="s:'+esc(c)+'">Cerca de '+esc(SALAS[c].nombre)+'</option>';}).join('')+
      '</optgroup><optgroup label="Un barrio (centro de sus salas)">'+
      barrioList.map(function(b){return '<option value="b:'+esc(b)+'">Cerca del centro de '+esc(b)+'</option>';}).join('')+
      '</optgroup>';
    var c=S.f.zona.centro;
    if(c&&c.tipo==='p') h+='<optgroup label="Punto"><option value="p">'+esc(c.label||'Tu dirección')+'</option></optgroup>';
    return h;
  }
  function valorCentro(){var c=S.f.zona.centro; if(!c) return ''; return c.tipo==='p'?'p':c.tipo+':'+c.ref;}
  function construirBarra(){
    $('fz-barrios-l').innerHTML=barrioList.map(function(b){
      return '<label class="fcheck"><input type="checkbox" data-b="'+esc(b)+'"> '+esc(b)+' ('+BARRIOS[b]+')</label>';}).join('');
    $('f-fmt').innerHTML=''; $('f-gen').innerHTML=''; $('f-cad').innerHTML='';
    $('f-rt-wrap').hidden=!HAY_RT;
    var fu=ORD.map(function(c){return SALAS[c].fuente;});
    $('f-idioma-nota').textContent=fu.indexOf('cinemark')>=0
      ?'Cinemark y Hoyts no informan idioma por función: con Subtitulada o Doblada solo se ven funciones con dato.'
      :'Las funciones sin dato de idioma solo se ven en «Todas».';
    $('f-ahora-wrap').hidden=!HOY_EN_VENTANA;
    if(!navigator.geolocation) $('fz-geo').hidden=true;
  }
  // Lleva el estado a los controles.
  function sincronizar(){
    var f=S.f, z=f.zona;
    Array.prototype.forEach.call(document.querySelectorAll('input[name=fz-modo]'),function(r){r.checked=r.value===z.modo;});
    $('fz-barrios').hidden=z.modo!=='barrios';
    $('fz-cerca').hidden=z.modo!=='cerca';
    Array.prototype.forEach.call($('fz-barrios-l').querySelectorAll('input'),function(i){
      i.checked=z.barrios.indexOf(i.getAttribute('data-b'))>=0;});
    $('fz-todos').checked=!z.barrios.length;
    $('fz-centro').innerHTML=centroOpciones(); $('fz-centro').value=valorCentro();
    $('fz-radio').value=String(z.radio);
    if($('f-q').value!==f.q) $('f-q').value=f.q;
    $('f-desde').value=f.desde; $('f-hasta').value=f.hasta;
    $('f-ahora').checked=!!f.ahora;
    $('f-idioma').value=f.idioma;
    $('f-clas').value=f.clas;
    $('f-rt').checked=!!f.rt70;
    $('f-fmt').innerHTML=chipsHTML(optFmt.map(function(x){return {v:x,t:x};}),f.fmts);
    $('f-gen').innerHTML=chipsHTML(optGen.map(function(x){return {v:x,t:x};}),f.generos);
    $('f-cad').innerHTML=chipsHTML(optCad.map(function(x){return {v:x,t:CADENAS[x]||x};}),f.cadenas);
  }
  function cambio(){guardar(); sincronizar(); render();}

  // ---------- eventos de la barra ----------
  Array.prototype.forEach.call(document.querySelectorAll('input[name=fz-modo]'),function(r){
    r.addEventListener('change',function(){S.f.zona.modo=r.value; cambio();});});
  $('fz-barrios-l').addEventListener('change',function(ev){
    var b=ev.target.getAttribute('data-b'); if(!b) return;
    toggleEn(S.f.zona.barrios,b); cambio();});
  $('fz-todos').addEventListener('change',function(){S.f.zona.barrios=[]; cambio();});
  function elegirCentro(){
    var v=$('fz-centro').value, c=null;
    if(v==='p') c=S.f.zona.centro;
    else if(v.indexOf('s:')===0){var id=v.slice(2); if(SALAS[id]) c={tipo:'s',ref:id,lat:SALAS[id].lat,lon:SALAS[id].lon};}
    else if(v.indexOf('b:')===0){var b=v.slice(2), cb=CF.centroBarrio(SALAS,b); if(cb) c={tipo:'b',ref:b,lat:cb.lat,lon:cb.lon};}
    S.f.zona.centro=c; avisoZona(''); cambio();
  }
  $('fz-centro').addEventListener('change',elegirCentro);
  $('fz-radio').addEventListener('change',function(){S.f.zona.radio=+$('fz-radio').value; cambio();});
  function avisoZona(t){var e=$('fz-aviso'); e.textContent=t; e.hidden=!t;}
  function puntoElegido(lat,lon,label){
    S.f.zona.centro={tipo:'p',lat:Math.round(lat*1e3)/1e3,lon:Math.round(lon*1e3)/1e3,label:label};
    avisoZona(''); cambio();
  }
  var NO_DIR='La búsqueda por dirección no está disponible acá: elegí una sala o un barrio.';
  function buscarDireccion(){
    var q=$('fz-dir').value.trim(); if(!q) return;
    var btn=$('fz-buscar'); btn.disabled=true; avisoZona('Buscando…');
    var fin=function(){btn.disabled=false;};
    try{
      var ctl=typeof AbortController!=='undefined'?new AbortController():null;
      var to=setTimeout(function(){if(ctl)ctl.abort();},6000);
      var carrera=new Promise(function(_,rej){setTimeout(function(){rej(new Error('timeout'));},6000);});
      var url='https://servicios.usig.buenosaires.gob.ar/normalizar/?direccion='+encodeURIComponent(q)+
        '&geocodificar=true&srid=4326';
      Promise.race([fetch(url,ctl?{signal:ctl.signal}:{}).then(function(r){
        if(!r.ok) throw new Error('http'); return r.json();}),carrera]).then(function(j){
        clearTimeout(to); fin();
        var p=CF.parseUsig(j);
        if(p) puntoElegido(p.lat,p.lon,'Tu dirección');
        else avisoZona('No encontramos esa dirección en la Ciudad. Probá con calle y altura, o elegí una sala o un barrio.');
      }).catch(function(){clearTimeout(to); fin(); avisoZona(NO_DIR);});
    }catch(e){fin(); avisoZona(NO_DIR);}
  }
  $('fz-buscar').addEventListener('click',buscarDireccion);
  $('fz-dir').addEventListener('keydown',function(ev){if(ev.key==='Enter'){ev.preventDefault(); buscarDireccion();}});
  $('fz-geo').addEventListener('click',function(){
    var ocultar=function(){$('fz-geo').hidden=true; avisoZona('No pudimos usar tu ubicación: elegí una sala o un barrio.');};
    try{navigator.geolocation.getCurrentPosition(function(p){puntoElegido(p.coords.latitude,p.coords.longitude,'Tu ubicación');},
      ocultar,{timeout:8000,maximumAge:60000});}catch(e){ocultar();}
  });
  $('f-q').addEventListener('input',function(){S.f.q=$('f-q').value; guardar(); render(); actualizarContadorFiltros();});
  function horaInput(id,k){$(id).addEventListener('change',function(){S.f[k]=$(id).value; cambio();});}
  horaInput('f-desde','desde'); horaInput('f-hasta','hasta');
  $('f-ahora').addEventListener('change',function(){S.f.ahora=$('f-ahora').checked; cambio();});
  $('f-tarde').addEventListener('click',function(){S.f.desde='12:00'; S.f.hasta='18:59'; cambio();});
  $('f-noche').addEventListener('click',function(){S.f.desde='19:00'; S.f.hasta=''; cambio();});
  $('f-idioma').addEventListener('change',function(){S.f.idioma=$('f-idioma').value; cambio();});
  $('f-clas').addEventListener('change',function(){S.f.clas=$('f-clas').value; cambio();});
  $('f-rt').addEventListener('change',function(){S.f.rt70=$('f-rt').checked; cambio();});
  delegar('f-fmt',function(){return S.f.fmts;});
  delegar('f-gen',function(){return S.f.generos;});
  delegar('f-cad',function(){return S.f.cadenas;});
  $('f-limpiar').addEventListener('click',function(){
    var z=S.f.zona; S.f=CF.crearFiltros(); S.f.zona=z; cambio();});

  // ---------- días (un solo estado para «Películas» y «Por cine») ----------
  function renderDays(){
    var h=DAYS.map(function(d){var L=lbl(d);
      return '<button class="tab'+(d===S.dia?' on':'')+'" data-day="'+d+'"><b>'+L[0]+'</b><span>'+L[1]+'</span></button>';}).join('');
    ['days-1','days-2'].forEach(function(id){$(id).innerHTML=h;});
  }
  ['days-1','days-2'].forEach(function(id){
    $(id).addEventListener('click',function(ev){
      var b=ev.target.closest?ev.target.closest('.tab'):null; if(!b) return;
      S.dia=b.getAttribute('data-day'); renderDays(); render();});});

  function times(rows){
    return rows.map(function(r){
      var lg=r.lang?'<u>'+r.lang+'</u>':'';
      var fm=r.fmt?' <span class="fmt">'+esc(r.fmt)+'</span>':'';
      return '<span class="hora">'+r.h+lg+'</span>'+fm;}).join('');
  }

  // ---------- vistas ----------
  function renderCards(RD,RW,dist){
    var rows=list.filter(function(f){return RD[f.key].n>0;});
    rows.sort(orden);
    $('cards').innerHTML=rows.map(function(f){
      var cines=RD[f.key].cines;
      var chips=ORD.filter(function(c){return RW[f.key].cines[c];}).map(function(c){
        return '<span class="chip '+cc(c)+'">'+esc(SALAS[c].corto)+'</span>';}).join('');
      var meta=[];
      if(f.duracion)meta.push(esc(f.duracion));
      if(f.genero)meta.push(esc(f.genero));
      if(f.clasificacion)meta.push('<span class="cls">'+esc(f.clasificacion)+'</span>');
      if(f.director)meta.push('Dir. '+esc(f.director));
      if(f.elenco)meta.push(esc(f.elenco));
      var ids=Object.keys(cines).sort(function(a,b){
        if(dist[a]!=null&&dist[b]!=null&&dist[a]!==dist[b]) return dist[a]-dist[b];
        return ORD.indexOf(a)-ORD.indexOf(b);});
      var fil=ids.map(function(c){
        var dd=dist[c]!=null?' <span class="fdist">· '+km(dist[c])+'</span>':'';
        return '<div class="fila"><span class="fila-n"><span class="dot '+cc(c)+'"></span>'+
          esc(SALAS[c].nombre)+dd+'</span><span class="horarios">'+times(cines[c][S.dia])+'</span></div>';}).join('');
      return '<article class="card"><h3>'+scoreHTML(f)+esc(f.titulo)+'</h3><div class="chips">'+chips+'</div>'+
        '<div class="meta">'+meta.join(' <i>·</i> ')+'</div>'+CF.enlacesHTML(f)+
        (f.sinopsis?'<p class="sinopsis">'+esc(f.sinopsis)+'</p>':'')+
        '<div class="porcine">'+fil+'</div></article>';}).join('')
      ||'<p class="vacio-in">'+(CF.contarFiltros(S.f)||S.f.zona.modo!=='todos'
        ?'Ninguna función cumple con estos filtros.':'Sin funciones para este día.')+'</p>';
  }
  function renderSalas(RD,zs,hayF){
    var out=[], ocultas=0, sinDatos=[];
    zs.forEach(function(z){
      var c=z.id;
      if(z.sinDatos){sinDatos.push(SALAS[c].nombre); return;}
      var fs=list.filter(function(f){return RD[f.key].cines[c]&&RD[f.key].cines[c][S.dia];});
      fs.sort(orden);
      if(!fs.length&&hayF){ocultas++; return;}
      var body=fs.length?('<div class="tablewrap"><table><thead><tr>'+
        '<th>Película</th><th>RT</th><th>TMDb</th><th>Horarios</th><th>Duración</th><th>Género</th><th>Director</th><th>Calif.</th>'+
        '</tr></thead><tbody>'+fs.map(function(f){
          var hs=RD[f.key].cines[c][S.dia].map(function(r){return r.h+(r.lang?' '+r.lang:'');}).join('  ');
          return '<tr><td class="tit">'+esc(f.titulo)+'</td><td class="num">'+
            (f.rt==null?'—':f.rt+'%')+'</td><td class="num">'+
            (f.score==null?'—':f.score.toFixed(1))+'</td><td class="hs">'+esc(hs)+
            '</td><td class="num">'+esc(f.duracion||'—')+'</td><td>'+esc(f.genero||'—')+
            '</td><td>'+esc(f.director||'—')+'</td><td class="num">'+esc(f.clasificacion||'—')+'</td></tr>';
        }).join('')+'</tbody></table></div>')
        :'<p class="vacio-in">Sin funciones publicadas para este día.</p>';
      var dd=z.dist!=null?' · a '+km(z.dist)+' en línea recta':'';
      out.push('<article class="sala"><div class="sala-head '+cc(c)+'"><h2>'+esc(SALAS[c].nombre)+
        '</h2><span class="dir">'+esc(SALAS[c].direccion)+' · '+esc(SALAS[c].barrio)+dd+'</span></div>'+body+'</article>');});
    var h=out.join('');
    if(!h&&!ocultas) h='<p class="vacio-in">No hay salas en la zona elegida.</p>';
    if(ocultas) h+='<p class="nota">'+ocultas+(ocultas===1?' sala sin funciones':' salas sin funciones')+' con estos filtros.</p>';
    if(sinDatos.length) h+='<p class="nota">Sin datos esta semana: '+esc(sinDatos.join(', '))+'.</p>';
    $('salas').innerHTML=h;
  }
  var sel=$('sel');
  var sorted=list.slice().sort(function(a,b){return a.titulo.localeCompare(b.titulo,'es');});
  function renderCal(RW){
    var pass=sorted.filter(function(f){return RW[f.key].n>0;});
    var prev=sel.value;
    sel.innerHTML=pass.map(function(f){return '<option value="'+esc(f.key)+'">'+esc(f.titulo)+'</option>';}).join('');
    if(!pass.length){$('cal').innerHTML='<p class="vacio-in">Nada cumple con estos filtros.</p>'; return;}
    sel.value=pass.some(function(f){return f.key===prev;})?prev:pass[0].key;
    var f=F[sel.value]; if(!f) return;
    var cines=RW[f.key].cines, hours=[];
    ORD.forEach(function(c){ if(!cines[c])return;
      Object.keys(cines[c]).forEach(function(d){ cines[c][d].forEach(function(r){
        var h=Math.floor(CF.horaComparable(r.h)/60); if(hours.indexOf(h)<0)hours.push(h);});});});
    hours.sort(function(a,b){return a-b;});
    if(!hours.length){$('cal').innerHTML='<p class="vacio-in">Sin funciones en estos días.</p>';return;}
    var head='<tr><th class="hcol"></th>'+DAYS.map(function(d){var L=lbl(d);
      return '<th>'+L[0]+' <span style="opacity:.6">'+L[1]+'</span></th>';}).join('')+'</tr>';
    var body=hours.map(function(h){
      var hh=h%24;
      return '<tr><td class="hcol">'+(hh<10?'0':'')+hh+':00'+(h>=24?'<small>trasnoche</small>':'')+'</td>'+DAYS.map(function(d){
        var cells='';
        ORD.forEach(function(c){ if(!cines[c]||!cines[c][d])return;
          cines[c][d].forEach(function(r){
            if(Math.floor(CF.horaComparable(r.h)/60)!==h)return;
            cells+='<span class="slot '+cc(c)+'" title="'+esc(SALAS[c].nombre)+'"><em>'+esc(abrev(c))+'</em>'+r.h+
              (r.lang?'<u>'+r.lang+'</u>':'')+'</span>';});});
        return '<td>'+cells+'</td>';}).join('')+'</tr>';}).join('');
    $('cal').innerHTML='<table><thead>'+head+'</thead><tbody>'+body+'</tbody></table>';
  }
  sel.addEventListener('change',function(){renderCal(ULT.RW);});

  // ---------- resumen de zona, contador y render general ----------
  var ULT={RW:{}};
  function actualizarContadorFiltros(){setTxt('ff-n',CF.contarFiltros(S.f));}
  function resumenZona(z){
    if(z.modo==='barrios'&&z.barrios.length){
      var b=z.barrios.slice(0,2).join(', ')+(z.barrios.length>2?' +'+(z.barrios.length-2):'');
      return b;}
    if(z.modo==='cerca'){
      if(!z.centro) return 'Cerca de… (elegí un punto)';
      var n=z.centro.tipo==='s'?SALAS[z.centro.ref].corto:z.centro.tipo==='b'?z.centro.ref:z.centro.label;
      return 'A ≤ '+z.radio+' km de '+n;}
    return 'Toda la ciudad';
  }
  function siguienteRadio(r){var o=[1,2,3,5,10]; for(var i=0;i<o.length;i++) if(o[i]>r) return o[i]; return null;}
  function render(){
    var a=ctxAhora(), z=S.f.zona;
    var zs=CF.filtrarSalas(SALAS,S.f,ORD);
    var ids=zs.map(function(x){return x.id;}), dist={};
    zs.forEach(function(x){if(x.dist!=null) dist[x.id]=x.dist;});
    var RD={}, RW={};
    var cD={dia:S.dia,hoy:a.hoy,ahoraMin:a.min}, cW={dia:null,hoy:a.hoy,ahoraMin:a.min};
    list.forEach(function(f){RD[f.key]=CF.filtrarFunciones(f,ids,S.f,cD); RW[f.key]=CF.filtrarFunciones(f,ids,S.f,cW);});
    ULT.RW=RW;
    var hayF=CF.contarFiltros(S.f)>0;
    renderCards(RD,RW,dist); renderSalas(RD,zs,hayF); renderCal(RW);
    // zona
    var conDatos=zs.filter(function(x){return !x.sinDatos;}), sd=zs.filter(function(x){return x.sinDatos;});
    var info=conDatos.length+(conDatos.length===1?' sala':' salas')+' en la zona';
    if(z.modo==='cerca'&&z.centro&&!conDatos.length){
      var nx=siguienteRadio(z.radio);
      info+=nx?'. <button type="button" class="flink" id="fz-ampliar">Ampliar radio a '+nx+' km</button>':'. Es el radio máximo';
    }
    if(sd.length) info+='. Sin datos esta semana: '+esc(sd.map(function(x){return SALAS[x.id].nombre;}).join(', '));
    $('fz-info').innerHTML=info+'.';
    var am=$('fz-ampliar'); if(am) am.addEventListener('click',function(){S.f.zona.radio=siguienteRadio(S.f.zona.radio); cambio();});
    setTxt('fz-res',resumenZona(z)+' · '+conDatos.length+(conDatos.length===1?' sala':' salas'));
    // contador (del día elegido; en Calendario, de toda la ventana)
    var M=S.pane==='calendario'?RW:RD, np=0, nf=0;
    list.forEach(function(f){if(M[f.key].n>0){np++; nf+=M[f.key].n;}});
    setTxt('fcount',np+(np===1?' película':' películas')+' · '+nf+(nf===1?' función':' funciones')+
      (S.pane==='calendario'?' (toda la ventana)':''));
    actualizarContadorFiltros();
  }

  // Encabezado, leyenda y fuentes salen del padron (D.salas).
  $('kicker').textContent=ORD.length+' salas · CABA';
  $('leyenda').innerHTML=ORD.map(function(c){
    return '<i><span class="dot '+cc(c)+'"></span>'+esc(SALAS[c].nombre)+'</i>';}).join('');
  var doms=[];ORD.forEach(function(c){var d=DOMINIOS[SALAS[c].fuente];if(d&&doms.indexOf(d)<0)doms.push(d);});
  $('fuentes').textContent='Fuentes: '+doms.join(' · ');
  var fu=ORD.map(function(c){return SALAS[c].fuente;});
  var nota=[];
  if(fu.indexOf('atlas')>=0)nota.push('Atlas informa el idioma función por función');
  if(fu.indexOf('cinemark')>=0)nota.push('Cinemark y Hoyts sólo publican los idiomas disponibles por película, así que la letra aparece únicamente cuando la película se da en un solo idioma');
  if(fu.indexOf('gaumont')>=0)nota.push('El Gaumont no publica idioma');
  $('nota-cal').innerHTML='<b>D</b> doblada · <b>S</b> subtitulada. '+
    nota.join('. ')+'.';
  if(INI.vencida&&DAYS.length){var U2=lbl(DAYS[DAYS.length-1]);
    var av=$('faviso'); av.hidden=false;
    av.textContent='La cartelera es del '+U2[0]+' '+U2[1]+'; puede estar desactualizada.';}

  construirBarra(); sincronizar(); renderDays(); render();
  // Escritorio: zona y filtros abiertos; celular: plegados.
  try{if(window.matchMedia&&window.matchMedia('(min-width:601px)').matches){
    $('fz').open=true; $('ff').open=true;}}catch(e){}

  Array.prototype.forEach.call(document.querySelectorAll('.mtab'),function(b){
    b.addEventListener('click',function(){
      Array.prototype.forEach.call(document.querySelectorAll('.mtab'),function(x){x.classList.remove('on');});
      Array.prototype.forEach.call(document.querySelectorAll('.pane'),function(p){p.classList.remove('on');});
      b.classList.add('on'); S.pane=b.getAttribute('data-pane');
      $('pane-'+S.pane).classList.add('on'); render();});});
})();}
