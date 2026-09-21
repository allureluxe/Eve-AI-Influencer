/**
 * La mise en forme des chiffres.
 *
 * Regle unique et non negociable : ON PARLE EN EUROS, JAMAIS EN JARGON.
 * Pas de « R », pas d'ATR, pas de « multiple ». L'utilisateur vise ne
 * connait rien au trading — un chiffre qu'il ne comprend pas est un
 * chiffre qui le fait douter de tout le reste.
 */

const NOMS: Record<string, string> = {
  BTC: "Bitcoin", ETH: "Ethereum", SOL: "Solana", XRP: "XRP",
  ADA: "Cardano", DOGE: "Dogecoin", LINK: "Chainlink", AVAX: "Avalanche",
  DOT: "Polkadot", LTC: "Litecoin", ATOM: "Cosmos", MATIC: "Polygon",
};

export function nomCrypto(paire: string): string {
  const base = paire.split("/")[0].toUpperCase();
  return NOMS[base] ?? base;
}

export function symbole(paire: string): string {
  return paire.split("/")[0].toUpperCase();
}

/** Un prix, avec juste ce qu'il faut de decimales pour rester exact. */
export function prix(valeur: number): string {
  const d = valeur >= 1000 ? 0 : valeur >= 1 ? 2 : valeur >= 0.01 ? 4 : 8;
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: d, maximumFractionDigits: d,
  });
}

export function euros(valeur: number, decimales = 2): string {
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: decimales, maximumFractionDigits: decimales,
  }) + " €";
}

export function pourcent(valeur: number, decimales = 1): string {
  const signe = valeur > 0 ? "+" : "";
  return signe + valeur.toFixed(decimales).replace(".", ",") + " %";
}

/** « aujourd'hui 14h30 », « demain 9h00 », « jeudi 14h30 ». */
export function quand(iso: string): string {
  const d = new Date(iso);
  const heure = d.toLocaleTimeString("fr-FR", {
    hour: "2-digit", minute: "2-digit",
  }).replace(":", "h");

  const jourDe = (x: Date) =>
    new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const ecart = Math.round((jourDe(d) - jourDe(new Date())) / 86_400_000);

  if (ecart === 0) return `aujourd'hui ${heure}`;
  if (ecart === 1) return `demain ${heure}`;
  if (ecart === -1) return `hier ${heure}`;
  if (ecart > 1 && ecart < 7) {
    return `${d.toLocaleDateString("fr-FR", { weekday: "long" })} ${heure}`;
  }
  return `${d.toLocaleDateString("fr-FR", {
    day: "numeric", month: "short" })} ${heure}`;
}

/** La date seule, pour un signal clos. */
export function jour(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "numeric", month: "short",
  });
}

/**
 * Ce que la position peut couter, EN EUROS, sur un capital donne.
 *
 * C'est le chiffre que l'utilisateur cherche vraiment. « 0,6 % de
 * risque » ne veut rien dire pour lui ; « au pire tu perds 3 € » se
 * comprend immediatement.
 *
 * ATTENTION AU SENS DE `position_size_pct`. Le robot y publie le
 * POURCENTAGE DU CAPITAL RISQUE, pas la somme engagee. Les deux se
 * ressemblent et different d'un facteur trente : sur ce signal, 0,6 %
 * de risque correspond a environ 18 % du capital engage. Prendre l'un
 * pour l'autre afficherait « tu peux perdre 60 € » la ou c'est 2 €.
 *
 * La perte maximale est donc directe :
 *
 *     perte = capital x position_size_pct / 100
 */
export function perteMax(partRisqueePct: number, capital: number): number {
  if (capital <= 0 || partRisqueePct <= 0) return 0;
  return capital * (partRisqueePct / 100);
}

/**
 * La somme engagee, deduite du risque et de la distance au stop.
 *
 *     mise = perte / (|entree - stop| / entree)
 *
 * Sert a repondre a « combien j'achete ? », qui est la question
 * suivante une fois qu'on sait ce qu'on risque.
 */
export function miseConseillee(
  entree: number, stop: number, partRisqueePct: number, capital: number,
): number {
  const distance = entree > 0 ? Math.abs(entree - stop) / entree : 0;
  if (distance <= 0) return 0;
  return perteMax(partRisqueePct, capital) / distance;
}

export interface ResultatDirect {
  /** Variation du PRIX lui-meme, signee selon le sens (achat/vente). */
  pctPrix: number;
  /** Gain ou perte en euros, EN DIRECT, pendant que la position est ouverte. */
  eur: number;
}

/**
 * Le resultat d'une position OUVERTE, en direct -- demande explicite de
 * l'operateur (18 sept.) : « style trading, juste le nom de la crypto,
 * le pourcentage et le benefice ou negatif en euro ».
 *
 * Le robot ne publie ni le volume ni la mise engagee (voir `perteMax` :
 * seul `position_size_pct`, le RISQUE, part vers l'application). Le
 * calcul reste exact malgre ça : chaque position est dimensionnee pour
 * que perdre jusqu'au stop coute exactement `perteMax()` -- donc, quel
 * que soit le prix actuel :
 *
 *     R_courant = (prix_actuel - entree) / (entree - stop) x sens
 *     gain_eur  = R_courant x perteMax(risque, capital)
 *
 * Pas une approximation : le meme calcul que celui qui a servi a
 * dimensionner la position (`gold_bot/trade_manager.py`), juste relu
 * depuis l'autre bout.
 */
export function resultatEnDirect(
  entree: number, stop: number, prixActuel: number,
  side: "buy" | "sell", partRisqueePct: number, capital: number,
  volume?: number | null,
): ResultatDirect {
  const sens = side === "sell" ? -1 : 1;
  const pctPrix = entree > 0 ? ((prixActuel - entree) / entree) * 100 * sens : 0;

  // LE VOLUME D'ABORD -- MEME CORRECTION QUE `gainEnEuros`, ET ELLE
  // AVAIT ETE OUBLIEE ICI.
  //
  // Le 20 septembre, `gainEnEuros` a ete corrigee pour lire le volume
  // plutot que de deduire la mise de la distance au stop. Cette
  // fonction-ci fait le meme calcul pour les positions OUVERTES, et
  // elle est restee sur l'ancienne formule : l'historique disait vrai
  // pendant que l'ecran en direct mentait.
  //
  // Mesure du 21 septembre sur RUNE, demo 1, pyramide a 3 etages :
  //
  //     mise reelle      1 104,02 RUNE x 0,49866  =   550,53 EUR
  //     mise affichee                                3 732,55 EUR
  //     gain reel                                       +0,71 EUR
  //     gain affiche                                    +4,89 EUR
  //
  // La cause est toujours la meme division : apres une fusion, le stop
  // remonte sous le DERNIER achat alors que l'entree est une MOYENNE,
  // donc la distance entre les deux devient minuscule -- et la mise,
  // qui se calcule en divisant par elle, explose. Sur un compte de
  // 3 300 EUR, l'application annoncait 3 732 EUR engages sur une seule
  // crypto.
  //
  // TROISIEME FOIS que cette division se retourne (18, 20 et 21
  // septembre), et TROISIEME FOIS que l'operateur la voit avant moi :
  // « un chiffre qui es faut rune qui es a 3700 mise on les a meme
  // pas ». La lecon n'est pas « corriger la formule » mais « corriger
  // TOUS les appelants » -- une correction posee a un seul endroit
  // laisse l'autre mentir.
  if (volume != null && volume > 0 && entree > 0) {
    return { pctPrix, eur: volume * (prixActuel - entree) * sens };
  }

  const distanceStop = Math.abs(entree - stop);
  if (distanceStop <= 0) return { pctPrix, eur: 0 };
  const rCourant = ((prixActuel - entree) * sens) / distanceStop;
  const eur = rCourant * perteMax(partRisqueePct ?? 0, capital);
  return { pctPrix, eur };
}

/**
 * La somme REELLEMENT engagee sur une position ouverte.
 *
 * `miseConseillee` repond a « combien FAUDRAIT-IL acheter ? » a partir
 * du risque et de la distance au stop. Ce n'est pas la meme question
 * que « combien A-T-ON achete ? », et les deux reponses divergent des
 * qu'une pyramide fusionne. Quand le volume est publie, il n'y a rien
 * a deduire : on multiplie.
 */
export function miseReelle(
  entree: number, stop: number, partRisqueePct: number, capital: number,
  volume?: number | null,
): number {
  if (volume != null && volume > 0 && entree > 0) return volume * entree;
  return miseConseillee(entree, stop, partRisqueePct, capital);
}

/**
 * Ce qu'un trade DEJA FERME a rapporte, en euros.
 *
 * L'historique n'affichait qu'un pourcentage -- or `result_pct` est la
 * variation du PRIX, pas le gain. Un "+2 %" ne dit rien tant qu'on ne
 * sait pas combien etait engage dessus. Demande de l'operateur le
 * 19 sept. : "dans historique on n'a pas les montants en euros".
 *
 * Le gain se deduit de la mise, qui se deduit elle-meme du risque
 * publie et de la distance au stop (voir `miseConseillee`) :
 *
 *     gain = mise x variation_du_prix
 */
export function gainEnEuros(
  entree: number, stop: number, resultatPct: number | null,
  partRisqueePct: number | null, capital: number,
  volume?: number | null,
): number | null {
  if (resultatPct == null) return null;

  // LE VOLUME D'ABORD, QUAND ON L'A. C'est le calcul exact :
  //
  //     gain = quantité × prix d'achat × variation
  //
  // La déduction par la distance au stop (plus bas) reste juste tant
  // que la position n'a qu'un étage. Dès qu'une pyramide FUSIONNE, elle
  // devient fausse -- et spectaculairement.
  //
  // Vu le 20 septembre sur DYDX : après la fusion, le prix d'achat
  // devient une moyenne et le stop remonte sous le dernier achat, donc
  // la distance entre les deux DEVIENT MINUSCULE. Or la mise se calcule
  // en divisant PAR cette distance : l'application annonçait 538 € de
  // mise pour une position qui en engageait 240, et une perte de
  // 17,72 € là où le robot avait perdu 7,95 €.
  //
  // C'est la même division par un nombre qui rétrécit que le 18
  // septembre, quand une position simulée affichait « 600 % de
  // bénéfice ». L'opérateur l'a repérée les deux fois avant moi.
  if (volume != null && volume > 0 && entree > 0) {
    return volume * entree * (resultatPct / 100);
  }

  const mise = miseConseillee(entree, stop, partRisqueePct ?? 0, capital);
  if (mise <= 0) return null;
  return mise * (resultatPct / 100);
}

/**
 * Regroupe les étages d'une même position en UNE ligne.
 *
 * Un trade pyramidé est publié en plusieurs lignes -- une par étage,
 * référence `<id>:1`, `<id>:2`... C'est voulu : chaque renfort est un
 * signal à part entière pour l'utilisateur. Mais à la CLÔTURE, il n'y a
 * qu'une position qui se ferme une seule fois.
 *
 * L'historique les additionnait : DYDX apparaissait deux fois, et sa
 * perte était comptée deux fois.
 *
 * On garde l'étage le PLUS HAUT de chaque position : c'est lui qui
 * porte le volume cumulé et le prix d'achat moyen, donc le seul qui
 * décrive la position telle qu'elle s'est fermée.
 */
export function regrouperLesEtages<T extends {
  reference: string | null; id: string;
}>(lignes: T[]): T[] {
  const parPosition = new Map<string, T>();
  for (const l of lignes) {
    const ref = l.reference ?? l.id;
    const [identifiant, etage] = ref.split(":");
    const cle = identifiant || l.id;
    const n = Number.parseInt(etage ?? "1", 10) || 1;
    const deja = parPosition.get(cle);
    if (!deja) { parPosition.set(cle, l); continue; }
    const nDeja = Number.parseInt(
      (deja.reference ?? "").split(":")[1] ?? "1", 10) || 1;
    if (n > nDeja) parPosition.set(cle, l);
  }
  return [...parPosition.values()];
}
