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
import { chiffresDe, gainTotalEnDirect, trier } from "./positionsTri";
import { regrouperLesEtages } from "../services/format";

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
  // CES TROIS TESTS ONT ETE REECRITS LE 21 SEPTEMBRE.
  //
  // Ils verifiaient la mise DEDUITE de la distance au stop. Depuis que
  // le robot publie le volume, la mise se LIT (`miseReelle`) au lieu de
  // se deduire -- parce que la deduction explose sur une pyramide
  // fusionnee : RUNE affichait 3 732 EUR engages pour 550 reels, sur un
  // compte de 3 300. L'assertion etait donc fausse, pas le code.
  //
  // Leur intention est conservee : le tri classe bien sur la somme
  // engagee, et le capital fige a l'ouverture sert toujours -- mais
  // seulement la ou il compte encore, c'est-a-dire sans volume publie.
  it("classe sur la somme engagee, pas sur le gain", () => {
    const grosse = position({ id: "grosse", pair: "A/EUR", volume: 10 });
    const petite = position({ id: "petite", pair: "B/EUR", volume: 1 });
    const ordre = trier([petite, grosse], "mise", true, 1000,
                        { "A/EUR": 100, "B/EUR": 100 }).map((p) => p.id);
    expect(ordre).toEqual(["grosse", "petite"]);
  });

  it("lit le volume plutot que de deduire la mise", () => {
    const ch = chiffresDe(position({ id: "v", pair: "A/EUR", volume: 3 }),
                          1000, 110);
    expect(ch!.mise).toBeCloseTo(300, 6);      // 3 x 100 EUR d'achat
  });
});

describe("le capital retenu, quand il compte encore", () => {
  // Sans volume publie (vieilles lignes), la mise se deduit du risque :
  // c'est la que le capital d'ouverture fait la difference.
  it("est celui FIGE a l'ouverture, pas le capital courant", () => {
    const ancienne = position({ id: "vieille", pair: "A/EUR",
                                capital_eur: 500, volume: null });
    const ch = chiffresDe(ancienne, 3300, 110);
    // 0,6 % de 500 EUR sur une distance au stop de 10 % => 30 EUR mises.
    expect(ch!.mise).toBeCloseTo(30, 6);
  });

  it("retombe sur le capital courant quand la ligne n'en porte pas", () => {
    const sansCapital = position({ id: "x", pair: "A/EUR",
                                   capital_eur: null, volume: null });
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

describe("le total des positions en cours", () => {
  const { gainTotalEnDirect } = require("./positionsTri");

  // CE TEST EXISTE A CAUSE DU 21 SEPTEMBRE. Les LIGNES affichaient les
  // bons chiffres pendant que le TOTAL annoncait 154,45 EUR pour 54,80
  // reels : l'ecran refaisait le calcul a la main, sans le volume.
  // Quatrieme fois que cette division se retournait.
  it("additionne les gains calcules sur le VOLUME", () => {
    const a = position({ id: "a", pair: "A/EUR", entry_price: 100, volume: 2 });
    const b = position({ id: "b", pair: "B/EUR", entry_price: 100, volume: 3 });
    const total = gainTotalEnDirect([a, b], 1000,
                                    { "A/EUR": 110, "B/EUR": 90 });
    // 2 x (+10) + 3 x (-10) = -10 EUR
    expect(total).toBeCloseTo(-10, 6);
  });

  it("ignore les positions dont la cotation manque", () => {
    const connue = position({ id: "a", pair: "A/EUR", volume: 2 });
    const inconnue = position({ id: "z", pair: "Z/EUR", volume: 99 });
    expect(gainTotalEnDirect([connue, inconnue], 1000, { "A/EUR": 110 }))
      .toBeCloseTo(20, 6);
  });

  it("vaut la somme exacte des lignes affichees", () => {
    // L'invariant qui manquait : le total et les lignes passent par le
    // MEME chemin, donc ils ne peuvent plus diverger.
    const ps = [
      position({ id: "a", pair: "A/EUR", entry_price: 100, volume: 2 }),
      position({ id: "b", pair: "B/EUR", entry_price: 100, volume: 3 }),
    ];
    const prix = { "A/EUR": 110, "B/EUR": 90 };
    const sommeDesLignes = ps.reduce(
      (s, p) => s + (chiffresDe(p, 1000, prix[p.pair as keyof typeof prix])?.eur ?? 0), 0);
    expect(gainTotalEnDirect(ps, 1000, prix)).toBeCloseTo(sommeDesLignes, 9);
  });
});

describe("le capital restant a investir", () => {
  const { resteAInvestir } = require("./positionsTri");

  it("retranche du capital les sommes deja engagees", () => {
    const ps = [
      position({ id: "a", pair: "A/EUR", entry_price: 100, volume: 2 }),
      position({ id: "b", pair: "B/EUR", entry_price: 100, volume: 3 }),
    ];
    // 200 + 300 engages sur 1000 => 500 disponibles
    expect(resteAInvestir(ps, 1000, { "A/EUR": 110, "B/EUR": 90 }))
      .toBeCloseTo(500, 6);
  });

  it("ne descend jamais sous zero", () => {
    const grosse = position({ id: "a", pair: "A/EUR",
                              entry_price: 100, volume: 50 });
    expect(resteAInvestir([grosse], 1000, { "A/EUR": 100 })).toBe(0);
  });

  it("vaut le capital entier quand rien n'est ouvert", () => {
    expect(resteAInvestir([], 3300, {})).toBeCloseTo(3300, 6);
  });
});

/**
 * Une pyramide est UNE position, pas une ligne par étage.
 *
 * La règle vit dans `format.ts` et s'applique aux QUATRE requêtes
 * (positions ouvertes et historique, réel et démo). Ces tests
 * gardent les chiffres relevés en production le 22 septembre.
 *
 * Les chiffres ci-dessous sont ceux relevés en production le
 * 22 septembre 2026 sur le BTC de la démo 1 : quatre étages publiés,
 * chacun portant le volume CUMULÉ après fusion. Les additionner donnait
 * 0,02873360 BTC pour 0,01380458 réellement détenu — la position
 * comptée deux fois, et 51 € de gain latent en trop sur le compte.
 */
describe("le regroupement des étages d'une pyramide", () => {
  const btc = [
    position({ id: "p1", reference: "2e9ab4875955:1",
               entry_price: 70599.65, volume: 0.00079782 }),
    position({ id: "p2", reference: "2e9ab4875955:2",
               entry_price: 72572.26, volume: 0.00682272 }),
    position({ id: "p3", reference: "2e9ab4875955:3",
               entry_price: 72646.98, volume: 0.00730848 }),
    position({ id: "p4", reference: "2e9ab4875955:4",
               entry_price: 73537.85, volume: 0.01380458 }),
  ];

  it("ne garde qu'une ligne, celle du dernier étage", () => {
    const f = regrouperLesEtages(btc);
    expect(f).toHaveLength(1);
    expect(f[0].volume).toBeCloseTo(0.01380458, 8);
    expect(f[0].entry_price).toBeCloseTo(73537.85, 2);
  });

  it("le total cesse de compter la position plusieurs fois", () => {
    const prixLive = { "BTC/EUR": 75000 };
    const avant = gainTotalEnDirect(btc, 3300, prixLive);
    const apres = gainTotalEnDirect(regrouperLesEtages(btc), 3300, prixLive);
    // Ce que le robot détient vraiment, au prix du marché.
    const vrai = 0.01380458 * (75000 - 73537.85);
    expect(apres).toBeCloseTo(vrai, 2);
    expect(avant).toBeGreaterThan(apres * 1.9);
  });

  it("laisse tranquilles les positions sans étage", () => {
    const simples = [
      position({ id: "a", reference: "aaa:1", pair: "A/EUR" }),
      position({ id: "b", reference: "bbb:1", pair: "B/EUR" }),
    ];
    expect(regrouperLesEtages(simples)).toHaveLength(2);
  });

  it("garde l'ordre d'arrivée, pour que la liste ne saute pas", () => {
    const melange = [
      position({ id: "x", reference: "xxx:1", pair: "X/EUR" }),
      ...btc,
      position({ id: "z", reference: "zzz:1", pair: "Z/EUR" }),
    ];
    expect(regrouperLesEtages(melange).map((p) => p.pair))
      .toEqual(["X/EUR", "BTC/EUR", "Z/EUR"]);
  });
});
