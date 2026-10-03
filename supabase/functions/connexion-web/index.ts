/**
 * POST /connexion-web — ouvre la session de la version web d'Alluxe Bot.
 *
 * Decision de l'operateur, 3 oct. 2026.
 *
 * L'APK se connecte avec le mot de passe du compte de service, embarque
 * dans le binaire. Une page web publique ne peut pas : son code se lit
 * dans n'importe quel navigateur. La page envoie donc seulement la
 * reponse de l'ecran « annee ». Le serveur la compare (meme secret que
 * `verifier_identite`, jamais renvoye) et rend un jeton a usage unique,
 * que la page echange contre une session (`verifyOtp`).
 *
 * Cette reponse est la seule porte d'une adresse publique : les echecs
 * sont plafonnes, comptes en base (`connexion_web_essais`).
 */

// Autonome (pas d'import de _partage) : deployee seule, elle ne doit
// dependre que de ce fichier.
import { createClient } from "jsr:@supabase/supabase-js@2";

const ENTETES_CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function reponse(corps: unknown, statut = 200): Response {
  return new Response(JSON.stringify(corps), {
    status: statut,
    headers: { ...ENTETES_CORS, "Content-Type": "application/json" },
  });
}

function erreur(message: string, statut = 400): Response {
  return reponse({ error: message }, statut);
}

function clientService() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );
}

const EMAIL_SERVICE = Deno.env.get("ALLUXE_BOT_SERVICE_EMAIL") ?? "alluxe-bot@service.interne";
const ECHECS_MAX = 5;
const FENETRE_MS = 15 * 60 * 1000;

Deno.serve(async (requete) => {
  if (requete.method === "OPTIONS") return new Response("ok", { headers: ENTETES_CORS });
  if (requete.method !== "POST") return erreur("methode non permise", 405);

  const service = clientService();
  try {
    const depuis = new Date(Date.now() - FENETRE_MS).toISOString();
    const { count, error: errCompte } = await service
      .from("connexion_web_essais")
      .select("id", { count: "exact", head: true })
      .eq("reussi", false).gte("a", depuis);
    // Le plafond echoue ferme : sans compteur lisible, pas d'essai.
    if (errCompte) throw errCompte;
    if ((count ?? 0) >= ECHECS_MAX) {
      return erreur("trop d'essais, reessaie dans un quart d'heure", 429);
    }

    const corps = await requete.json().catch(() => ({}));
    const tentative = typeof corps?.reponse === "string" ? corps.reponse : "";

    const { data: secret, error: errSecret } = await service
      .from("secret_verification").select("valeur").eq("id", "alluxe_bot").maybeSingle();
    if (errSecret) throw errSecret;
    const bonne = !!secret?.valeur && tentative === secret.valeur;

    const { error: errJournal } = await service
      .from("connexion_web_essais").insert({ reussi: bonne });
    if (errJournal) throw errJournal;
    if (!bonne) return erreur("reponse incorrecte", 401);

    const { data, error } = await service.auth.admin.generateLink({
      type: "magiclink", email: EMAIL_SERVICE,
    });
    if (error || !data?.properties?.hashed_token) throw error ?? new Error("jeton absent");
    return reponse({ token_hash: data.properties.hashed_token });
  } catch (e) {
    console.error("connexion-web :", e);
    return erreur("erreur interne", 500);
  }
});
