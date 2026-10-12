// Le « flyer » alluxe.ia de la boutique de Noël (12 oct.) : chaque client du portrait
// voit les services numériques. Prix lus dans /offres.json, la seule source des prix
// du site (jamais recopiés ici). Si le fichier ne répond pas, le bloc disparaît.
(() => {
  const bloc = document.getElementById("pros");
  if (!bloc) return;
  const CHOIX = ["noel_boutique", "noel_campagne", "autopost", "vitrine"];
  fetch("/offres.json", { cache: "no-store" }).then((r) => r.json()).then(({ offres, promo }) => {
    const liste = CHOIX.map((id) => offres.find((o) => o.id === id)).filter(Boolean);
    if (!liste.length) throw new Error("aucune offre");
    bloc.querySelector(".pros-offres").innerHTML = liste.map((o) => `
      <a class="pro" href="/offres.html#${o.id}">
        <b>${o.nom}</b><span>${o.accroche}</span>
        <em>dès ${o.unique} €${o.mensuel ? ` <small>ou ${o.mensuel} €/mois</small>` : ""}</em>
      </a>`).join("");
    const p = bloc.querySelector(".pros-promo");
    if (p && promo && new Date(promo.fin) > Date.now()) p.textContent = `🎁 ${promo.titre} : ${promo.texte}.`;
    bloc.hidden = false;
  }).catch(() => bloc.remove());
})();
