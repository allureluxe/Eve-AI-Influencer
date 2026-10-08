// Éléments communs à toutes les pages d'alluxe.fr : barre, pied de page,
// assistant, apparition au défilement. Une seule copie, jamais recopiée.
(() => {
  const PAGES = [["index.html", "Accueil"], ["concours.html", "🎁 Concours"], ["kit.html", "Kit gratuit"], ["offres.html", "Offres & prix"], ["kits.html", "Kits à faire soi-même"],
    ["realisations.html", "Réalisations"], ["prompts.html", "Prompts gratuits"]];
  const ici = location.pathname.split("/").pop() || "index.html";
  const barre = document.createElement("div");
  barre.className = "barre";
  barre.innerHTML = `<div class="conteneur"><a href="index.html" style="display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit">
    <img src="logo-alluxe.png" alt="Logo Alluxe"><b>alluxe.ia</b></a>
    <button class="menu" aria-label="Menu">☰</button>
    <nav>${PAGES.map(([u, t]) => `<a href="${u}"${u === ici ? ' class="ici"' : ""}>${t}</a>`).join("")}
    <a class="cadre" href="commander.html">Commander →</a></nav></div>`;
  document.body.prepend(barre);
  barre.querySelector(".menu").onclick = () => barre.querySelector("nav").classList.toggle("ouvert");

  const pied = document.createElement("footer");
  pied.innerHTML = `<div class="conteneur"><div class="liens"><a href="kit.html">Kit gratuit</a><a href="offres.html">Offres</a><a href="commander.html">Commander</a>
    <a href="https://www.instagram.com/alluxe.ia/">Instagram</a><a href="mentions-legales.html">Mentions légales</a><a href="cgv.html">CGV</a></div>
    Les réponses de l'IA sont à vérifier : elles ne remplacent pas un conseil juridique, médical ou financier.<br>© alluxe.ia</div>`;
  document.body.appendChild(pied);

  const obs = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("vu"); obs.unobserve(e.target); }
  }), { threshold: 0.12 });
  window.observer = (el) => obs.observe(el);
  document.querySelectorAll(".apparait, h2").forEach((el) => obs.observe(el));

  // Assistant (fonction Edge alluxe-site-assistant).
  document.body.insertAdjacentHTML("beforeend", `<button id="bulle" aria-label="Poser une question"><img src="logo-alluxe.png" alt=""></button>
    <section id="fenetre" aria-label="Assistant alluxe.ia"><header><img src="logo-alluxe.png" alt="">Assistant alluxe.ia<button id="fermer" aria-label="Fermer">×</button></header>
    <div id="fil"></div><form id="saisie"><input id="texte" maxlength="600" placeholder="Ta question…" autocomplete="off"><button>➤</button></form>
    <small>Réponses générées par une IA, à vérifier. Aucun conseil financier.</small></section>`);
  const ADRESSE = "https://jwksajhtvhwktkbkpits.supabase.co/functions/v1/alluxe-site-assistant";
  const bulle = document.getElementById("bulle"), fenetre = document.getElementById("fenetre");
  const fil = document.getElementById("fil"), form = document.getElementById("saisie"), champ = document.getElementById("texte");
  const historique = [];
  const ajouter = (texte, qui) => { const d = document.createElement("div"); d.className = "msg " + qui; d.textContent = texte;
    fil.appendChild(d); fil.scrollTop = fil.scrollHeight; return d; };
  let accueilli = false;
  bulle.onclick = () => { fenetre.classList.toggle("ouverte");
    if (!accueilli) { accueilli = true; ajouter("Salut ! Une question sur nos offres, un site, une boutique, un agent IA, ou sur les prompts ?", "ia"); }
    champ.focus(); };
  document.getElementById("fermer").onclick = () => fenetre.classList.remove("ouverte");
  form.onsubmit = async (e) => {
    e.preventDefault(); const q = champ.value.trim(); if (!q) return;
    champ.value = ""; ajouter(q, "moi"); historique.push({ role: "user", content: q });
    const attente = ajouter("…", "ia");
    try {
      const r = await fetch(ADRESSE, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: historique.slice(-8) }) });
      const d = await r.json(); const rep = d.reponse || "Je n'arrive pas à répondre pour l'instant, réessaie plus tard.";
      attente.textContent = rep; if (d.reponse) historique.push({ role: "assistant", content: rep }); else historique.pop();
    } catch { attente.textContent = "Connexion impossible, réessaie dans un instant."; historique.pop(); }
    fil.scrollTop = fil.scrollHeight;
  };

  // Les prix viennent d'un seul fichier (offres.json).
  let offresEnCours = null;   // un seul téléchargement de offres.json par page
  window.chargerOffres = () => (offresEnCours ||= fetch("offres.json").then((r) => r.json()));

  // Noël (8 oct.) : bandeau avec compte à rebours + neige, tant que l'offre court.
  // La date de fin vient de offres.json (« promo.fin ») : après, tout disparaît seul.
  window.chargerOffres().then(({ promo }) => {
    if (!promo || new Date(promo.fin) <= new Date()) return;
    document.body.classList.add("noel");
    const b = document.createElement("a");
    b.className = "bandeau-noel"; b.href = "offres.html#cat-noel";
    b.innerHTML = `<span class="sapin">🎄</span> <b></b> <span class="texte"></span> <span class="decompte"></span>`;
    b.querySelector("b").textContent = promo.titre + " :";
    b.querySelector(".texte").textContent = promo.texte;
    document.querySelector(".barre")?.after(b);
    // Compte à rebours en cases (jours / h / min / s), comme un calendrier.
    const fin = new Date(promo.fin).getTime(), z = b.querySelector(".decompte");
    z.innerHTML = ["j", "h", "min", "s"].map((u) => `<span class="case"><b>00</b>${u}</span>`).join("");
    const cases = z.querySelectorAll("b");
    const tic = () => {
      const s = Math.max(0, Math.floor((fin - Date.now()) / 1000));
      [Math.floor(s / 86400), Math.floor(s / 3600) % 24, Math.floor(s / 60) % 60, s % 60]
        .forEach((v, i) => { cases[i].textContent = String(v).padStart(2, "0"); });
      if (!s) { b.remove(); document.body.classList.remove("noel"); }
    };
    tic(); setInterval(tic, 1000);

    // 9 oct. : décor de Noël « premium » (tendance des sites d'agence : peu
    // d'éléments, tons profonds rouge/or, animations lentes). Tout est décoratif
    // (aria-hidden) et s'éteint avec la classe .noel au 25 décembre.
    const deco = (cls, html = "") => {
      const d = document.createElement("div"); d.className = cls; d.setAttribute("aria-hidden", "true");
      d.innerHTML = html; return d;
    };
    // Guirlande lumineuse, accrochée sous le dernier bandeau (elle pend sur le haut de page).
    const bandeaux = document.querySelectorAll(".bandeau-noel, .bandeau-kit");
    bandeaux[bandeaux.length - 1].after(deco("guirlande", Array.from({ length: 26 }, (_, i) => `<i style="--i:${i}"></i>`).join("")));
    // Boules suspendues + étiquette « Édition Noël » dans le haut de page.
    const hero = document.querySelector(".eventail") || document.querySelector("header .conteneur");
    if (hero) {
      hero.appendChild(deco("boules", ["rouge", "or", "vert"].map((c, i) =>
        `<span class="boule ${c}" style="--n:${i}"><i></i></span>`).join("")));
      hero.appendChild(deco("etiquette-noel", "🎁 Édition Noël"));
    }
    // De la neige qui « tient » sur les blocs forts de la page.
    document.querySelectorAll(".chiffres, .final .boite, .duel .panneau").forEach((el) => {
      el.classList.add("enneige"); el.prepend(deco("congere"));
    });
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const neige = deco("neige");
      const n = innerWidth < 700 ? 18 : 34;
      for (let i = 0; i < n; i++) {
        const f = document.createElement("i"); f.textContent = ["❄", "❅", "•", "✻"][i % 4];
        f.style.left = Math.random() * 100 + "vw"; f.style.fontSize = 8 + Math.random() * 16 + "px";
        f.style.animationDuration = 9 + Math.random() * 10 + "s"; f.style.animationDelay = -Math.random() * 19 + "s";
        f.style.setProperty("--derive", (Math.random() * 80 - 40).toFixed(0) + "px");
        f.style.opacity = 0.4 + Math.random() * 0.5; neige.appendChild(f);
      }
      document.body.appendChild(neige);
    }
  });
  window.euros = (n) => n.toLocaleString("fr-FR") + " €";
})();
