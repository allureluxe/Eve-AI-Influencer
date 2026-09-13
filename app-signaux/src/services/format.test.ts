/**
 * La conversion en euros est le seul calcul de l'application.
 *
 * Elle merite des tests parce que je m'y suis deja trompe en
 * l'ecrivant : `position_size_pct` est le POURCENTAGE DU CAPITAL
 * RISQUE, pas la somme engagee. Confondre les deux affichait « au pire
 * tu perds 60 € » la ou c'etait 2 € — soit trente fois trop, sur le
 * chiffre le plus important de l'ecran.
 */

import { euros, miseConseillee, nomCrypto, perteMax, pourcent, prix }
  from "./format";

describe("ce que la position peut couter", () => {
  test("la perte maximale est le capital fois le pourcentage risque", () => {
    // 1 000 € de capital, 0,6 % de risque -> 6 €. Directement.
    expect(perteMax(0.6, 1000)).toBeCloseTo(6, 6);
    expect(perteMax(0.6, 225)).toBeCloseTo(1.35, 6);
  });

  test("un capital ou un pourcentage absurde rend zero, pas une erreur", () => {
    // Mieux vaut ne rien afficher qu'un chiffre invente.
    expect(perteMax(0.6, 0)).toBe(0);
    expect(perteMax(0, 1000)).toBe(0);
    expect(perteMax(-1, 1000)).toBe(0);
  });

  test("la mise se deduit du risque et de la distance au stop", () => {
    // Entree 100, stop 95 : on risque 5 % du montant engage.
    // Pour ne perdre que 6 €, il faut engager 120 €.
    expect(miseConseillee(100, 95, 0.6, 1000)).toBeCloseTo(120, 4);
  });

  test("un stop colle au prix d'entree ne fait pas exploser la mise", () => {
    // Division par zero : on rend 0 plutot qu'un infini affiche.
    expect(miseConseillee(100, 100, 0.6, 1000)).toBe(0);
  });

  test("la mise est toujours superieure a la perte maximale", () => {
    // Sanity : on engage plus qu'on ne risque, sinon le stop serait
    // au-dela de zero.
    const perte = perteMax(0.6, 1000);
    expect(miseConseillee(100, 95, 0.6, 1000)).toBeGreaterThan(perte);
  });
});

describe("l'affichage des chiffres", () => {
  test("un prix garde assez de decimales pour rester exact", () => {
    // Un jeton a 0,00001234 € affiche « 0 € » serait faux.
    expect(prix(58420.42)).not.toMatch(/,/);      // gros prix : entier
    expect(prix(2.5)).toMatch(/2,50/);
    expect(prix(0.00001234)).toMatch(/0,00001234/);
  });

  test("un pourcentage porte toujours son signe", () => {
    expect(pourcent(4.23)).toBe("+4,2 %");
    expect(pourcent(-1.85)).toBe("-1,9 %");
    // Zero n'est ni un gain ni une perte : pas de « +0,0 % ».
    expect(pourcent(0)).toBe("0,0 %");
  });

  test("les euros s'ecrivent a la francaise", () => {
    expect(euros(1234.5)).toContain("€");
    expect(euros(1234.5)).toContain(",50");
  });

  test("les cryptos portent leur nom, ou leur symbole a defaut", () => {
    expect(nomCrypto("BTC/EUR")).toBe("Bitcoin");
    expect(nomCrypto("SOL/EUR")).toBe("Solana");
    // Inventer un nom pour une crypto inconnue serait pire.
    expect(nomCrypto("PENDLE/EUR")).toBe("PENDLE");
  });
});
