(function(){
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
  var list=Object.keys(F).map(function(k){return F[k];});
  // Tolera que falte un nodo: antes, un id que la plantilla no traía cortaba
  // el script entero y la página salía en blanco.
  function setTxt(id,t){var e=document.getElementById(id); if(e) e.textContent=t;}
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
  })();

  function dayTabs(el,cb){
    el.innerHTML=DAYS.map(function(d,i){var L=lbl(d);
      return '<button class="tab'+(i===0?' on':'')+'" data-day="'+d+'"><b>'+L[0]+'</b><span>'+L[1]+'</span></button>';}).join('');
    el.querySelectorAll('.tab').forEach(function(b){
      b.addEventListener('click',function(){
        el.querySelectorAll('.tab').forEach(function(x){x.classList.remove('on');});
        b.classList.add('on'); cb(b.getAttribute('data-day'));});});
  }
  function times(rows){
    return rows.map(function(r){
      var lg=r.lang?'<u>'+r.lang+'</u>':'';
      var fm=r.fmt?' <span class="fmt">'+esc(r.fmt)+'</span>':'';
      return '<span class="hora">'+r.h+lg+'</span>'+fm;}).join('');
  }
  // ---------- tab 1 ----------
  function renderCards(day){
    var rows=list.filter(function(f){
      return ORD.some(function(c){return f.cines[c]&&f.cines[c][day];});});
    rows.sort(orden);
    document.getElementById('cards').innerHTML=rows.map(function(f){
      var chips=ORD.filter(function(c){return f.cines[c];}).map(function(c){
        return '<span class="chip '+cc(c)+'">'+esc(SALAS[c].corto)+'</span>';}).join('');
      var meta=[];
      if(f.duracion)meta.push(esc(f.duracion));
      if(f.genero)meta.push(esc(f.genero));
      if(f.clasificacion)meta.push('<span class="cls">'+esc(f.clasificacion)+'</span>');
      if(f.director)meta.push('Dir. '+esc(f.director));
      if(f.elenco)meta.push(esc(f.elenco));
      var fil=ORD.filter(function(c){return f.cines[c]&&f.cines[c][day];}).map(function(c){
        return '<div class="fila"><span class="fila-n"><span class="dot '+cc(c)+'"></span>'+
          esc(SALAS[c].nombre)+'</span><span class="horarios">'+times(f.cines[c][day])+'</span></div>';}).join('');
      return '<article class="card"><h3>'+scoreHTML(f)+esc(f.titulo)+'</h3><div class="chips">'+chips+'</div>'+
        '<div class="meta">'+meta.join(' <i>·</i> ')+'</div>'+
        (f.sinopsis?'<p class="sinopsis">'+esc(f.sinopsis)+'</p>':'')+
        '<div class="porcine">'+fil+'</div></article>';}).join('')
      ||'<p class="vacio-in">Sin funciones para este día.</p>';
  }
  // ---------- tab 2 ----------
  function renderSalas(day){
    document.getElementById('salas').innerHTML=ORD.map(function(c){
      var fs=list.filter(function(f){return f.cines[c]&&f.cines[c][day];});
      fs.sort(orden);
      var body=fs.length?('<div class="tablewrap"><table><thead><tr>'+
        '<th>Película</th><th>RT</th><th>TMDb</th><th>Horarios</th><th>Duración</th><th>Género</th><th>Director</th><th>Calif.</th>'+
        '</tr></thead><tbody>'+fs.map(function(f){
          var hs=f.cines[c][day].map(function(r){return r.h+(r.lang?' '+r.lang:'');}).join('  ');
          return '<tr><td class="tit">'+esc(f.titulo)+'</td><td class="num">'+
            (f.rt==null?'—':f.rt+'%')+'</td><td class="num">'+
            (f.score==null?'—':f.score.toFixed(1))+'</td><td class="hs">'+esc(hs)+
            '</td><td class="num">'+esc(f.duracion||'—')+'</td><td>'+esc(f.genero||'—')+
            '</td><td>'+esc(f.director||'—')+'</td><td class="num">'+esc(f.clasificacion||'—')+'</td></tr>';
        }).join('')+'</tbody></table></div>')
        :'<p class="vacio-in">Sin funciones publicadas para este día.</p>';
      return '<article class="sala"><div class="sala-head '+cc(c)+'"><h2>'+esc(SALAS[c].nombre)+
        '</h2><span class="dir">'+esc(SALAS[c].direccion)+' · '+esc(SALAS[c].barrio)+'</span></div>'+body+'</article>';}).join('');
  }
  // ---------- tab 3 ----------
  var sel=document.getElementById('sel');
  var sorted=list.slice().sort(function(a,b){return a.titulo.localeCompare(b.titulo,'es');});
  sel.innerHTML=sorted.map(function(f,i){
    return '<option value="'+esc(f.key)+'">'+esc(f.titulo)+'</option>';}).join('');
  function renderCal(){
    var f=F[sel.value]; if(!f)return;
    var hours=[];
    ORD.forEach(function(c){ if(!f.cines[c])return;
      DAYS.forEach(function(d){ (f.cines[c][d]||[]).forEach(function(r){
        var h=parseInt(r.h.split(':')[0],10); if(hours.indexOf(h)<0)hours.push(h);});});});
    hours.sort(function(a,b){return a-b;});
    if(!hours.length){document.getElementById('cal').innerHTML=
      '<p class="vacio-in">Sin funciones en estos días.</p>';return;}
    var head='<tr><th class="hcol"></th>'+DAYS.map(function(d){var L=lbl(d);
      return '<th>'+L[0]+' <span style="opacity:.6">'+L[1]+'</span></th>';}).join('')+'</tr>';
    var body=hours.map(function(h){
      return '<tr><td class="hcol">'+(h<10?'0':'')+h+':00</td>'+DAYS.map(function(d){
        var cells='';
        ORD.forEach(function(c){ if(!f.cines[c])return;
          (f.cines[c][d]||[]).forEach(function(r){
            if(parseInt(r.h.split(':')[0],10)!==h)return;
            cells+='<span class="slot '+cc(c)+'" title="'+esc(SALAS[c].nombre)+'"><em>'+esc(abrev(c))+'</em>'+r.h+
              (r.lang?'<u>'+r.lang+'</u>':'')+'</span>';});});
        return '<td>'+cells+'</td>';}).join('')+'</tr>';}).join('');
    document.getElementById('cal').innerHTML='<table><thead>'+head+'</thead><tbody>'+body+'</tbody></table>';
  }
  sel.addEventListener('change',renderCal);

  // Encabezado, leyenda y fuentes salen del padron (D.salas).
  document.getElementById('kicker').textContent=ORD.length+' salas · CABA';
  document.getElementById('leyenda').innerHTML=ORD.map(function(c){
    return '<i><span class="dot '+cc(c)+'"></span>'+esc(SALAS[c].nombre)+'</i>';}).join('');
  var doms=[];ORD.forEach(function(c){var d=DOMINIOS[SALAS[c].fuente];if(d&&doms.indexOf(d)<0)doms.push(d);});
  document.getElementById('fuentes').textContent='Fuentes: '+doms.join(' · ');
  var fu=ORD.map(function(c){return SALAS[c].fuente;});
  var nota=[];
  if(fu.indexOf('atlas')>=0)nota.push('Atlas informa el idioma función por función');
  if(fu.indexOf('cinemark')>=0)nota.push('Cinemark y Hoyts sólo publican los idiomas disponibles por película, así que la letra aparece únicamente cuando la película se da en un solo idioma');
  if(fu.indexOf('gaumont')>=0)nota.push('El Gaumont no publica idioma');
  document.getElementById('nota-cal').innerHTML='<b>D</b> doblada · <b>S</b> subtitulada. '+
    nota.join('. ')+'.';

  dayTabs(document.getElementById('days-1'),renderCards);
  dayTabs(document.getElementById('days-2'),renderSalas);
  renderCards(DAYS[0]); renderSalas(DAYS[0]); renderCal();

  document.querySelectorAll('.mtab').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('.mtab').forEach(function(x){x.classList.remove('on');});
      document.querySelectorAll('.pane').forEach(function(p){p.classList.remove('on');});
      b.classList.add('on');
      document.getElementById('pane-'+b.getAttribute('data-pane')).classList.add('on');});});
})();
