/**
 * Ce que le webhook alluxe.ia sait faire, sans reseau : verifier la
 * signature de Meta et extraire les evenements utiles.
 *
 * Separe de index.ts pour etre teste (logique_test.ts).
 */

export interface Evenement {
  ident: string;
  type: "commentaire" | "message";
  ig_user_id: string;
  username: string | null;
  texte: string | null;
  media_id: string | null;
}

/** Comparaison en temps constant : ne pas reveler ou la signature differe. */
function egaux(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

/**
 * Meta signe chaque envoi : `X-Hub-Signature-256: sha256=<hex>`, HMAC du
 * corps BRUT avec le secret de l'application. Sans secret configure, on
 * refuse tout : un webhook qui ne peut pas verifier ne doit rien croire
 * (n'importe qui pourrait sinon faire envoyer des messages au compte).
 *
 * `secrets` peut en porter plusieurs, separes par des virgules : une app
 * Meta a son secret « Meta » ET un secret « Instagram » distinct, et la
 * documentation ne dit pas clairement lequel signe les webhooks de la
 * connexion Instagram. Les deux sont acceptes ; un tiers n'a ni l'un ni
 * l'autre.
 */
export async function signatureValide(
  corpsBrut: string,
  entete: string | null,
  secrets: string | undefined,
): Promise<boolean> {
  if (!secrets || !entete || !entete.startsWith("sha256=")) return false;
  const recu = entete.slice("sha256=".length);
  for (const secret of secrets.split(",").map((x) => x.trim()).filter(Boolean)) {
    const cle = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
    );
    const sig = await crypto.subtle.sign("HMAC", cle, new TextEncoder().encode(corpsBrut));
    const hex = [...new Uint8Array(sig)].map((o) => o.toString(16).padStart(2, "0")).join("");
    if (egaux(hex, recu)) return true;
  }
  return false;
}

/**
 * Les commentaires et messages ENTRANTS. Ignore ce que le compte ecrit
 * lui-meme (ses reponses publiques reviennent en commentaires, ses
 * messages reviennent en « echo ») : sinon le robot se repondrait.
 */
// deno-lint-ignore no-explicit-any
export function extraire(payload: any): Evenement[] {
  const sortie: Evenement[] = [];
  if (!payload || payload.object !== "instagram") return sortie;
  for (const entree of payload.entry ?? []) {
    const compte = String(entree.id ?? "");
    for (const ch of entree.changes ?? []) {
      if (ch.field !== "comments") continue;
      const v = ch.value ?? {};
      const auteur = String(v.from?.id ?? "");
      if (!v.id || !auteur || auteur === compte) continue;
      sortie.push({
        ident: String(v.id), type: "commentaire", ig_user_id: auteur,
        username: v.from?.username ?? null, texte: v.text ?? null,
        media_id: v.media?.id ?? null,
      });
    }
    for (const m of entree.messaging ?? []) {
      const msg = m.message;
      const auteur = String(m.sender?.id ?? "");
      if (!msg || msg.is_echo || !msg.mid || !auteur || auteur === compte) continue;
      sortie.push({
        ident: String(msg.mid), type: "message", ig_user_id: auteur,
        username: null, texte: msg.quick_reply?.payload ?? msg.text ?? null,
        media_id: null,
      });
    }
  }
  return sortie;
}
