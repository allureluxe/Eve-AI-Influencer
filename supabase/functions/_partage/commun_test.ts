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
  debitDepasse,
  filtrerPourLePalier,
  PAIRES_GRATUITES,
  RETARD_GRATUIT_MS,
  Signal,
} from "./commun.ts";

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
  assertEquals(filtrerPourLePalier(signaux, "plus", MAINTENANT).length, 2);
});

Deno.test("un compte gratuit ne voit pas un signal recent", () => {
  // Le coeur de l'abonnement : le temps reel se paie.
  const signaux = [signal("BTC/EUR", 30)];
  assertEquals(filtrerPourLePalier(signaux, "free", MAINTENANT).length, 0);
});

Deno.test("un compte gratuit voit le meme signal deux heures plus tard", () => {
  const signaux = [signal("BTC/EUR", 121)];
  assertEquals(filtrerPourLePalier(signaux, "free", MAINTENANT).length, 1);
});

Deno.test("la limite des deux heures est franchie, pas approchee", () => {
  const juste = RETARD_GRATUIT_MS / 60_000;          // 120 minutes
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", juste)], "free", MAINTENANT).length, 1);
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", juste - 1)], "free", MAINTENANT).length, 0);
});

Deno.test("un compte gratuit ne voit que BTC, ETH et SOL", () => {
  // Anciennes de trois heures : seule la paire les distingue.
  const signaux = [
    signal("BTC/EUR", 180), signal("ETH/EUR", 180), signal("SOL/EUR", 180),
    signal("PENDLE/EUR", 180), signal("LINK/EUR", 180),
  ];
  const vus = filtrerPourLePalier(signaux, "free", MAINTENANT).map((s) => s.pair);
  assertEquals(vus.sort(), [...PAIRES_GRATUITES].sort());
});

Deno.test("les deux conditions s'appliquent ensemble, pas au choix", () => {
  // Une paire gratuite MAIS recente : refusee.
  assertEquals(filtrerPourLePalier([signal("BTC/EUR", 10)], "free", MAINTENANT).length, 0);
  // Une paire payante MAIS ancienne : refusee aussi.
  assertEquals(filtrerPourLePalier([signal("PENDLE/EUR", 500)], "free", MAINTENANT).length, 0);
});

Deno.test("une date de publication illisible ne passe pas", () => {
  // FAIL-CLOSED. Une date cassee ne doit pas ouvrir la porte : c'est
  // exactement le genre de trou qu'on ne voit qu'apres coup.
  const casse = { ...signal("BTC/EUR", 500), published_at: "pas une date" };
  assertEquals(filtrerPourLePalier([casse], "free", MAINTENANT).length, 0);
});

Deno.test("le filtrage ne modifie pas la liste d'origine", () => {
  const signaux = [signal("BTC/EUR", 180), signal("PENDLE/EUR", 180)];
  filtrerPourLePalier(signaux, "free", MAINTENANT);
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
