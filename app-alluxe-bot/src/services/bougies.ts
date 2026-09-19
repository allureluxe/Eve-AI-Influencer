/**
 * Les bougies d'une crypto, pour le graphique de l'ecran Position.
 *
 * POURQUOI PAS LE WIDGET TRADINGVIEW TOUT FAIT.
 *
 * L'operateur a demande « le mode TradingView ». Le widget officiel
 * afficherait le graphique de la PLATEFORME TradingView -- qui ne
 * reference pas toutes les paires que le robot traite (il en suit 240
 * chez Bitvavo, dont beaucoup d'altcoins recents), et qui affiche alors
 * une boite de recherche vide a la place du graphique.
 *
 * On dessine donc le meme graphique avec `lightweight-charts`, la
 * bibliotheque publiee par TradingView eux-memes, alimentee par les
 * bougies de BITVAVO -- exactement la source que le robot utilise pour
 * decider. Le graphique montre donc ce que le robot a vu, pas une autre
 * cotation qui lui ressemble.
 *
 * Les unites de temps sont celles demandees : 1 m, 5 m, 15 m, 30 m,
 * 1 h, 4 h, 1 jour.
 */

export const UNITES = [
  { cle: "1m", libelle: "1 m" },
  { cle: "5m", libelle: "5 m" },
  { cle: "15m", libelle: "15 m" },
  { cle: "30m", libelle: "30 m" },
  { cle: "1h", libelle: "1 h" },
  { cle: "4h", libelle: "4 h" },
  { cle: "1d", libelle: "1 j" },
] as const;

export type Unite = (typeof UNITES)[number]["cle"];

export interface Bougie {
  /** Secondes depuis l'epoque -- ce qu'attend lightweight-charts. */
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

/** "BTC/EUR" -> "BTC-EUR", le format des marches Bitvavo. */
export function marcheBitvavo(paire: string): string {
  return paire.replace("/", "-").toUpperCase();
}

/**
 * Les `limite` dernieres bougies. Rend un tableau vide plutot que de
 * lever : un graphique absent ne doit pas emporter l'ecran entier, qui
 * porte aussi le stop et le resultat de la position.
 */
export async function bougies(
  paire: string, unite: Unite, limite = 300,
): Promise<Bougie[]> {
  const marche = marcheBitvavo(paire);
  const url = `https://api.bitvavo.com/v2/${marche}/candles`
    + `?interval=${unite}&limit=${limite}`;
  try {
    const reponse = await fetch(url);
    if (!reponse.ok) return [];
    const brut = (await reponse.json()) as unknown;
    if (!Array.isArray(brut)) return [];
    // Bitvavo rend [horodatage_ms, ouverture, haut, bas, cloture, volume],
    // du PLUS RECENT au plus ancien. lightweight-charts exige l'ordre
    // chronologique strict : sans ce retournement il n'affiche rien, et
    // sans message d'erreur.
    const lues = brut
      .map((l) => {
        const [ms, o, h, b, c] = l as [number, string, string, string, string];
        return {
          time: Math.floor(Number(ms) / 1000),
          open: Number(o), high: Number(h), low: Number(b), close: Number(c),
        };
      })
      .filter((x) => Number.isFinite(x.time) && Number.isFinite(x.close));
    lues.sort((a, b) => a.time - b.time);
    return lues;
  } catch {
    return [];
  }
}
