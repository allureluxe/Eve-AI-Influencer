/**
 * Boutique de Noël : reçoit la commande (photo + choix), range la photo dans le
 * bucket privé « boutique », crée la ligne, ouvre une session Stripe Checkout
 * (Stripe collecte l'adresse de livraison) et renvoie son adresse.
 * Le paiement est constaté par l'automate du VPS (boutique/automate.py), qui
 * interroge Stripe : pas de webhook à signer.
 * Secrets : STRIPE_SECRET_KEY. Sans lui, la commande est refusée proprement.
 */
import { createClient } from "jsr:@supabase/supabase-js@2";
import { cleVisiteur, originePermise } from "../alluxe-site-assistant/logique.ts";
import { type Catalogue, corpsStripe, valider } from "./logique.ts";

const BASE = Deno.env.get("BOUTIQUE_BASE_URL") ?? "https://alluxe.fr/noel";

function reponse(corps: unknown, statut: number, origine: string | null): Response {
  const e: Record<string, string> = { "content-type": "application/json" };
  if (origine) Object.assign(e, { "access-control-allow-origin": origine, "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type", vary: "origin" });
  return new Response(statut === 204 ? null : JSON.stringify(corps), { status: statut, headers: e });
}

Deno.serve(async (requete) => {
  const origine = originePermise(requete.headers.get("origin"));
  if (requete.method === "OPTIONS") return reponse({}, origine ? 204 : 403, origine);
  if (!origine) return reponse({ erreur: "origine refusée" }, 403, null);
  if (requete.method !== "POST") return reponse({ erreur: "POST" }, 405, origine);
  const stripe = Deno.env.get("STRIPE_SECRET_KEY");
  if (!stripe) return reponse({ erreur: "Les commandes ne sont pas encore ouvertes." }, 503, origine);

  let brut: Record<string, unknown>;
  try { brut = await requete.json(); } catch { return reponse({ erreur: "JSON attendu" }, 400, origine); }
  let cat: Catalogue;
  try { cat = await (await fetch(`${BASE}/catalogue.json`, { cache: "no-store" })).json(); }
  catch { return reponse({ erreur: "Réessayez dans un instant." }, 503, origine); }
  const c = valider(brut, cat);
  if (c === "spam") return reponse({ ok: true }, 200, origine);
  if (typeof c === "string") return reponse({ erreur: c }, 400, origine);

  const base = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } });
  const ip = (requete.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "inconnu";
  const { data: passe } = await base.rpc("alluxe_site_compter",
    { p_cle: "boutique:" + await cleVisiteur(ip, Deno.env.get("ASSISTANT_SEL") ?? "alluxe"), p_max_visiteur: 8, p_max_jour: 400 });
  if (passe === false) return reponse({ erreur: "Trop de tentatives aujourd'hui, réessayez demain." }, 429, origine);

  const id = crypto.randomUUID();
  const jeton = crypto.randomUUID().replaceAll("-", "") + crypto.randomUUID().replaceAll("-", "");
  const photoPath = `photos/${id}.${c.type === "image/png" ? "png" : "jpg"}`;
  const { error: eUp } = await base.storage.from("boutique").upload(photoPath, c.photo, { contentType: c.type });
  if (eUp) { console.error("photo", eUp.message); return reponse({ erreur: "Envoi de la photo impossible, réessayez." }, 503, origine); }

  const r = await fetch("https://api.stripe.com/v1/checkout/sessions", { method: "POST",
    headers: { authorization: `Bearer ${stripe}`, "content-type": "application/x-www-form-urlencoded" },
    body: corpsStripe(c, id, BASE) });
  const session = await r.json();
  if (!r.ok) { console.error("stripe", JSON.stringify(session.error ?? session)); return reponse({ erreur: "Paiement indisponible, réessayez." }, 503, origine); }

  const { error } = await base.from("boutique_commandes").insert({ id, produit: c.produit.id, style: c.style, sujet: c.sujet,
    prenom: c.prenom, email: c.email, montant_eur: c.produit.prix, photo_path: photoPath, jeton, stripe_session_id: session.id });
  if (error) { console.error("insertion", error.message); return reponse({ erreur: "Réessayez dans un instant." }, 503, origine); }
  return reponse({ ok: true, paiement: session.url }, 200, origine);
});
