const NOMS: Record<string, string> = {
  BTC: "Bitcoin", ETH: "Ethereum", SOL: "Solana", XRP: "XRP",
  ADA: "Cardano", DOGE: "Dogecoin", LINK: "Chainlink", AVAX: "Avalanche",
  DOT: "Polkadot", LTC: "Litecoin", ATOM: "Cosmos", MATIC: "Polygon",
};
export function nomCrypto(paire: string): string { const base = paire.split("/")[0].toUpperCase(); return NOMS[base] ?? base; }
export function symbole(paire: string): string { return paire.split("/")[0].toUpperCase(); }
export function prix(valeur: number): string { const d = valeur >= 1000 ? 0 : valeur >= 1 ? 2 : valeur >= 0.01 ? 4 : 8; return valeur.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d }); }
export function euros(valeur: number, decimales = 2): string { return valeur.toLocaleString("fr-FR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales }) + " €"; }
export function pourcent(valeur: number, decimales = 1): string { const signe = valeur > 0 ? "+" : ""; return signe + valeur.toFixed(decimales).replace(".", ",") + " %"; }
export function quand(iso: string): string { const d = new Date(iso); const heure = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }).replace(":", "h"); const jourDe = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(); const ecart = Math.round((jourDe(d) - jourDe(new Date())) / 86_400_000); if (ecart === 0) return "aujourd'hui " + heure; if (ecart === 1) return "demain " + heure; if (ecart === -1) return "hier " + heure; if (ecart > 1 && ecart < 7) return d.toLocaleDateString("fr-FR", { weekday: "long" }) + " " + heure; return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) + " " + heure; }
export function jour(iso: string): string { return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }); }
export function perteMax(partRisqueePct: number, capital: number): number { if (capital <= 0 || partRisqueePct <= 0) return 0; return capital * (partRisqueePct / 100); }
export function miseConseillee(entree: number, stop: number, partRisqueePct: number, capital: number): number { const distance = entree > 0 ? Math.abs(entree - stop) / entree : 0; if (distance <= 0) return 0; return perteMax(partRisqueePct, capital) / distance; }
export interface ResultatDirect { pctPrix: number; eur: number; }
export function resultatEnDirect(entree: number, stop: number, prixActuel: number, side: "buy" | "sell", partRisqueePct: number, capital: number, volume?: number | null): ResultatDirect { const sens = side === "sell" ? -1 : 1; const pctPrix = entree > 0 ? ((prixActuel - entree) / entree) * 100 * sens : 0; if (volume != null && volume > 0 && entree > 0) return { pctPrix, eur: volume * (prixActuel - entree) * sens }; const distanceStop = Math.abs(entree - stop); if (distanceStop <= 0) return { pctPrix, eur: 0 }; const rCourant = ((prixActuel - entree) * sens) / distanceStop; return { pctPrix, eur: rCourant * perteMax(partRisqueePct ?? 0, capital) }; }
export function miseReelle(entree: number, stop: number, partRisqueePct: number, capital: number, volume?: number | null): number { if (volume != null && volume > 0 && entree > 0) return volume * entree; return miseConseillee(entree, stop, partRisqueePct, capital); }
export function gainEnEuros(entree: number, stop: number, resultatPct: number | null, partRisqueePct: number | null, capital: number, volume?: number | null): number | null { if (resultatPct == null) return null; if (volume != null && volume > 0 && entree > 0) return volume * entree * (resultatPct / 100); const mise = miseConseillee(entree, stop, partRisqueePct ?? 0, capital); if (mise <= 0) return null; return mise * (resultatPct / 100); }
export function gainRealiseDe(p: { profit_eur?: number | null; entry_price: number; stop_loss: number; result_pct: number | null; position_size_pct: number | null; capital_eur?: number | null; volume?: number | null; }, capitalParDefaut: number): number | null { if (p.profit_eur != null) return p.profit_eur; return gainEnEuros(p.entry_price, p.stop_loss, p.result_pct, p.position_size_pct, p.capital_eur ?? capitalParDefaut, p.volume); }

/**
 * L'HISTORIQUE REEL, FUSIONNE SANS DOUBLON NI GAIN PERDU (11 oct. 2026).
 *
 * L'operateur : « l'affichage des positions historique est faux ». Mesure
 * ce soir-la : 128 lignes et −95,04 EUR affiches pour −75,43 EUR reels.
 *
 *  1. DOUBLONS : `signals` ecrit `ZKUSD~1791562517:1`, le journal `ZKUSD`.
 *     La cle de fusion gardait le `~horodatage` : 31 trades apparaissaient
 *     deux fois (−14,91 EUR comptes en double). La cle prend donc le
 *     SYMBOLE seul (avant `~` et `:`), + paire + heure de cloture.
 *  2. GAIN PERDU : les etages d'une pyramide se ferment a la meme seconde
 *     sous la meme cle. L'etage 2 (profit 0, par construction) ecrasait
 *     l'etage 1 qui porte le gain : DOS +2,92 et ATOM +1,65 s'affichaient
 *     a 0. Les etages sont donc d'abord additionnes en UNE ligne.
 *
 * Le journal ne complete que les clotures absentes de `signals`.
 */
type LigneClose = {
  id: string; reference: string | null; pair: string; closed_at: string | null;
  profit_eur?: number | null; volume?: number | null;
};

function symboleDeReference(ref: string): string {
  return ref.split(":")[0].split("~")[0];
}

function cleCloture(p: LigneClose): string {
  return symboleDeReference(p.reference ?? p.id) + "|" + p.pair + "|" + (p.closed_at ?? "");
}

export function fusionnerHistorique<T extends LigneClose>(signaux: T[], journal: T[]): T[] {
  // 1. une ligne par position close : les etages s'additionnent
  const parPosition = new Map<string, T>();
  for (const l of signaux) {
    const cle = (l.reference ?? l.id).split(":")[0] + "|" + l.pair + "|" + (l.closed_at ?? "");
    const deja = parPosition.get(cle);
    if (!deja) { parPosition.set(cle, { ...l }); continue; }
    const somme = (a?: number | null, b?: number | null) =>
      a == null && b == null ? null : (a ?? 0) + (b ?? 0);
    deja.profit_eur = somme(deja.profit_eur, l.profit_eur);
    deja.volume = somme(deja.volume, l.volume);
    // la ligne affichee reste celle du 1er etage (prix d'entree d'origine)
    const n = (x: T) => Number.parseInt((x.reference ?? "").split(":")[1] ?? "1", 10) || 1;
    if (n(l) < n(deja)) parPosition.set(cle, { ...l, profit_eur: deja.profit_eur, volume: deja.volume });
  }
  // 2. le journal ne comble que ce que `signals` n'a pas
  const fusion = new Map<string, T>();
  for (const p of journal) fusion.set(cleCloture(p), p);
  for (const p of parPosition.values()) fusion.set(cleCloture(p), p);
  return [...fusion.values()]
    .sort((a, b) => new Date(b.closed_at ?? 0).getTime() - new Date(a.closed_at ?? 0).getTime());
}

export function regrouperLesEtages<T extends { reference: string | null; id: string; profit_eur?: number | null; }>(lignes: T[]): T[] {
  const parPosition = new Map<string, T>();
  for (const l of lignes) {
    const ref = l.reference ?? l.id;
    const [identifiant, etage] = ref.split(":");
    const cle = identifiant || l.id;
    const n = Number.parseInt(etage ?? "1", 10) || 1;
    const deja = parPosition.get(cle);
    if (!deja) { parPosition.set(cle, l); continue; }
    const nDeja = Number.parseInt((deja.reference ?? "").split(":")[1] ?? "1", 10) || 1;
    if (n > nDeja) {
      if ((l.profit_eur == null || l.profit_eur === 0) && deja.profit_eur != null && deja.profit_eur !== 0) {
        (l as T & { profit_eur: number }).profit_eur = deja.profit_eur;
      }
      parPosition.set(cle, l);
    } else if ((deja.profit_eur == null || deja.profit_eur === 0) && l.profit_eur != null && l.profit_eur !== 0) {
      (deja as T & { profit_eur: number }).profit_eur = l.profit_eur;
    }
  }
  return [...parPosition.values()];
}
