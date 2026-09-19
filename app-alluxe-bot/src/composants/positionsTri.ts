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
import { miseConseillee, nomCrypto, resultatEnDirect } from "../services/format";

/** L'etage de pyramide : 1 = position d'origine, 2 et au-dela = renforts
 *  ajoutes quand elle etait deja a l'abri. Lu en fin de reference
 *  (`<id>:<etage>`), que le robot construit a la publication. */
export function etagePyramide(p: Position): number {
  const fin = (p.reference ?? "").split(":").pop();
  const n = Number.parseInt(fin ?? "", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
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
    p.position_size_pct ?? 0, capitalOuverture,
  );
  return {
    eur, pctPrix,
    mise: miseConseillee(p.entry_price, p.stop_loss,
                         p.position_size_pct ?? 0, capitalOuverture),
    etage: etagePyramide(p),
  };
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

