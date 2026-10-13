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
  // Pour Google : les produits avec leur prix (précommande tant que les commandes sont fermées)
  const ld = document.createElement("script");
  ld.type = "application/ld+json";
  ld.textContent = JSON.stringify({ "@context": "https://schema.org", "@type": "ItemList", name: "Cadeaux de Noël personnalisés",
    itemListElement: cat.produits.filter((p) => p.actif && p.prix).map((p, i) => ({ "@type": "ListItem", position: i + 1, item: {
      "@type": "Product", name: p.nom, description: p.texte, image: new URL(p.image, location.href).href, brand: { "@type": "Brand", name: "alluxe" },
      offers: { "@type": "Offer", price: p.prix.toFixed(2), priceCurrency: "EUR", url: location.origin + location.pathname,
        availability: cat.commandes_ouvertes ? "https://schema.org/InStock" : "https://schema.org/PreOrder" } } })) });
  document.head.appendChild(ld);
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
  // 12 oct. : la boutique complète est rangée par rayons ; un produit dont le
  // fournisseur n'est pas encore branché s'affiche « Bientôt », sans bouton.
  const carte = (p) => p.actif ? `
    <article class="produit">${p.vedette ? '<span class="badge">Le plus choisi</span>' : ""}
      <img src="${p.image}" alt="${p.nom}" loading="lazy">
      <div class="corps"><h3>${p.nom}</h3><p>${p.texte}</p>
        <span class="prix">${euros(p.prix)}</span>${p.livraison ? `<small class="port">+ ${euros(p.livraison)} de livraison</small>` : ""}
        <a href="#commander" data-produit="${p.id}">Choisir →</a></div>
    </article>` : `
    <article class="produit bientot"><span class="badge">Bientôt</span>
      <img src="${p.image}" alt="${p.nom}" loading="lazy">
      <div class="corps"><h3>${p.nom}</h3><p>${p.texte}</p>
        <span class="prix">${p.prix ? euros(p.prix) : "Prix bientôt"}</span></div>
    </article>`;
  const rayons = cat.categories || [{ id: "portrait", nom: "", texte: "" }];
  document.getElementById("grille").innerHTML = rayons.map((r) => {
    const lot = cat.produits.filter((p) => (p.categorie || "portrait") === r.id && p.texte)
                            .sort((x, y) => (y.actif ? 1 : 0) - (x.actif ? 1 : 0));
    if (!lot.length) return "";
    return `<div class="rayon" id="rayon-${r.id}"><h3>❄ ${r.nom}</h3><p>${r.texte}</p></div>` + lot.map(carte).join("");
  }).join("");
  const choix = document.getElementById("choix-produit");
  choix.innerHTML = actifs.map((p) => `<option value="${p.id}">${p.nom} — ${euros(p.prix)}${p.livraison ? " + livraison " + euros(p.livraison) : ""}</option>`).join("");
  document.querySelectorAll("[data-produit]").forEach((a) => a.onclick = () => { choix.value = a.dataset.produit; });

  if (cat.commandes_ouvertes) {
    ouvert = true;
    document.getElementById("etat-commandes").textContent = "Envoyez la photo, payez, et recevez l'aperçu par e-mail avant impression.";
    document.getElementById("envoyer").textContent = "Commander et payer";
    document.querySelectorAll(".si-ouvert").forEach((e) => e.hidden = false);
    document.querySelectorAll(".si-ferme").forEach((e) => e.hidden = true);
  }
});

let ouvert = false, photo = null;
// Photo redimensionnée dans le navigateur (2048 px, JPEG) : légère à envoyer, et
// les photos HEIC d'iPhone sont converties par Safari au passage.
document.getElementById("photo").onchange = (e) => {
  const f = e.target.files[0]; if (!f) return;
  const img = new Image();
  img.onload = () => {
    const k = Math.min(1, 2048 / Math.max(img.width, img.height));
    const cv = document.createElement("canvas"); cv.width = img.width * k; cv.height = img.height * k;
    cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
    photo = cv.toDataURL("image/jpeg", 0.9);
    const v = document.getElementById("vignette"); v.src = photo; v.hidden = false;
  };
  img.src = URL.createObjectURL(f);
};

async function commander(f) {
  if (!photo) { retour.textContent = "Ajoutez une photo."; return; }
  if (!form.cgv.checked) { retour.textContent = "Cochez la case des conditions de vente."; return; }
  bouton.disabled = true; retour.textContent = "Envoi de la photo…";
  try {
    const r = await fetch("https://jwksajhtvhwktkbkpits.supabase.co/functions/v1/boutique-commande", { method: "POST",
      headers: { "content-type": "application/json" }, body: JSON.stringify({ produit: f.produit, style: f.style,
        sujet: f.sujet, prenom: f.nom, email: f.email, site_web: f.site_web, cgv: true, photo }) });
    const d = await r.json();
    if (d.paiement) { location.href = d.paiement; return; }
    retour.textContent = d.erreur || "Une erreur est survenue, réessayez."; bouton.disabled = false;
  } catch { retour.textContent = "Connexion impossible, réessayez dans un instant."; bouton.disabled = false; }
}

// Liste d'attente : même fonction que le bon de commande d'alluxe.fr (offre « noel »).
const form = document.getElementById("formulaire"), retour = document.getElementById("retour"), bouton = document.getElementById("envoyer");
form.onsubmit = async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(form).entries());
  if (ouvert) return commander(f);
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
