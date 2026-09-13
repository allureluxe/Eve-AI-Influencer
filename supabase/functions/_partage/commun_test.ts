/**
 * Le filtrage gratuit / payant est la charniere commerciale de l'app.
 *
 * Une erreur ici a deux visages, et les deux coutent :
 *   - trop permissif, l'abonnement ne sert a rien ;
 *   - trop strict, un abonne payant ne voit pas ce qu'il paie.
 *
 * Lancer :  deno test supabase/functions/_partage/commun_test.ts
 */

import { assertEquals } from "jsr:@std/assert@1";
import {
  Capacites,
  CAPACITES_GRATUIT,
  debitDepasse,
  filtrerPourLePalier,
  PAIRES_GRATUITES,
  RETARD_GRATUIT_MS,
  Signal,
} from "./commun.ts";

/**
 * Les capacites telles que la base les declare, reproduites ici.
 *
 * Le filtre ne connait plus les noms de paliers : il lit ces drapeaux.
 * Ajouter une offre demain ne demandera donc aucune modification du
 * filtre — seulement une ligne dans `public.offres`.
 */
const GRATUIT = CAPACITES_GRATUIT;

const ESSENTIEL: Capacites = {
  tier: "essentiel", rang: 1, nom: "Essentiel",
  toutes_paires: true, retard_minutes: 0, positions_direct: false,
  note_du_matin: false, historique_complet: false, export_csv: false,
};

const PLUS: Capacites = {
  tier: "plus", rang: 2, nom: "Plus",
  toutes_paires: true, retard_minutes: 0, positions_direct: true,
  note_du_matin: true, historique_complet: true, export_csv: false,
};

const MAINTENANT = Date.parse("2026-09-13T12:00:00Z");

function signal(pair: string, ilYAMinutes: number): Signal {
  return {
    id: `${pair}-${ilYAMinutes}`,
    published_at: new Date(MAINTENANT - ilYAMinutes * 60_000).toISOString(),
    pair,
    side: "buy",
    entry_price: 100,
    stop_loss: 95,
    take_profit_1: null,
    take_profit_2: null,
    risk_reward: null,
    position_size_pct: 0.6,
    conviction: 70,
    rationale: "explication",
    status: "active",
    closed_at: null,
    result_pct: null,
    macro_flag: false,
  };
}

Deno.test("un abonne voit tout, sans delai", () => {
  const signaux = [signal("BTC/EUR", 1), signal("PENDLE/EUR", 0)];
  assertEquals(filtrerPourLePalier(signaux, PLUS, MAINTENANT).length, 2);
});

Deno.test("un compte gratuit ne voit pas un signal recent", () => {
  // Le coeur de l'abonnement : le temps reel se paie.
  const signaux = [signal("BTC/EUR", 30)];
  assertEquals(filtrerPourLePalier(signaux, GRATUIT, MAINTENANT).length, 0);
});

Deno.test("un compte gratuit voit le meme signal deux heures plus tard", () => {
  const signaux = [signal("BTC/EUR", 121)];
  assertEquals(filtrerPourLePalier(signaux, GRATUIT, MAINTENANT).length, 1);
});

Deno.test("la limite des deux heures est franchie, pas approchee", () => {
  const juste = RETARD_GRATUIT_MS / 60_000;          // 120 minutes
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", juste)], GRATUIT, MAINTENANT).length, 1);
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", juste - 1)], GRATUIT, MAINTENANT).length, 0);
});

Deno.test("un compte gratuit ne voit que BTC, ETH et SOL", () => {
  // Anciennes de trois heures : seule la paire les distingue.
  const signaux = [
    signal("BTC/EUR", 180), signal("ETH/EUR", 180), signal("SOL/EUR", 180),
    signal("PENDLE/EUR", 180), signal("LINK/EUR", 180),
  ];
  const vus = filtrerPourLePalier(signaux, GRATUIT, MAINTENANT).map((s) => s.pair);
  assertEquals(vus.sort(), [...PAIRES_GRATUITES].sort());
});

Deno.test("les deux conditions s'appliquent ensemble, pas au choix", () => {
  // Une paire gratuite MAIS recente : refusee.
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", 10)], GRATUIT, MAINTENANT).length, 0);
  // Une paire payante MAIS ancienne : refusee aussi.
  assertEquals(filtrerPourLePalier([signal("PENDLE/EUR", 500)], GRATUIT, MAINTENANT).length, 0);
});

Deno.test("une date de publication illisible ne passe pas", () => {
  // FAIL-CLOSED. Une date cassee ne doit pas ouvrir la porte : c'est
  // exactement le genre de trou qu'on ne voit qu'apres coup.
  const casse = { ...signal("BTC/EUR", 500), published_at: "pas une date" };
  assertEquals(filtrerPourLePalier([casse], GRATUIT, MAINTENANT).length, 0);
});

Deno.test("le filtrage ne modifie pas la liste d'origine", () => {
  const signaux = [signal("BTC/EUR", 180), signal("PENDLE/EUR", 180)];
  filtrerPourLePalier(signaux, GRATUIT, MAINTENANT);
  assertEquals(signaux.length, 2);
});

Deno.test("la limitation de debit laisse passer puis coupe", () => {
  const cle = `test-${Math.random()}`;
  for (let i = 0; i < 5; i++) {
    assertEquals(debitDepasse(cle, 5), false, `appel ${i + 1}`);
  }
  assertEquals(debitDepasse(cle, 5), true, "6e appel");
});

Deno.test("chaque utilisateur a son propre compteur", () => {
  const a = `a-${Math.random()}`, b = `b-${Math.random()}`;
  for (let i = 0; i < 3; i++) debitDepasse(a, 3);
  assertEquals(debitDepasse(a, 3), true);
  assertEquals(debitDepasse(b, 3), false, "un utilisateur en bloque un autre");
});


Deno.test("un palier intermediaire recoit tout, en temps reel", () => {
  // « Essentiel » n'est ni gratuit ni « plus » : sans un filtre fonde
  // sur les capacites, il serait tombe dans la branche « pas plus »
  // et aurait ete traite comme un compte gratuit — c'est-a-dire qu'il
  // aurait paye le temps reel pour recevoir trois cryptos en differe.
  const signaux = [signal("BTC/EUR", 1), signal("PENDLE/EUR", 0)];
  assertEquals(filtrerPourLePalier(signaux, ESSENTIEL, MAINTENANT).length, 2);
});

Deno.test("le retard vient de la grille, pas d une constante", () => {
  // Une offre a 30 minutes de retard doit fonctionner sans toucher au
  // code du filtre.
  const trenteMin: Capacites = { ...GRATUIT, toutes_paires: true,
                                 retard_minutes: 30 };
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", 29)], trenteMin,
                                   MAINTENANT).length, 0);
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", 31)], trenteMin,
                                   MAINTENANT).length, 1);
});

Deno.test("un retard nul ne regarde meme pas la date", () => {
  // Un signal publie « dans le futur » (horloge decalee cote serveur)
  // ne doit pas disparaitre pour un abonne en temps reel.
  const futur = { ...signal("BTC/EUR", -5) };
  assertEquals(filtrerPourLePalier([futur], PLUS, MAINTENANT).length, 1);
});

Deno.test("le repli en cas de grille injoignable est le plus restrictif", () => {
  // FAIL-CLOSED : un abonne verra momentanement moins que ce qu il
  // paie, ce qui se repare. L inverse distribuerait gratuitement ce
  // que d autres paient, ce qui ne se repare pas.
  assertEquals(CAPACITES_GRATUIT.toutes_paires, false);
  assertEquals(CAPACITES_GRATUIT.retard_minutes, 120);
  assertEquals(CAPACITES_GRATUIT.positions_direct, false);
});
