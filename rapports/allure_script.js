/* ---------- graphique ---------- */
(function(){
  const svg = document.getElementById('chart');
  const W = 900, H = 320, PL = 58, PR = 14, PT = 18, PB = 30;
  const xs = POINTS.map(p => p[0]), ys = POINTS.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  // On borne l'axe sur les valeurs reelles, avec une marge de 6 %.
  const lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo) * .06;
  const yLo = lo - pad, yHi = hi + pad;
  const X = t => PL + (t - x0) / (x1 - x0) * (W - PL - PR);
  const Y = v => PT + (yHi - v) / (yHi - yLo) * (H - PT - PB);

  const css = getComputedStyle(document.documentElement);
  const C = n => css.getPropertyValue(n).trim();
  const ns = 'http://www.w3.org/2000/svg';
  const el = (t, a) => { const e = document.createElementNS(ns, t);
    for (const k in a) e.setAttribute(k, a[k]); return e; };

  // Degrade de remplissage sous la courbe : dense pres du trait,
  // transparent au niveau de l'axe.
  const defs = el('defs', {});
  const g = el('linearGradient', {id:'deg', x1:0, y1:0, x2:0, y2:1});
  const s1 = el('stop', {offset:'0%',  'stop-color':C('--jaune'), 'stop-opacity':.95});
  const s2 = el('stop', {offset:'100%','stop-color':C('--jaune'), 'stop-opacity':.15});
  g.appendChild(s1); g.appendChild(s2); defs.appendChild(g); svg.appendChild(defs);

  // Grille horizontale, graduee au demi-euro : a cette echelle c'est
  // l'unite que l'oeil sait lire sans calculer.
  const pas = 0.5;
  for (let v = Math.ceil(yLo / pas) * pas; v <= yHi; v += pas){
    const y = Y(v), rond = Math.abs(v - Math.round(v)) < 1e-9;
    svg.appendChild(el('line', {x1:PL, y1:y, x2:W-PR, y2:y,
      stroke:C('--line-soft'), 'stroke-width':rond ? 1.4 : 1,
      'stroke-dasharray': rond ? '' : '2 4'}));
    const tx = el('text', {x:PL-10, y:y+4, fill:C('--ink-faint'),
      'font-size':11.5, 'text-anchor':'end',
      'font-family':'IBM Plex Mono, monospace'});
    tx.textContent = v.toFixed(rond ? 0 : 2).replace('.', ',') + ' €';
    svg.appendChild(tx);
  }

  // Reperes de temps toutes les 6 h : la periode fait 32 h, l'heure
  // est l'echelle a laquelle ces mouvements se lisent.
  const TZ = 'Europe/Paris';
  const heure = t => +new Intl.DateTimeFormat('fr-FR',
    {hour:'2-digit', hour12:false, timeZone:TZ}).format(new Date(t*1000));
  const jour = t => new Intl.DateTimeFormat('fr-FR',
    {day:'numeric', month:'short', timeZone:TZ}).format(new Date(t*1000));

  const H6 = 6 * 3600;
  for (let t = Math.ceil((x0 + 5400) / H6) * H6; t <= x1 - 3600; t += H6){
    const x = X(t), h = heure(t);
    svg.appendChild(el('line', {x1:x, y1:PT, x2:x, y2:H-PB,
      stroke:C('--line-soft'), 'stroke-width':1, 'stroke-dasharray':'2 5'}));
    const e = el('text', {x, y:H-9, fill:C('--ink-faint'), 'font-size':11,
      'text-anchor':'middle', 'font-family':'Archivo, sans-serif'});
    e.textContent = (h === 0 ? jour(t) : h + ' h');
    svg.appendChild(e);
  }

  // Les deux bouts, toujours nommes.
  [[x0, PL, 'start'], [x1, W-PR, 'end']].forEach(([t, x, anc]) => {
    const e = el('text', {x, y:H-9, fill:C('--ink-soft'), 'font-size':11,
      'text-anchor':anc, 'font-weight':500, 'font-family':'Archivo, sans-serif'});
    e.textContent = jour(t) + ' ' + String(heure(t)).padStart(2,'0') + ' h';
    svg.appendChild(e);
  });

  // Ligne de depart : tout ce qui est au-dessus est du gain.
  const yDep = Y(POINTS[0][1]);
  svg.appendChild(el('line', {x1:PL, y1:yDep, x2:W-PR, y2:yDep,
    stroke:C('--ink-faint'), 'stroke-width':1.5, 'stroke-dasharray':'6 4'}));
  const dep = el('text', {x:W-PR-4, y:yDep-7, fill:C('--ink-soft'),
    'font-size':11.5, 'text-anchor':'end', 'font-family':'Archivo, sans-serif'});
  dep.textContent = 'départ 365,90 €';
  svg.appendChild(dep);

  // On coupe la courbe la ou le robot etait arrete (trou > 2 h) :
  // relier les deux bouts dessinerait une chute qui n'a pas eu lieu.
  const segs = [[]];
  POINTS.forEach((p, i) => {
    if (i && p[0] - POINTS[i-1][0] > 7200) segs.push([]);
    segs[segs.length-1].push(p);
  });

  segs.forEach(seg => {
    if (seg.length < 2) return;
    const d = seg.map((p,i) => (i?'L':'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join(' ');
    const aire = d + ' L' + X(seg[seg.length-1][0]).toFixed(1) + ' ' + (H-PB)
               + ' L' + X(seg[0][0]).toFixed(1) + ' ' + (H-PB) + ' Z';
    svg.appendChild(el('path', {d:aire, fill:'url(#deg)'}));
    // Le trait n'est pas noir : c'est le jaune du logo pousse au fonce.
    // Il se detache du remplissage sans assombrir le graphique.
    svg.appendChild(el('path', {d, fill:'none', stroke:C('--olive'),
      'stroke-width':3, 'stroke-linejoin':'round', 'stroke-linecap':'round'}));
  });

  // Chaque trade ferme, pose sur la courbe : on voit ce qui a bouge
  // le solde et ce qui n'etait que le prix des positions ouvertes.
  const val = t => {
    let b = POINTS[0];
    for (const p of POINTS){ if (p[0] <= t) b = p; else break; }
    return b[1];
  };
  TRADES.forEach(tr => {
    if (tr.c < x0 || tr.c > x1) return;
    svg.appendChild(el('circle', {cx:X(tr.c), cy:Y(val(tr.c)), r:4.5,
      fill: tr.p >= 0 ? C('--gain') : C('--loss'),
      stroke:C('--surface'), 'stroke-width':2}));
  });

  // Point final, appuye.
  const last = POINTS[POINTS.length-1];
  svg.appendChild(el('circle', {cx:X(last[0]), cy:Y(last[1]), r:6,
    fill:C('--jaune'), stroke:C('--olive'), 'stroke-width':3}));
  const fin = el('text', {x:X(last[0])-10, y:Y(last[1])-12, fill:C('--olive'),
    'font-size':13, 'text-anchor':'end', 'font-weight':600,
    'font-family':'IBM Plex Mono, monospace'});
  fin.textContent = '361,04 €';
  svg.appendChild(fin);
})();

/* ---------- tableau ---------- */
(function(){
  const tb = document.getElementById('trades');
  const maxR = Math.max(...TRADES.map(t => Math.abs(t.r)));
  const css = getComputedStyle(document.documentElement);
  TRADES.forEach(t => {
    const tr = document.createElement('tr');
    const d = new Date(t.c*1000);
    const fr = new Intl.DateTimeFormat('fr-FR', {day:'2-digit', month:'2-digit',
      hour:'2-digit', minute:'2-digit', hour12:false,
      timeZone:'Europe/Paris'}).format(d).replace(' ', ' à ');
    const cls = t.p > 0 ? 'pos' : 'neg';
    const col = t.p > 0 ? 'var(--gain)' : 'var(--loss)';
    const w = Math.abs(t.r)/maxR*50;                      // 50 % = demi-largeur
    const style = t.r >= 0
      ? `left:50%;width:${w}%;background:var(--gain)`
      : `right:50%;width:${w}%;background:var(--loss)`;
    tr.innerHTML =
      `<td class="num" style="color:var(--ink-soft)">${fr}</td>`+
      `<td class="sym">${t.s.replace('USD','')}</td>`+
      `<td><span class="bar"><i class="mid"></i><i style="${style}"></i></span></td>`+
      `<td class="r num ${cls}">${t.r>=0?'+':''}${t.r.toFixed(2)}</td>`+
      `<td class="r num ${cls}">${t.p>=0?'+':''}${t.p.toFixed(2)} €</td>`;
    tb.appendChild(tr);
  });
})();
</script>
