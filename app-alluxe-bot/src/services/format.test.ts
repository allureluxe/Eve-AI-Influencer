import { resultatEnDirect } from "./format";

describe("le resultat en direct d'une position ouverte", () => {
  it("un achat qui monte est gagnant, en pourcentage et en euros", () => {
    const r = resultatEnDirect(100, 90, 105, "buy", 0.6, 500);
    // +5 % de prix, a mi-chemin du stop (10) -> +0,5 R
    expect(r.pctPrix).toBeCloseTo(5, 5);
    expect(r.eur).toBeCloseTo(0.5 * (500 * 0.006), 5);
  });

  it("un achat qui baisse est perdant", () => {
    const r = resultatEnDirect(100, 90, 95, "buy", 0.6, 500);
    expect(r.pctPrix).toBeLessThan(0);
    expect(r.eur).toBeLessThan(0);
  });

  it("une vente qui baisse est gagnante -- le sens inverse le signe", () => {
    const r = resultatEnDirect(100, 110, 95, "sell", 0.6, 500);
    expect(r.pctPrix).toBeGreaterThan(0);
    expect(r.eur).toBeGreaterThan(0);
  });

  it("toucher exactement le stop rend la perte maximale, pas plus", () => {
    const r = resultatEnDirect(100, 90, 90, "buy", 0.6, 500);
    expect(r.eur).toBeCloseTo(-(500 * 0.006), 5);
  });

  it("un stop colle a l'entree ne fait pas exploser le calcul", () => {
    const r = resultatEnDirect(100, 100, 105, "buy", 0.6, 500);
    expect(r.eur).toBe(0);
    expect(Number.isFinite(r.eur)).toBe(true);
  });

  it("sans pourcentage de risque publie, le gain en euros reste zero (pas NaN)", () => {
    const r = resultatEnDirect(100, 90, 105, "buy", undefined as unknown as number, 500);
    expect(r.eur).toBe(0);
  });
});

describe("le gain d'une position pyramidée", () => {
  const { gainEnEuros, regrouperLesEtages } = require("./format");

  // Le cas réel du 20 septembre. DYDX, deux étages, perte réelle du
  // robot : −7,95 €. L'application en affichait −18,81.
  const DYDX = {
    entree: 0.1153249, stop: 0.1115238,   // après fusion : stop collé à l'entrée
    volume: 2079.83771362, resultatPct: -3.2959,
    risquePct: 0.6, capital: 3300,
  };

  it("utilise le volume quand on l'a, au lieu de diviser par la distance au stop", () => {
    const juste = gainEnEuros(DYDX.entree, DYDX.stop, DYDX.resultatPct,
                              DYDX.risquePct, DYDX.capital, DYDX.volume);
    expect(juste).toBeCloseTo(-7.9, 0);
  });

  it("sans le volume, la déduction explose après une fusion", () => {
    // On documente le défaut plutôt que de prétendre qu'il n'existe pas :
    // ce repli reste juste pour une position à UN seul étage, où le stop
    // est à sa distance d'origine.
    const faux = gainEnEuros(DYDX.entree, DYDX.stop, DYDX.resultatPct,
                             DYDX.risquePct, DYDX.capital);
    expect(Math.abs(faux!)).toBeGreaterThan(15);
  });

  it("ne garde qu'une ligne par position, celle de l'étage le plus haut", () => {
    const lignes = [
      { id: "a", reference: "fbac:1" },
      { id: "b", reference: "fbac:2" },
      { id: "c", reference: "autre:1" },
    ];
    const groupees = regrouperLesEtages(lignes);
    expect(groupees).toHaveLength(2);
    expect(groupees.find((l: any) => l.reference.startsWith("fbac")).reference)
      .toBe("fbac:2");
  });

  it("garde l'étage le plus haut quel que soit l'ordre d'arrivée", () => {
    const groupees = regrouperLesEtages([
      { id: "b", reference: "x:3" },
      { id: "a", reference: "x:1" },
      { id: "c", reference: "x:2" },
    ]);
    expect(groupees).toHaveLength(1);
    expect(groupees[0].reference).toBe("x:3");
  });

  it("laisse tranquille une position sans étage dans sa référence", () => {
    expect(regrouperLesEtages([{ id: "seul", reference: null }])).toHaveLength(1);
  });
});

describe("la mise et le gain d'une position OUVERTE", () => {
  const { resultatEnDirect, miseReelle } = require("./format");

  // Chiffres reels de RUNE, demo 1, 21 septembre, pyramide a 3 etages.
  // L'entree est une MOYENNE et le stop est remonte sous le DERNIER
  // achat : la distance entre les deux est minuscule, et toute formule
  // qui DIVISE par elle explose.
  const RUNE = {
    entree: 0.49865655, stop: 0.49596495,
    volume: 1104.02362394, risque: 0.6, capital: 3357.87,
  };

  it("lit le volume au lieu de deduire la mise", () => {
    const mise = miseReelle(RUNE.entree, RUNE.stop, RUNE.risque,
                            RUNE.capital, RUNE.volume);
    expect(mise).toBeCloseTo(550.53, 1);
    // Sans le volume, l'ancienne deduction depasse le capital entier.
    const deduite = miseReelle(RUNE.entree, RUNE.stop, RUNE.risque,
                               RUNE.capital, null);
    expect(deduite).toBeGreaterThan(RUNE.capital);
  });

  it("calcule le gain sur le volume, pas sur la distance au stop", () => {
    const prixActuel = 0.4993;
    const { eur } = resultatEnDirect(
      RUNE.entree, RUNE.stop, prixActuel, "buy",
      RUNE.risque, RUNE.capital, RUNE.volume);
    // 1104,02 x (0,4993 - 0,49866) = +0,71 EUR
    expect(eur).toBeCloseTo(0.71, 1);
  });

  it("l'ancienne formule gonflait le gain d'un facteur 6", () => {
    const prixActuel = 0.4993;
    const sansVolume = resultatEnDirect(
      RUNE.entree, RUNE.stop, prixActuel, "buy",
      RUNE.risque, RUNE.capital, null).eur;
    const avecVolume = resultatEnDirect(
      RUNE.entree, RUNE.stop, prixActuel, "buy",
      RUNE.risque, RUNE.capital, RUNE.volume).eur;
    expect(sansVolume / avecVolume).toBeGreaterThan(5);
  });

  it("sans volume publie, la deduction reste utilisee", () => {
    // Une position a UN seul etage : les deux calculs concordent, et le
    // repli doit continuer de fonctionner pour les vieilles lignes.
    const { eur } = resultatEnDirect(100, 90, 105, "buy", 0.6, 1000, null);
    expect(eur).toBeCloseTo(3.0, 1);
  });
});

describe("l'historique reel fusionne (11 oct.)", () => {
  const { fusionnerHistorique } = require("./format");
  const ligne = (reference: string, pair: string, closed_at: string, profit_eur: number | null, volume = 10) =>
    ({ id: reference, reference, pair, closed_at, profit_eur, volume });

  it("un trade present dans signals ET le journal n'apparait qu'une fois", () => {
    const signaux = [ligne("ZKUSD~1791562517:1", "ZK/EUR", "2026-10-10T07:48:41Z", -2.79)];
    const journal = [ligne("ZKUSD", "ZK/EUR", "2026-10-10T07:48:41Z", -2.787441)];
    const h = fusionnerHistorique(signaux, journal);
    expect(h).toHaveLength(1);
    expect(h[0].profit_eur).toBeCloseTo(-2.79, 2);
  });

  it("l'etage 2 a zero n'efface plus le gain de l'etage 1", () => {
    const t = "2026-10-11T03:39:38Z";
    const signaux = [ligne("DOSUSD:1", "DOS/EUR", t, 2.92, 100), ligne("DOSUSD:2", "DOS/EUR", t, 0, 50)];
    const h = fusionnerHistorique(signaux, [ligne("DOSUSD", "DOS/EUR", t, 2.917979, 150)]);
    expect(h).toHaveLength(1);
    expect(h[0].profit_eur).toBeCloseTo(2.92, 2);
    expect(h[0].volume).toBe(150);
  });

  it("le journal comble une cloture absente de signals", () => {
    const h = fusionnerHistorique([], [ligne("SANDUSD", "SAND/EUR", "2026-10-02T12:04:47Z", 0.13)]);
    expect(h).toHaveLength(1);
  });

  it("deux trades du meme symbole a des heures differentes restent deux lignes", () => {
    const signaux = [ligne("KAIAUSD:1", "KAIA/EUR", "2026-10-01T12:45:22Z", -1.21),
                     ligne("KAIAUSD:1", "KAIA/EUR", "2026-10-01T17:55:34Z", 2.01)];
    expect(fusionnerHistorique(signaux, [])).toHaveLength(2);
  });
});
