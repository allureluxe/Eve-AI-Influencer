/**
 * Le client voit son portrait et décide, depuis le lien secret reçu par e-mail
 * (alluxe.fr/noel/apercu.html?j=JETON). Rien n'est imprimé sans « valider ».
 *   GET  ?j=JETON                              -> état + portrait (lien signé 1 h)
 *   POST {j, action: "valider"}                -> validee (l'automate commande l'impression)
 *   POST {j, action: "retoucher", note: "..."} -> a_retoucher (3 retouches au plus)
 */
import { createClient } from "jsr:@supabase/supabase-js@2";
import { originePermise } from "../alluxe-site-assistant/logique.ts";

export const MAX_RETOUCHES = 3;

function reponse(corps: unknown, statut: number, origine: string | null): Response {
  const e: Record<string, string> = { "content-type": "application/json" };
  if (origine) Object.assign(e, { "access-control-allow-origin": origine, "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type", vary: "origin" });
  return new Response(statut === 204 ? null : JSON.stringify(corps), { status: statut, headers: e });
}

Deno.serve(async (requete) => {
  const origine = originePermise(requete.headers.get("origin"));
  if (requete.method === "OPTIONS") return reponse({}, origine ? 204 : 403, origine);
  if (!origine) return reponse({ erreur: "origine refusée" }, 403, null);
  const base = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } });

  let corps: Record<string, unknown> = {};
  if (requete.method === "POST") { try { corps = await requete.json(); } catch { /* vide */ } }
  const jeton = String(new URL(requete.url).searchParams.get("j") ?? corps.j ?? "");
  if (!/^[a-f0-9]{64}$/.test(jeton)) return reponse({ erreur: "Lien invalide." }, 404, origine);
  const { data: c } = await base.from("boutique_commandes")
    .select("id, statut, prenom, produit, portrait_path, retouches, suivi_url, journal").eq("jeton", jeton).maybeSingle();
  if (!c) return reponse({ erreur: "Lien invalide." }, 404, origine);

  if (requete.method === "GET") {
    let portrait: string | null = null;
    if (c.portrait_path) {
      const { data } = await base.storage.from("boutique").createSignedUrl(c.portrait_path, 3600);
      portrait = data?.signedUrl ?? null;
    }
    return reponse({ statut: c.statut, prenom: c.prenom, produit: c.produit, portrait,
      retouches_restantes: MAX_RETOUCHES - c.retouches, suivi: c.suivi_url }, 200, origine);
  }
  if (requete.method !== "POST") return reponse({ erreur: "GET ou POST" }, 405, origine);
  if (c.statut !== "portrait_pret") return reponse({ erreur: "Cette commande n'attend pas de réponse." }, 409, origine);

  const action = String(corps.action ?? "");
  const journal = [...(c.journal ?? []), { quand: new Date().toISOString(), quoi: `client: ${action}` }];
  if (action === "valider") {
    await base.from("boutique_commandes").update({ statut: "validee", journal, maj_le: new Date().toISOString() })
      .eq("id", c.id).eq("statut", "portrait_pret");
    return reponse({ ok: true }, 200, origine);
  }
  if (action === "retoucher") {
    if (c.retouches >= MAX_RETOUCHES) return reponse({ erreur: "Plus de retouche automatique : nous vous écrivons." }, 409, origine);
    const note = String(corps.note ?? "").trim().slice(0, 500);
    if (note.length < 3) return reponse({ erreur: "Dites-nous ce qu'il faut changer." }, 400, origine);
    await base.from("boutique_commandes").update({ statut: "a_retoucher", note_retouche: note, journal,
      maj_le: new Date().toISOString() }).eq("id", c.id).eq("statut", "portrait_pret");
    return reponse({ ok: true }, 200, origine);
  }
  return reponse({ erreur: "Action inconnue." }, 400, origine);
});
