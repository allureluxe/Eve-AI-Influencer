/**
 * Le ton des notifications est une decision, pas un hasard.
 *
 * Ces tests existent pour le jour ou quelqu'un ajoutera un message
 * « pour faire revenir les gens ». Le texte fautif ne partira pas.
 */

import { assertEquals, assertThrows } from "jsr:@std/assert@1";
import {
  nomCourant,
  prixLisible,
  texteCloture,
  texteMacro,
  texteSignal,
  TonRefuse,
  verifierLeTon,
} from "./redaction.ts";

Deno.test("un point d'exclamation est refuse", () => {
  assertThrows(() => verifierLeTon("Nouveau signal !"), TonRefuse);
});

Deno.test("un emoji est refuse", () => {
  assertThrows(() => verifierLeTon("Bitcoin en hausse 🚀"), TonRefuse);
  assertThrows(() => verifierLeTon("Attention ⚠️"), TonRefuse);
});

Deno.test("une promesse de gain est refusee", () => {
  for (const texte of [
    "Un gain garanti sur ce signal",
    "Achete sans risque maintenant",
    "Derniere chance avant la hausse",
    "Il faut acheter tout de suite",
  ]) {
    assertThrows(() => verifierLeTon(texte), TonRefuse, undefined, texte);
  }
});

Deno.test("un texte sobre passe", () => {
  verifierLeTon("Bitcoin, achat a 58 420 EUR");
});

Deno.test("les trois messages de l'application sont conformes", () => {
  // C'est le test qui compte : les textes REELLEMENT envoyes.
  const messages = [
    texteSignal("BTC/EUR", "buy", 58420),
    texteMacro("Inflation americaine", 15),
    texteCloture("BTC/EUR", 4.2),
    texteCloture("SOL/EUR", -1.8),
  ];
  for (const m of messages) {
    verifierLeTon(m.titre);
    verifierLeTon(m.corps);
  }
});

Deno.test("une perte est annoncee comme un gain", () => {
  // NE NOTIFIER QUE LES GAINS donnerait une impression de reussite que
  // l'historique ne porte pas. C'est un mensonge par omission.
  const perte = texteCloture("BTC/EUR", -3.4);
  assertEquals(perte.corps, "Bitcoin : -3,4 %");
  const gain = texteCloture("BTC/EUR", 3.4);
  assertEquals(gain.corps, "Bitcoin : +3,4 %");
  assertEquals(perte.titre, gain.titre, "titres differents selon le resultat");
});

//  Le francais separe les milliers par une ESPACE INSECABLE FINE
//  (U+202F), pas par une espace ordinaire. C'est voulu : un prix ne
//  doit pas se couper en fin de ligne dans une notification. Les
//  attentes ci-dessous utilisent donc le vrai caractere.
const ESP = " ";

Deno.test("le prix s'affiche sans decimales inutiles", () => {
  assertEquals(prixLisible(58420.4), `58${ESP}420 EUR`);
  assertEquals(prixLisible(2.5), "2,50 EUR");
  // Un jeton a 0,000012 EUR affiche « 0 EUR » serait faux.
  assertEquals(prixLisible(0.000012), "0,000012 EUR");
});

Deno.test("le separateur de milliers est insecable", () => {
  // Verrouille l'intention : si un jour la locale change et rend une
  // espace ordinaire ENTRE LES CHIFFRES, le nombre pourra se couper en
  // fin de ligne. L'espace avant « EUR », elle, est normale.
  const nombre = prixLisible(58420).replace(" EUR", "");
  assertEquals(/\d \d/.test(nombre), false, `separable : ${nombre}`);
  assertEquals(nombre, `58${ESP}420`);
});

Deno.test("les cryptos portent leur nom courant", () => {
  assertEquals(nomCourant("BTC/EUR"), "Bitcoin");
  // Repli sur le symbole : mieux que d'inventer un nom.
  assertEquals(nomCourant("PENDLE/EUR"), "PENDLE");
});

Deno.test("le message de signal dit ce qu'il faut et rien de plus", () => {
  const m = texteSignal("BTC/EUR", "buy", 58420);
  assertEquals(m.titre, "Nouveau signal");
  assertEquals(m.corps, `Bitcoin, achat a 58${ESP}420 EUR`);
});
