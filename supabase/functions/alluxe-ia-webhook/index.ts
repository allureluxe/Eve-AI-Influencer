/**
 * Le webhook Instagram de @alluxe.ia : il RECOIT, il ne repond pas.
 *
 * Instagram appelle cette adresse a chaque commentaire et a chaque
 * message prive. La fonction verifie que l'envoi vient bien de Meta,
 * garde les evenements entrants dans `alluxe_ia_evenements`, et rend
 * 200 tout de suite (Meta coupe l'abonnement d'un webhook trop lent).
 *
 * C'est le VPS qui repond (`ops/alluxe_ia_kit.py traiter`, toutes les
 * 30 secondes), avec le jeton Instagram de son .env. Ici, seulement
 * deux secrets qui n'expirent jamais :
 *   IG_WEBHOOK_VERIFY_TOKEN  mot choisi par l'operateur, recopie dans Meta
 *   IG_APP_SECRET            secret(s) de l'application, separes par des
 *                            virgules (secret Meta et/ou secret Instagram)
 *
 * Deployee SANS verification JWT : Meta n'envoie pas de jeton Supabase.
 * La signature HMAC la remplace.
 */

import { createClient } from "jsr:@supabase/supabase-js@2";
import { extraire, signatureValide } from "./logique.ts";

Deno.serve(async (requete) => {
  const url = new URL(requete.url);

  // Verification de l'abonnement, une seule fois, quand on colle
  // l'adresse dans le tableau de bord Meta.
  if (requete.method === "GET") {
    const attendu = Deno.env.get("IG_WEBHOOK_VERIFY_TOKEN");
    if (
      attendu &&
      url.searchParams.get("hub.mode") === "subscribe" &&
      url.searchParams.get("hub.verify_token") === attendu
    ) {
      return new Response(url.searchParams.get("hub.challenge") ?? "", { status: 200 });
    }
    return new Response("refuse", { status: 403 });
  }
  if (requete.method !== "POST") return new Response("POST", { status: 405 });

  const brut = await requete.text();
  const ok = await signatureValide(
    brut, requete.headers.get("x-hub-signature-256"), Deno.env.get("IG_APP_SECRET"),
  );
  if (!ok) return new Response("signature invalide", { status: 401 });

  let payload: unknown;
  try {
    payload = JSON.parse(brut);
  } catch {
    return new Response("JSON attendu", { status: 400 });
  }

  const evenements = extraire(payload);
  if (evenements.length) {
    // Autonome (pas de ../_partage) : la fonction se deploie seule.
    const base = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
      { auth: { persistSession: false } },
    );
    const { error } = await base
      .from("alluxe_ia_evenements")
      .upsert(evenements, { onConflict: "ident", ignoreDuplicates: true });
    // On rend 200 quand meme : Meta renverrait en boucle, et l'unicite
    // d'`ident` absorbe les doublons. L'erreur part dans les journaux.
    if (error) console.error("depot impossible :", error.message);
  }
  return new Response("ok", { status: 200 });
});
