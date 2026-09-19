/**
 * Acces direct aux donnees reelles du robot, sans passage par les
 * fonctions Edge d'Allure -- celles-ci masquent/retardent selon le
 * palier d'abonnement, ce qui n'a pas de sens pour l'outil PRIVE de
 * l'operateur. Alluxe Bot lit les tables Supabase directement, avec le
 * compte de l'operateur (RLS deja permissive sur `signals`/`etat_public`
 * pour tout utilisateur connecte -- voir supabase/migrations).
 */
import { supabase } from "./supabase";

export interface EtatCapital {
  capital_eur: number;
  variation_jour_pct: number;
  updated_at: string;
}

export interface Position {
  id: string;
  pair: string;
  side: "buy" | "sell";
  entry_price: number;
  stop_loss: number;
  take_profit_1: number | null;
  take_profit_2: number | null;
  position_size_pct: number | null;
  published_at: string;
  status: string;
  closed_at: string | null;
  result_pct: number | null;
}

export async function etatCapital(): Promise<EtatCapital | null> {
  const { data, error } = await supabase
    .from("etat_public")
    .select("capital_eur, variation_jour_pct, updated_at")
    .eq("id", "robot")
    .maybeSingle();
  if (error) throw error;
  return data;
}

const COLONNES_POSITION = "id, pair, side, entry_price, stop_loss, take_profit_1, take_profit_2, position_size_pct, published_at, status, closed_at, result_pct";

// `is_demo` est EXPLICITE sur chaque requete ci-dessous, jamais implicite
// -- fuite du 18 sept. : la simulation a 500 EUR virtuels a publie ses
// positions dans ces memes tables sans distinction, et une position
// fictive est apparue dans l'app comme si elle etait reelle. La colonne
// existe depuis (supabase/migrations/20260918234500_marquer_demo.sql) ;
// les fonctions REELLES filtrent `is_demo=false`, les fonctions DEMO
// filtrent `is_demo=true` -- jamais l'un sans l'autre, jamais melange.

export async function positionsOuvertes(): Promise<Position[]> {
  const { data, error } = await supabase
    .from("signals")
    .select(COLONNES_POSITION)
    .eq("status", "active")
    .eq("is_demo", false)
    .not("published_at", "is", null)
    .order("published_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as unknown as Position[];
}

export async function historique(limite = 100): Promise<Position[]> {
  const { data, error } = await supabase
    .from("signals")
    .select(COLONNES_POSITION)
    .in("status", ["closed_tp", "closed_sl", "cancelled"])
    .eq("is_demo", false)
    .not("published_at", "is", null)
    .order("closed_at", { ascending: false })
    .limit(limite);
  if (error) throw error;
  return (data ?? []) as unknown as Position[];
}

/** Memes positions, cote simulation a capital virtuel (voir run_demo.py). */
export async function positionsOuvertesDemo(): Promise<Position[]> {
  const { data, error } = await supabase
    .from("signals")
    .select(COLONNES_POSITION)
    .eq("status", "active")
    .eq("is_demo", true)
    .not("published_at", "is", null)
    .order("published_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as unknown as Position[];
}

export async function historiqueDemo(limite = 100): Promise<Position[]> {
  const { data, error } = await supabase
    .from("signals")
    .select(COLONNES_POSITION)
    .in("status", ["closed_tp", "closed_sl", "cancelled"])
    .eq("is_demo", true)
    .not("published_at", "is", null)
    .order("closed_at", { ascending: false })
    .limit(limite);
  if (error) throw error;
  return (data ?? []) as unknown as Position[];
}

/** Les 40 trades de preuve + objectifs -- table privee, reservee admin.
 * Rend `null` tant que la table/la ligne n'existe pas encore (chantier
 * en cours le 15 sept.), plutot que de planter l'ecran. */
export interface Objectifs {
  stats_40: {
    trades: number;
    taux_reussite_pct: number | null;
    esperance_R_nette: number | null;
    facteur_profit: number | null;
    palier: string;
  };
  objectifs: Record<string, { atteint: boolean; pct: number }>;
  methode: string;
  updated_at: string;
}

export async function objectifs(): Promise<Objectifs | null> {
  const { data, error } = await supabase
    .from("alluxe_bot_prive")
    .select("stats_40, objectifs, methode, updated_at")
    .eq("id", "robot")
    .maybeSingle();
  if (error) {
    // Table pas encore creee : on le traite comme "pas de donnees",
    // pas comme une panne a afficher a l'ecran.
    if (/relation .* does not exist/i.test(error.message)) return null;
    throw error;
  }
  return data;
}

export interface Alerte {
  id: number;
  created_at: string;
  niveau: "debug" | "info" | "trade" | "warning" | "critical";
  titre: string;
  corps: string;
}

export async function alertes(limite = 100): Promise<Alerte[]> {
  const { data, error } = await supabase
    .from("alluxe_bot_alertes")
    .select("id, created_at, niveau, titre, corps")
    .eq("is_demo", false)
    .order("created_at", { ascending: false })
    .limit(limite);
  if (error) throw error;
  return (data ?? []) as unknown as Alerte[];
}

/** Memes alertes, cote simulation -- deja prefixees "[DEMO]" par NotifierDemo. */
export async function alertesDemo(limite = 100): Promise<Alerte[]> {
  const { data, error } = await supabase
    .from("alluxe_bot_alertes")
    .select("id, created_at, niveau, titre, corps")
    .eq("is_demo", true)
    .order("created_at", { ascending: false })
    .limit(limite);
  if (error) throw error;
  return (data ?? []) as unknown as Alerte[];
}
