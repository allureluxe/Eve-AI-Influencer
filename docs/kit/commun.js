// Éléments communs à toutes les pages d'alluxe.fr : barre, pied de page,
// assistant, apparition au défilement. Une seule copie, jamais recopiée.
(() => {
  const PAGES = [["index.html", "Accueil"], ["offres.html", "Offres & prix"], ["realisations.html", "Réalisations"],
    ["prompts.html", "Prompts gratuits"]];
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
  pied.innerHTML = `<div class="conteneur"><div class="liens"><a href="offres.html">Offres</a><a href="commander.html">Commander</a>
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
  window.chargerOffres = () => fetch("offres.json").then((r) => r.json());
  window.euros = (n) => n.toLocaleString("fr-FR") + " €";
})();
