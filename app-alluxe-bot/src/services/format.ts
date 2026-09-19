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
): ResultatDirect {
  const sens = side === "sell" ? -1 : 1;
  const pctPrix = entree > 0 ? ((prixActuel - entree) / entree) * 100 * sens : 0;
  const distanceStop = Math.abs(entree - stop);
  if (distanceStop <= 0) return { pctPrix, eur: 0 };
  const rCourant = ((prixActuel - entree) * sens) / distanceStop;
  const eur = rCourant * perteMax(partRisqueePct ?? 0, capital);
  return { pctPrix, eur };
}
