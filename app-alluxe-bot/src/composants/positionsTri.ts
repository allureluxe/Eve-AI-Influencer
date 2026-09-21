/**
 * Le calcul et le tri des positions -- SANS React et SANS Supabase.
 *
 * Separe des composants pour une raison concrete : le test de tri
 * importait `ListePositions.tsx`, donc `robot.ts`, donc le client
 * Supabase, donc AsyncStorage -- un module natif qui n'existe pas en
 * test. Une logique pure qui traine tout l'appareillage derriere elle
 * est une logique qu'on finit par ne plus tester.
 *
 * `Position` est importe en TYPE seul : l'import disparait a la
 * compilation, et rien de `robot.ts` n'est charge a l'execution.
 */
import type { Position } from "../services/robot";
import { miseReelle, nomCrypto, resultatEnDirect } from "../services/format";

/** L'etage de pyramide : 1 = position d'origine, 2 et au-dela = renforts
 *  ajoutes quand elle etait deja a l'abri. Lu en fin de reference
 *  (`<id>:<etage>`), que le robot construit a la publication. */
export function etagePyramide(p: Position): number {
  const fin = (p.reference ?? "").split(":").pop();
  const n = Number.parseInt(fin ?? "", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

/**
 * LES ETAGES VUS DEPUIS LA LISTE, ET PAS SEULEMENT DEPUIS LA REFERENCE.
 *
 * Retour de l'operateur le 20 septembre : « plusieurs positions sur la
 * meme crypto ont ete achetees, si ce sont des etages de pyramide alors
 * c'est mal inscrit sur l'application, Avalanche a plusieurs positions
 * ouvertes mais toutes a l'etage 1 ».
 *
 * Il a raison. Le simulateur creait une position NEUVE a chaque achat
 * au lieu de fusionner comme le vrai courtier -- corrige le 19 sept. au
 * soir, mais les positions ouvertes AVANT restent deux lignes
 * distinctes, chacune marquee « etage 1 » dans sa reference. C'est vrai
 * ligne par ligne, et faux a l'ecran : l'operateur voit deux fois le
 * meme etage pour deux achats successifs.
 *
 * On complete donc la reference par ce que la LISTE montre : quand
 * plusieurs positions ouvertes portent la meme crypto, elles sont
 * numerotees dans l'ordre d'achat. Le deuxieme achat d'Avalanche est
 * bien son deuxieme etage, quoi qu'en dise sa reference.
 *
 * La reference reste prioritaire quand elle dit mieux (>= 2) : sur le
 * vrai courtier, les achats fusionnent en UNE position dont la
 * reference porte le vrai compte d'etages.
 */
export function etagesAffiches(positions: Position[]): Record<string, number> {
  const parPaire: Record<string, Position[]> = {};
  for (const p of positions) {
    (parPaire[p.pair] ??= []).push(p);
  }
  const etages: Record<string, number> = {};
  for (const lignes of Object.values(parPaire)) {
    const ordonnees = [...lignes].sort((a, b) =>
      new Date(a.published_at).getTime() - new Date(b.published_at).getTime());
    ordonnees.forEach((p, i) => {
      etages[p.id] = Math.max(etagePyramide(p), i + 1);
    });
  }
  return etages;
}

export const TRIS = [
  { cle: "gain", libelle: "Gain" },
  { cle: "mise", libelle: "Mise" },
  { cle: "recent", libelle: "Récent" },
  { cle: "nom", libelle: "Nom" },
] as const;

export type Tri = (typeof TRIS)[number]["cle"];

export interface Chiffres {
  eur: number;
  pctPrix: number;
  mise: number;
  etage: number;
}

/** Les chiffres d'une position, ou `null` si la cotation manque encore. */
export function chiffresDe(
  p: Position, capital: number, prixActuel: number | undefined,
): Chiffres | null {
  if (prixActuel == null) return null;
  // Le capital FIGE a l'ouverture, jamais le courant : sinon une
  // position prise a 500 EUR et relue a 3 300 afficherait une mise
  // 6,6 fois trop grosse.
  const capitalOuverture = p.capital_eur ?? capital;
  const { pctPrix, eur } = resultatEnDirect(
    p.entry_price, p.stop_loss, prixActuel, p.side,
    p.position_size_pct ?? 0, capitalOuverture, p.volume,
  );
  return {
    eur, pctPrix,
    // `miseReelle`, pas `miseConseillee` : sur une pyramide fusionnee la
    // deduction par la distance au stop explose (RUNE : 3 732 EUR
    // affiches pour 550 engages, sur un compte de 3 300).
    mise: miseReelle(p.entry_price, p.stop_loss,
                     p.position_size_pct ?? 0, capitalOuverture, p.volume),
    etage: etagePyramide(p),
  };
}

/**
 * Le gain latent de TOUTES les positions, en euros.
 *
 * POURQUOI CETTE FONCTION EXISTE. Ce total etait calcule a la main dans
 * `Demo.tsx`, par un `reduce` de quatre lignes. Le 21 septembre, les
 * LIGNES affichaient les bons chiffres (RUNE +10,92 EUR) pendant que ce
 * total annoncait 154,45 EUR pour 54,80 reels : l'appel inline avait
 * ete ecrit sans le volume, donc il retombait sur l'ancienne deduction
 * par la distance au stop.
 *
 * C'etait la QUATRIEME fois que cette division se retournait. La cause
 * n'est pas la formule -- elle est juste depuis le 20 septembre -- mais
 * le fait qu'un ECRAN refasse le calcul dans son coin, hors de portee
 * des tests. On passe donc par `chiffresDe`, exactement comme les
 * lignes : un seul chemin, un seul resultat possible.
 */
export function gainTotalEnDirect(
  positions: Position[], capital: number,
  prixLive: Record<string, number>,
): number {
  return positions.reduce((somme, p) => {
    const ch = chiffresDe(p, capital, prixLive[p.pair]);
    return ch == null ? somme : somme + ch.eur;
  }, 0);
}

/**
 * Trie les positions. Les cotations manquantes finissent toujours en bas
 * -- une position dont on ignore le resultat n'a pas sa place au milieu
 * d'un classement par resultat.
 */
export function trier(
  positions: Position[], tri: Tri, descendant: boolean,
  capital: number, prixLive: Record<string, number>,
): Position[] {
  const valeur = (p: Position): number | null => {
    if (tri === "recent") return new Date(p.published_at).getTime();
    if (tri === "nom") return null;          // traite a part, c'est du texte
    const ch = chiffresDe(p, capital, prixLive[p.pair]);
    if (ch == null) return null;
    return tri === "gain" ? ch.eur : ch.mise;
  };

  const sansChiffre: Position[] = [];
  const avecChiffre: { p: Position; v: number }[] = [];
  const parNom: Position[] = [];

  for (const p of positions) {
    if (tri === "nom") { parNom.push(p); continue; }
    const v = valeur(p);
    if (v == null) sansChiffre.push(p);
    else avecChiffre.push({ p, v });
  }

  if (tri === "nom") {
    const ordonnees = [...parNom].sort((a, b) =>
      nomCrypto(a.pair).localeCompare(nomCrypto(b.pair), "fr"));
    return descendant ? ordonnees.reverse() : ordonnees;
  }

  avecChiffre.sort((a, b) => (descendant ? b.v - a.v : a.v - b.v));
  return [...avecChiffre.map((x) => x.p), ...sansChiffre];
}

