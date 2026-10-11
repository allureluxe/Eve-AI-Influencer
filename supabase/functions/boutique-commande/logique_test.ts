/** Lancer : deno test supabase/functions/boutique-commande/logique_test.ts */
import { assertEquals } from "jsr:@std/assert@1";
import { type Catalogue, corpsStripe, valider } from "./logique.ts";

const cat: Catalogue = { commandes_ouvertes: true, styles: [{ id: "royal" }],
  produits: [{ id: "mug", nom: "Mug", prix: 24.9, actif: true }, { id: "plaid", nom: "Plaid", prix: 64, actif: false }] };
const photo = "data:image/jpeg;base64," + btoa("x".repeat(30_000));
const bon = { produit: "mug", style: "royal", sujet: "Mon chien", prenom: "Léa", email: "Lea@X.fr", cgv: true, photo };

Deno.test("une commande correcte passe, prix pris au catalogue", () => {
  const c = valider({ ...bon, prix: 0.01 }, cat);
  if (typeof c === "string") throw new Error(c);
  assertEquals(c.produit.prix, 24.9);
  assertEquals(c.email, "lea@x.fr");
  assertEquals(corpsStripe(c, "abc", "https://alluxe.fr/noel").get("line_items[0][price_data][unit_amount]"), "2490");
});

Deno.test("les refus", () => {
  assertEquals(valider(bon, { ...cat, commandes_ouvertes: false }), "Les commandes ne sont pas encore ouvertes.");
  assertEquals(valider({ ...bon, produit: "plaid" }, cat), "Choisissez un support.");   // produit masqué
  assertEquals(valider({ ...bon, cgv: false }, cat), "Merci d'accepter les conditions de vente.");
  assertEquals(valider({ ...bon, photo: "data:image/gif;base64,AAAA" }, cat), "Ajoutez une photo (JPEG ou PNG).");
  assertEquals(valider({ ...bon, site_web: "http://spam" }, cat), "spam");
});
