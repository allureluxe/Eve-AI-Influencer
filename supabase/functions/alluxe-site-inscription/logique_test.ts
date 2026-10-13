import { assertEquals } from "jsr:@std/assert";
import { valider } from "./logique.ts";

Deno.test("une inscription correcte est nettoyée", () => {
  assertEquals(valider({ email: " Marie@Exemple.FR ", interet: "noel", page: "/noel/", consentement: true }),
    { email: "marie@exemple.fr", interet: "noel", page: "/noel/" });
});
Deno.test("sans consentement, refus", () => {
  assertEquals(typeof valider({ email: "a@b.fr", consentement: false }), "string");
});
Deno.test("e-mail invalide, refus", () => {
  assertEquals(valider({ email: "pas-un-mail", consentement: true }), "Adresse e-mail invalide.");
});
Deno.test("le champ piège signale un robot", () => {
  assertEquals(valider({ email: "a@b.fr", consentement: true, site_web: "http://spam" }), "spam");
});
Deno.test("un intérêt inconnu devient « tout »", () => {
  assertEquals((valider({ email: "a@b.fr", consentement: true, interet: "x" }) as { interet: string }).interet, "tout");
});
