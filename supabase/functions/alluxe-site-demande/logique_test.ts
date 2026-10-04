/** Lancer : deno test supabase/functions/alluxe-site-demande/logique_test.ts */
import { assertEquals } from "jsr:@std/assert@1";
import { valider } from "./logique.ts";

const bon = { offre: "shopify", formule: "unique", nom: "Léa", email: "Lea@Exemple.fr", consentement: true };

Deno.test("une commande correcte passe, nettoyée", () => {
  const d = valider({ ...bon, telephone: "06 12 34 56 78<script>" });
  if (typeof d === "string") throw new Error(d);
  assertEquals(d.email, "lea@exemple.fr");
  assertEquals(d.telephone, "06 12 34 56 78");
});

Deno.test("les refus", () => {
  assertEquals(valider({ ...bon, consentement: false }), "Merci d'accepter d'être recontacté.");
  assertEquals(valider({ ...bon, offre: "robot-de-trading" }), "Choisis une offre.");
  assertEquals(valider({ ...bon, email: "pas-un-mail" }), "Adresse e-mail invalide.");
  assertEquals(valider({ ...bon, site_web: "http://spam" }), "spam");
});
