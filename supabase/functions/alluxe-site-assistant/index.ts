/**
 * L'assistant de la page publique alluxe.fr (bulle en bas a droite).
 *
 * Le navigateur du visiteur envoie l'historique de la discussion ; la
 * fonction compte le message (plafond par visiteur et par jour), appelle
 * Groq avec la cle cachee ici, et rend la reponse. Rien n'est garde.
 *
 * Secrets : GROQ_API_KEY (meme cle que l'agent), ASSISTANT_SEL (sel du
 * hachage des IP). Modeles : ASSISTANT_MODELES, du premier au repli.
 * qwen d'abord : son quota Groq n'est pas celui de l'agent (gpt-oss-120b),
 * et, mesure le 4 oct., il dit « je ne sais pas » la ou gpt-oss-20b
 * inventait un prix au kit.
 *
 * Deployee SANS verification JWT : la page publique n'a pas de session.
 * Protections : CORS limite a alluxe.fr, plafonds, consigne stricte.
 */

import { createClient } from "jsr:@supabase/supabase-js@2";
import {
  consigne, cleVisiteur, type Offre, MAX_MESSAGES_PAR_JOUR, MAX_MESSAGES_PAR_VISITEUR,
  nettoyerHistorique, nettoyerReponse, originePermise,
} from "./logique.ts";

const MODELES = (Deno.env.get("ASSISTANT_MODELES") ?? "qwen/qwen3.8-27b,openai/gpt-oss-20b")
  .split(",").map((m) => m.trim()).filter(Boolean);

function reponse(corps: unknown, statut: number, origine: string | null): Response {
  const entetes: Record<string, string> = { "content-type": "application/json" };
  if (origine) {
    entetes["access-control-allow-origin"] = origine;
    entetes["access-control-allow-methods"] = "POST, OPTIONS";
    entetes["access-control-allow-headers"] = "content-type";
    entetes["vary"] = "origin";
  }
  // Un 204 ne peut pas porter de corps : Deno leve une erreur (500), et le
  // navigateur refusait alors TOUT envoi (pre-verification CORS echouee).
  const contenu = statut === 204 ? null : JSON.stringify(corps);
  return new Response(contenu, { status: statut, headers: entetes });
}

// Les prix viennent du site lui-même (offres.json), relus toutes les 10 minutes.
let cacheOffres: { quand: number; offres: Offre[] | null } = { quand: 0, offres: null };
async function offresDuSite(): Promise<Offre[] | null> {
  if (Date.now() - cacheOffres.quand < 10 * 60_000 && cacheOffres.offres) return cacheOffres.offres;
  try {
    const r = await fetch("https://alluxe.fr/offres.json", { signal: AbortSignal.timeout(4000) });
    const d = await r.json();
    cacheOffres = { quand: Date.now(), offres: Array.isArray(d?.offres) ? d.offres : null };
  } catch (e) {
    console.error("offres.json :", (e as Error).message);
  }
  return cacheOffres.offres;
}

async function appelerGroq(messages: unknown[]): Promise<string> {
  const cle = Deno.env.get("GROQ_API_KEY");
  if (!cle) throw new Error("GROQ_API_KEY absent");
  let derniere = "";
  for (const modele of MODELES) {
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${cle}` },
      body: JSON.stringify({ model: modele, messages, max_tokens: 400, temperature: 0.3 }),
    });
    if (r.ok) {
      const d = await r.json();
      const texte = nettoyerReponse(String(d?.choices?.[0]?.message?.content ?? ""));
      if (texte) return texte;
      derniere = `${modele} : reponse vide`;
    } else {
      derniere = `${modele} : ${r.status}`;
    }
    console.error("groq", derniere);
  }
  throw new Error(derniere);
}

Deno.serve(async (requete) => {
  const origine = originePermise(requete.headers.get("origin"));
  if (requete.method === "OPTIONS") return reponse({}, origine ? 204 : 403, origine);
  if (!origine) return reponse({ erreur: "origine refusee" }, 403, null);
  if (requete.method !== "POST") return reponse({ erreur: "POST" }, 405, origine);

  let corps: Record<string, unknown>;
  try {
    corps = await requete.json();
  } catch {
    return reponse({ erreur: "JSON attendu" }, 400, origine);
  }
  const historique = nettoyerHistorique(corps?.messages);
  if (!historique) return reponse({ erreur: "message vide" }, 400, origine);

  const ip = (requete.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "inconnu";
  const cle = await cleVisiteur(ip, Deno.env.get("ASSISTANT_SEL") ?? "alluxe");
  const base = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );
  const { data: passe, error } = await base.rpc("alluxe_site_compter", {
    p_cle: cle, p_max_visiteur: MAX_MESSAGES_PAR_VISITEUR, p_max_jour: MAX_MESSAGES_PAR_JOUR,
  });
  if (error) {
    console.error("quota :", error.message);
    return reponse({ erreur: "indisponible" }, 503, origine);
  }
  if (!passe) {
    return reponse({
      reponse: "J'ai atteint ma limite de messages pour aujourd'hui. Reviens demain, " +
        "ou retrouve-moi sur Instagram : @alluxe.ia.",
    }, 200, origine);
  }

  try {
    const texte = await appelerGroq([{ role: "system", content: consigne(await offresDuSite()) }, ...historique]);
    return reponse({ reponse: texte }, 200, origine);
  } catch (e) {
    console.error("assistant :", (e as Error).message);
    return reponse({
      reponse: "Trop de demandes en ce moment, réessaie dans une minute.",
    }, 200, origine);
  }
});
