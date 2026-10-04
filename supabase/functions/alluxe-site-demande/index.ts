/**
 * Reçoit les commandes du formulaire d'alluxe.fr (commander.html) et les
 * range dans `alluxe_site_demandes`. Aucun paiement ici : l'opérateur n'a
 * pas encore de SIRET (4 oct.) ; il rappelle le client et envoie le lien.
 *
 * Sans vérification JWT (page publique). Protections : CORS alluxe.fr,
 * champ piège anti-robot, plafonds par visiteur et par jour (compteur
 * partagé avec l'assistant, clé préfixée « demande: »), IP hachée.
 */
import { createClient } from "jsr:@supabase/supabase-js@2";
import { cleVisiteur, originePermise } from "../alluxe-site-assistant/logique.ts";
import { MAX_PAR_JOUR, MAX_PAR_VISITEUR, valider } from "./logique.ts";

function reponse(corps: unknown, statut: number, origine: string | null): Response {
  const e: Record<string, string> = { "content-type": "application/json" };
  if (origine) {
    e["access-control-allow-origin"] = origine;
    e["access-control-allow-methods"] = "POST, OPTIONS";
    e["access-control-allow-headers"] = "content-type";
    e["vary"] = "origin";
  }
  return new Response(statut === 204 ? null : JSON.stringify(corps), { status: statut, headers: e });
}

Deno.serve(async (requete) => {
  const origine = originePermise(requete.headers.get("origin"));
  if (requete.method === "OPTIONS") return reponse({}, origine ? 204 : 403, origine);
  if (!origine) return reponse({ erreur: "origine refusée" }, 403, null);
  if (requete.method !== "POST") return reponse({ erreur: "POST" }, 405, origine);
  let brut: Record<string, unknown>;
  try { brut = await requete.json(); } catch { return reponse({ erreur: "JSON attendu" }, 400, origine); }

  const d = valider(brut);
  if (d === "spam") return reponse({ ok: true }, 200, origine);     // on ne dit rien au robot
  if (typeof d === "string") return reponse({ erreur: d }, 400, origine);

  const base = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } });
  const ip = (requete.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "inconnu";
  const cle = "demande:" + await cleVisiteur(ip, Deno.env.get("ASSISTANT_SEL") ?? "alluxe");
  const { data: passe, error: eq } = await base.rpc("alluxe_site_compter",
    { p_cle: cle, p_max_visiteur: MAX_PAR_VISITEUR, p_max_jour: MAX_PAR_JOUR });
  if (eq) { console.error("quota", eq.message); return reponse({ erreur: "Réessaie dans un instant." }, 503, origine); }
  if (!passe) return reponse({ erreur: "Trop de demandes aujourd'hui, réessaie demain ou écris sur Instagram." }, 429, origine);

  const { error } = await base.from("alluxe_site_demandes").insert(d);
  if (error) { console.error("insertion", error.message); return reponse({ erreur: "Réessaie dans un instant." }, 503, origine); }
  return reponse({ ok: true }, 200, origine);
});
