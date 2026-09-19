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
