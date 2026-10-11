// Boutique de Noël : catalogue lu dans catalogue.json (jamais recopié ici),
// comparateur avant/après, compte à rebours, liste d'attente.
const euros = (n) => n.toLocaleString("fr-FR", { style: "currency", currency: "EUR" });

// Comparateur
const curseur = document.getElementById("curseur");
curseur.oninput = () => {
  document.getElementById("avant").style.clipPath = `inset(0 ${100 - curseur.value}% 0 0)`;
  document.getElementById("poignee").style.left = curseur.value + "%";
};

fetch("catalogue.json", { cache: "no-store" }).then((r) => r.json()).then((cat) => {
  // Compte à rebours jusqu'à la dernière commande livrable pour Noël
  const fin = new Date(cat.date_limite_noel), rebours = document.getElementById("rebours");
  const tic = () => {
    const ms = fin - Date.now();
    if (ms <= 0) { document.getElementById("bandeau").remove(); return; }
    const j = Math.floor(ms / 864e5), h = Math.floor(ms / 36e5) % 24, m = Math.floor(ms / 6e4) % 60;
    rebours.textContent = `encore ${j} j ${h} h ${m} min`;
  };
  tic(); setInterval(tic, 30000);

  document.getElementById("styles").innerHTML = cat.styles.map((s) =>
    `<div class="style"><h3>${s.nom}</h3><p>${s.texte}</p></div>`).join("");
  document.getElementById("choix-style").innerHTML = cat.styles.map((s) =>
    `<option value="${s.id}">${s.nom}</option>`).join("");

  const actifs = cat.produits.filter((p) => p.actif);
  document.getElementById("grille").innerHTML = actifs.map((p) => `
    <article class="produit">${p.vedette ? '<span class="badge">Le plus choisi</span>' : ""}
      <img src="${p.image}" alt="${p.nom}" loading="lazy">
      <div class="corps"><h3>${p.nom}</h3><p>${p.texte}</p>
        <span class="prix">${euros(p.prix)}</span>
        <a href="#commander" data-produit="${p.id}">Choisir →</a></div>
    </article>`).join("");
  const choix = document.getElementById("choix-produit");
  choix.innerHTML = actifs.map((p) => `<option value="${p.id}">${p.nom} — ${euros(p.prix)}</option>`).join("");
  document.querySelectorAll("[data-produit]").forEach((a) => a.onclick = () => { choix.value = a.dataset.produit; });

  if (cat.commandes_ouvertes) {
    document.getElementById("etat-commandes").textContent = "Envoyez votre demande : on vous répond avec l'aperçu.";
    document.getElementById("envoyer").textContent = "Envoyer ma demande";
  }
});

// Liste d'attente : même fonction que le bon de commande d'alluxe.fr (offre « noel »).
const form = document.getElementById("formulaire"), retour = document.getElementById("retour"), bouton = document.getElementById("envoyer");
form.onsubmit = async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(form).entries());
  if (!form.consentement.checked) { retour.textContent = "Cochez la case pour qu'on puisse vous écrire."; return; }
  const corps = { offre: "noel", formule: "unique", nom: f.nom, email: f.email, site_web: f.site_web,
    consentement: true, activite: f.sujet, message: `noel | style=${f.style} | produit=${f.produit} | sujet=${f.sujet}` };
  bouton.disabled = true; retour.textContent = "Envoi…";
  try {
    const r = await fetch("https://jwksajhtvhwktkbkpits.supabase.co/functions/v1/alluxe-site-demande",
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(corps) });
    const d = await r.json();
    if (d.ok) form.innerHTML = `<div class="message-ok">C'est noté ! Vous serez prévenu par e-mail dès l'ouverture des commandes.</div>`;
    else { retour.textContent = d.erreur || "Une erreur est survenue, réessayez."; bouton.disabled = false; }
  } catch { retour.textContent = "Connexion impossible, réessayez dans un instant."; bouton.disabled = false; }
};
