/**
 * Le tri des positions -- demande de l'operateur le 19 sept. : « un mode
 * filtre pour que je puisse mettre toutes les positions en positif, de
 * la plus grosse a la plus petite ».
 *
 * Deux pieges tenus ici : une position sans cotation ne doit pas
 * s'inviter au milieu d'un classement par resultat, et le capital retenu
 * doit etre celui FIGE a l'ouverture -- sinon une position prise a
 * 500 EUR et relue a 3 300 pese 6,6 fois trop lourd dans le tri.
 */
import { Position } from "../services/robot";
import { chiffresDe, trier } from "./positionsTri";

function position(sur: Partial<Position> & { id: string }): Position {
  return {
    reference: `${sur.id}:1`, pair: "BTC/EUR", side: "buy",
    entry_price: 100, stop_loss: 90, take_profit_1: null, take_profit_2: null,
    position_size_pct: 0.6, capital_eur: 1000, volume: 1,
    stop_loss_actuel: null, published_at: "2026-09-19T12:00:00Z",
    status: "active", closed_at: null, result_pct: null, ...sur,
  } as Position;
}

describe("le tri par gain", () => {
  const prixLive = { "A/EUR": 110, "B/EUR": 105, "C/EUR": 95 };
  const positions = [
    position({ id: "b", pair: "B/EUR" }),
    position({ id: "c", pair: "C/EUR" }),
    position({ id: "a", pair: "A/EUR" }),
  ];

  it("met la plus grosse en premier", () => {
    const ordre = trier(positions, "gain", true, 1000, prixLive).map((p) => p.id);
    expect(ordre).toEqual(["a", "b", "c"]);
  });

  it("s'inverse quand on redemande le meme critere", () => {
    const ordre = trier(positions, "gain", false, 1000, prixLive).map((p) => p.id);
    expect(ordre).toEqual(["c", "b", "a"]);
  });

  it("renvoie en bas les positions sans cotation, dans les deux sens", () => {
    const avecInconnue = [...positions, position({ id: "z", pair: "Z/EUR" })];
    for (const descendant of [true, false]) {
      const ordre = trier(avecInconnue, "gain", descendant, 1000, prixLive)
        .map((p) => p.id);
      expect(ordre[ordre.length - 1]).toBe("z");
    }
  });
});

describe("le tri par mise", () => {
  it("classe sur la somme engagee, pas sur le gain", () => {
    // Meme risque en pourcentage, mais un stop deux fois plus proche :
    // la mise est donc deux fois plus grosse.
    const serre = position({ id: "serre", pair: "A/EUR", stop_loss: 95 });
    const large = position({ id: "large", pair: "B/EUR", stop_loss: 90 });
    const ordre = trier([large, serre], "mise", true, 1000,
                        { "A/EUR": 100, "B/EUR": 100 }).map((p) => p.id);
    expect(ordre).toEqual(["serre", "large"]);
  });
});

describe("le capital retenu", () => {
  it("est celui FIGE a l'ouverture, pas le capital courant", () => {
    const ancienne = position({ id: "vieille", pair: "A/EUR", capital_eur: 500 });
    const ch = chiffresDe(ancienne, 3300, 110);
    // 0,6 % de 500 EUR sur une distance au stop de 10 % => 30 EUR mises.
    expect(ch!.mise).toBeCloseTo(30, 6);
  });

  it("retombe sur le capital courant quand la ligne n'en porte pas", () => {
    const sansCapital = position({ id: "x", pair: "A/EUR", capital_eur: null });
    const ch = chiffresDe(sansCapital, 500, 110);
    expect(ch!.mise).toBeCloseTo(30, 6);
  });
});

describe("le tri par nom", () => {
  it("classe par nom lisible, pas par code", () => {
    const btc = position({ id: "btc", pair: "BTC/EUR" });   // Bitcoin
    const ada = position({ id: "ada", pair: "ADA/EUR" });   // Cardano
    const ordre = trier([btc, ada], "nom", false, 1000, {}).map((p) => p.id);
    expect(ordre).toEqual(["btc", "ada"]);   // Bitcoin avant Cardano
  });
});

describe("les étages vus depuis la liste", () => {
  // Retour de l'opérateur le 20 sept. : « Avalanche a plusieurs
  // positions ouvertes mais toutes à l'étage 1 ». Deux achats
  // successifs de la même crypto SONT deux étages, même quand chaque
  // référence dit « 1 » — c'est le cas des positions ouvertes avant
  // que le simulateur ne se mette à fusionner.
  const { etagesAffiches } = require("./positionsTri");

  it("numérote les achats successifs d'une même crypto", () => {
    const a = position({ id: "a", pair: "AVAX/EUR", reference: "x:1",
                         published_at: "2026-09-19T15:33:00Z" });
    const b = position({ id: "b", pair: "AVAX/EUR", reference: "y:1",
                         published_at: "2026-09-19T19:31:00Z" });
    const e = etagesAffiches([b, a]);       // ordre d'arrivée quelconque
    expect(e["a"]).toBe(1);
    expect(e["b"]).toBe(2);
  });

  it("laisse une crypto seule à l'étage 1", () => {
    const seul = position({ id: "s", pair: "BTC/EUR", reference: "z:1" });
    expect(etagesAffiches([seul])["s"]).toBe(1);
  });

  it("garde la référence quand elle en dit PLUS", () => {
    // Sur le vrai courtier, les achats fusionnent en UNE position dont
    // la référence porte le vrai compte d'étages. La liste, elle, n'y
    // voit qu'une ligne.
    const fusionnee = position({ id: "f", pair: "OP/EUR", reference: "w:4" });
    expect(etagesAffiches([fusionnee])["f"]).toBe(4);
  });

  it("ne mélange jamais deux cryptos différentes", () => {
    const a = position({ id: "a", pair: "AVAX/EUR", reference: "x:1",
                         published_at: "2026-09-19T10:00:00Z" });
    const n = position({ id: "n", pair: "NEO/EUR", reference: "y:1",
                         published_at: "2026-09-19T11:00:00Z" });
    const e = etagesAffiches([a, n]);
    expect(e["a"]).toBe(1);
    expect(e["n"]).toBe(1);
  });
});
