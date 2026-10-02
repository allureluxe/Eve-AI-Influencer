/**
 * Lancer :  deno test supabase/functions/alluxe-ia-webhook/logique_test.ts
 */
import { assertEquals } from "jsr:@std/assert@1";
import { extraire, signatureValide } from "./logique.ts";

async function signer(corps: string, secret: string): Promise<string> {
  const cle = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const s = await crypto.subtle.sign("HMAC", cle, new TextEncoder().encode(corps));
  return "sha256=" + [...new Uint8Array(s)].map((o) => o.toString(16).padStart(2, "0")).join("");
}

Deno.test("une signature juste passe, une fausse non", async () => {
  const corps = '{"object":"instagram"}';
  assertEquals(await signatureValide(corps, await signer(corps, "s3cret"), "s3cret"), true);
  assertEquals(await signatureValide(corps, await signer(corps, "autre"), "s3cret"), false);
  assertEquals(await signatureValide(corps + " ", await signer(corps, "s3cret"), "s3cret"), false);
});

Deno.test("sans secret configure, tout est refuse", async () => {
  const corps = "{}";
  assertEquals(await signatureValide(corps, await signer(corps, "x"), undefined), false);
  assertEquals(await signatureValide(corps, null, "s3cret"), false);
});

Deno.test("commentaires et messages entrants, jamais ceux du compte", () => {
  const p = {
    object: "instagram",
    entry: [{
      id: "MOI",
      changes: [
        { field: "comments", value: { id: "C1", text: "KIT", from: { id: "U1", username: "lea" }, media: { id: "M1" } } },
        { field: "comments", value: { id: "C2", text: "Envoyé en privé", from: { id: "MOI", username: "alluxe.ia" } } },
        { field: "mentions", value: { id: "X" } },
      ],
      messaging: [
        { sender: { id: "U1" }, recipient: { id: "MOI" }, message: { mid: "m1", text: "je pars de zéro" } },
        { sender: { id: "MOI" }, recipient: { id: "U1" }, message: { mid: "m2", text: "salut", is_echo: true } },
        { sender: { id: "U2" }, recipient: { id: "MOI" }, message: { mid: "m3", text: "x", quick_reply: { payload: "ZERO" } } },
      ],
    }],
  };
  const e = extraire(p);
  assertEquals(e.map((x) => [x.type, x.ident, x.ig_user_id, x.texte]), [
    ["commentaire", "C1", "U1", "KIT"],
    ["message", "m1", "U1", "je pars de zéro"],
    ["message", "m3", "U2", "ZERO"],
  ]);
  assertEquals(e[0].username, "lea");
  assertEquals(e[0].media_id, "M1");
});

Deno.test("un autre objet que instagram est ignore", () => {
  assertEquals(extraire({ object: "page", entry: [] }), []);
  assertEquals(extraire(null), []);
});
