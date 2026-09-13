/**
 * Ce que toutes les fonctions de l'API partagent.
 *
 * LA REGLE QUI GOUVERNE CE FICHIER
 * --------------------------------
 * Le filtrage gratuit / payant se fait ICI, cote serveur, et nulle part
 * ailleurs. L'application ne recoit JAMAIS un signal auquel
 * l'utilisateur n'a pas droit.
 *
 * Ce n'est pas une precaution theorique. Une application mobile est un
 * fichier que n'importe qui peut ouvrir : masquer un signal en le
 * rendant invisible a l'ecran revient a le publier. Un abonnement dont
 * le contenu voyage quand meme jusqu'au telephone n'est pas un
 * abonnement, c'est une politesse.
 */

import { createClient, SupabaseClient } from "jsr:@supabase/supabase-js@2";

export const ENTETES_CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

/** Delai avant qu'un signal devienne visible pour un compte gratuit. */
export const RETARD_GRATUIT_MS = 2 * 60 * 60 * 1000;

/** Les seules cryptos visibles sans abonnement. */
export const PAIRES_GRATUITES = ["BTC/EUR", "ETH/EUR", "SOL/EUR"];

export type Palier = "free" | "essentiel" | "plus" | "pro";

/**
 * Ce que le palier donne, tel que la base le declare.
 *
 * LE FILTRE NE TESTE JAMAIS LE NOM DU PALIER, il teste ces capacites.
 * Ajouter une offre demain ne demande donc aucune modification ici —
 * une ligne dans `public.offres` suffit. Un `if (palier === "plus")`
 * dissemine dans cinq fichiers est la garantie qu'un jour l'un d'eux
 * sera oublie, et que quelqu'un paiera sans recevoir.
 */
export interface Capacites {
  tier: Palier;
  rang: number;
  nom: string;
  toutes_paires: boolean;
  retard_minutes: number;
  positions_direct: boolean;
  note_du_matin: boolean;
  historique_complet: boolean;
  export_csv: boolean;
}

/** Le repli si la table est injoignable : le palier le plus restrictif. */
export const CAPACITES_GRATUIT: Capacites = {
  tier: "free", rang: 0, nom: "Decouverte",
  toutes_paires: false, retard_minutes: 120, positions_direct: false,
  note_du_matin: false, historique_complet: false, export_csv: false,
};

export interface Visiteur {
  id: string;
  palier: Palier;
  capacites: Capacites;
}

export function reponse(corps: unknown, statut = 200): Response {
  return new Response(JSON.stringify(corps), {
    status: statut,
    headers: { ...ENTETES_CORS, "Content-Type": "application/json" },
  });
}

export function erreur(message: string, statut = 400): Response {
  return reponse({ error: message }, statut);
}

/**
 * Le client de service : il contourne la RLS.
 *
 * Il ne sort jamais de la fonction Edge. C'est lui qui applique le
 * filtrage par palier — et c'est pour cela que le filtrage ne peut pas
 * etre contourne depuis le telephone.
 */
export function clientService(): SupabaseClient {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );
}

/**
 * Qui appelle, et avec quel abonnement.
 *
 * LE PALIER EST LU EN BASE, JAMAIS DANS LA REQUETE. Un champ
 * `tier: "plus"` envoye par l'application serait une declaration de
 * l'application sur elle-meme : exactement ce qu'il ne faut pas croire.
 */
export async function identifier(
  requete: Request,
  service: SupabaseClient,
): Promise<Visiteur | null> {
  const entete = requete.headers.get("Authorization") ?? "";
  const jeton = entete.replace(/^Bearer\s+/i, "").trim();
  if (!jeton) return null;

  const { data: auth, error } = await service.auth.getUser(jeton);
  if (error || !auth?.user) return null;

  const { data: profil } = await service
    .from("profiles")
    .select("tier")
    .eq("id", auth.user.id)
    .single();

  // Profil absent = compte tout juste cree, le declencheur n'a pas
  // encore tourne. On sert le palier gratuit plutot que de refuser :
  // un premier lancement sur un ecran d'erreur perd l'utilisateur.
  const palier = (profil?.tier as Palier) ?? "free";

  const { data: offre } = await service
    .from("offres")
    .select(`tier, rang, nom, toutes_paires, retard_minutes,
             positions_direct, note_du_matin, historique_complet, export_csv`)
    .eq("tier", palier)
    .single();

  // FAIL-CLOSED. Si la grille est injoignable, on sert le palier le
  // plus restrictif : un abonne verra momentanement moins que ce qu'il
  // paie, ce qui se repare ; l'inverse distribuerait gratuitement ce
  // que d'autres paient, ce qui ne se repare pas.
  return {
    id: auth.user.id,
    palier,
    capacites: (offre as Capacites | null) ?? CAPACITES_GRATUIT,
  };
}

/** Un signal, tel qu'il sort de la base. */
export interface Signal {
  id: string;
  published_at: string;
  pair: string;
  side: string;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number | null;
  take_profit_2: number | null;
  risk_reward: number | null;
  position_size_pct: number | null;
  conviction: number;
  rationale: string;
  status: string;
  closed_at: string | null;
  result_pct: number | null;
  macro_flag: boolean;
}

/**
 * Le filtrage par palier. LE POINT SENSIBLE DE TOUTE L'API.
 *
 * Un compte gratuit voit :
 *   - uniquement BTC, ETH et SOL,
 *   - et seulement deux heures apres la publication.
 *
 * Les signaux ecartes ne sont pas masques : ils ne sont pas renvoyes.
 */
export function filtrerPourLePalier(
  signaux: Signal[],
  capacites: Capacites,
  maintenant = Date.now(),
): Signal[] {
  const retardMs = Math.max(0, capacites.retard_minutes) * 60_000;
  return signaux.filter((s) => {
    if (!capacites.toutes_paires && !PAIRES_GRATUITES.includes(s.pair)) {
      return false;
    }
    if (retardMs === 0) return true;
    const publie = Date.parse(s.published_at);
    // FAIL-CLOSED sur une date illisible : sans elle on ne peut pas
    // savoir si le retard est ecoule, et laisser passer donnerait
    // gratuitement un signal en temps reel.
    return Number.isFinite(publie) && maintenant - publie >= retardMs;
  });
}

/**
 * Limitation de debit, par utilisateur et par fonction.
 *
 * Simple compteur en memoire du conteneur : il ne survit pas a un
 * redemarrage et ne se partage pas entre instances. C'est assez pour
 * arreter une boucle d'application qui part en vrille — ce qui est le
 * cas reel ici. Une vraie protection contre un attaquant demanderait
 * un compteur partage ; ce n'est pas la menace a ce stade, et le dire
 * vaut mieux que de laisser croire le contraire.
 */
const compteurs = new Map<string, { jusqua: number; reste: number }>();

export function debitDepasse(cle: string, parMinute = 60): boolean {
  const maintenant = Date.now();
  const actuel = compteurs.get(cle);
  if (!actuel || actuel.jusqua < maintenant) {
    compteurs.set(cle, { jusqua: maintenant + 60_000, reste: parMinute - 1 });
    return false;
  }
  if (actuel.reste <= 0) return true;
  actuel.reste -= 1;
  return false;
}

/** L'ossature commune : CORS, authentification, debit. */
export async function servir(
  requete: Request,
  nom: string,
  traitement: (v: Visiteur, s: SupabaseClient, r: Request) => Promise<Response>,
  parMinute = 60,
): Promise<Response> {
  if (requete.method === "OPTIONS") {
    return new Response("ok", { headers: ENTETES_CORS });
  }
  const service = clientService();
  const visiteur = await identifier(requete, service);
  if (!visiteur) return erreur("connexion requise", 401);
  if (debitDepasse(`${nom}:${visiteur.id}`, parMinute)) {
    return erreur("trop de requetes, reessaie dans une minute", 429);
  }
  try {
    return await traitement(visiteur, service, requete);
  } catch (e) {
    console.error(`${nom} :`, e);
    return erreur("erreur interne", 500);
  }
}
