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
  /** "<id interne>:<etage>" -- l'etage de pyramide se lit a la fin.
   *  Un renfort de pyramide est publie comme un signal a part entiere
   *  (voir gold_bot/engine.py::_publier_le_signal), d'ou ce suffixe. */
  reference: string | null;
  pair: string;
  side: "buy" | "sell";
  entry_price: number;
  stop_loss: number;
  take_profit_1: number | null;
  take_profit_2: number | null;
  position_size_pct: number | null;
  /** Capital au moment de l'ouverture. `position_size_pct` n'en est
   *  qu'un pourcentage : sans lui, la mise recalculee devient fausse des
   *  qu'un depot a lieu. Nul sur les lignes d'avant le 19 sept. */
  capital_eur: number | null;
  /** Quantite reellement achetee, en unites de la crypto. Le seul champ
   *  qui reponde a « combien j'en ai » -- `position_size_pct` est un
   *  pourcentage de RISQUE et la mise en euros s'en deduit. Nul avant le
   *  19 sept. */
  volume: number | null;
  /** Le stop SUIVEUR courant. `stop_loss` reste le stop d'OUVERTURE et
   *  ne bouge jamais (tout le calcul du R en depend). Nul tant que le
   *  suiveur n'a pas deplace le stop -- l'ecran retombe alors sur
   *  `stop_loss`. */
  stop_loss_actuel: number | null;
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

/**
 * L'APPLICATION ET LA BASE NE SE METTENT PAS A JOUR ENSEMBLE.
 *
 * L'APK part sur le telephone de l'operateur ; les colonnes arrivent en
 * base par une migration. Rien ne garantit l'ordre, et PostgREST refuse
 * la requete ENTIERE si une seule colonne demandee n'existe pas
 * (erreur 42703). Une liste de positions vide, sans explication --
 * exactement ce qui serait arrive le 19 sept. : les colonnes `volume`
 * et `stop_loss_actuel` ont ete ajoutees au code alors que la migration
 * n'avait pas pu etre appliquee (jeton Supabase expire).
 *
 * On demande donc le confort, et on retombe sur l'essentiel s'il n'est
 * pas encore la. Le detail perd deux lignes ; la liste, elle, s'affiche
 * toujours.
 */
const COLONNES_BASE = "id, reference, capital_eur, pair, side, entry_price, stop_loss, take_profit_1, take_profit_2, position_size_pct, published_at, status, closed_at, result_pct";
const COLONNES_CONFORT = `${COLONNES_BASE}, volume, stop_loss_actuel`;

/** Une fois la reponse connue, on ne retente plus : inutile de payer un
 *  aller-retour rate a chaque rafraichissement. */
let colonnesConfortDisponibles: boolean | null = null;

function colonnesPosition(): string {
  return colonnesConfortDisponibles === false ? COLONNES_BASE : COLONNES_CONFORT;
}

/** Vrai si l'erreur dit « cette colonne n'existe pas ». */
function colonneAbsente(erreur: { code?: string; message?: string } | null): boolean {
  if (!erreur) return false;
  return erreur.code === "42703"
    || /column .* does not exist/i.test(erreur.message ?? "");
}

/**
 * Joue la requete avec les colonnes de confort, et la rejoue sans elles
 * si la base ne les connait pas encore.
 */
async function lirePositions(
  construire: (colonnes: string) => PromiseLike<{ data: unknown; error: any }>,
): Promise<Position[]> {
  const { data, error } = await construire(colonnesPosition());
  if (!error) {
    if (colonnesConfortDisponibles === null) colonnesConfortDisponibles = true;
    return (data ?? []) as Position[];
  }
  if (!colonneAbsente(error)) throw error;
  colonnesConfortDisponibles = false;
  const repli = await construire(COLONNES_BASE);
  if (repli.error) throw repli.error;
  return (repli.data ?? []) as Position[];
}

// `is_demo` est EXPLICITE sur chaque requete ci-dessous, jamais implicite
// -- fuite du 18 sept. : la simulation a 500 EUR virtuels a publie ses
// positions dans ces memes tables sans distinction, et une position
// fictive est apparue dans l'app comme si elle etait reelle. La colonne
// existe depuis (supabase/migrations/20260918234500_marquer_demo.sql) ;
// les fonctions REELLES filtrent `is_demo=false`, les fonctions DEMO
// filtrent `is_demo=true` -- jamais l'un sans l'autre, jamais melange.

export async function positionsOuvertes(): Promise<Position[]> {
  return lirePositions((colonnes) => supabase
    .from("signals")
    .select(colonnes)
    .eq("status", "active")
    .eq("is_demo", false)
    .not("published_at", "is", null)
    .order("published_at", { ascending: false }));
}

export async function historique(limite = 100): Promise<Position[]> {
  return lirePositions((colonnes) => supabase
    .from("signals")
    .select(colonnes)
    .in("status", ["closed_tp", "closed_sl", "cancelled"])
    .eq("is_demo", false)
    .not("published_at", "is", null)
    .order("closed_at", { ascending: false })
    .limit(limite));
}

/**
 * Memes positions, cote simulation (voir run_demo.py).
 *
 * `compte` distingue DEUX SIMULATIONS qui tournent en parallele sur le
 * meme marche : la seule facon de comparer deux methodes sans que le
 * marche s'en mele. Sans ce filtre, les positions des deux comptes
 * s'additionneraient a l'ecran -- la meme confusion que le 18 sept.
 * entre le simule et le reel, en plus difficile a voir puisque les deux
 * sont « virtuels ».
 */
export async function positionsOuvertesDemo(compte = "demo"): Promise<Position[]> {
  return lirePositions((colonnes) => supabase
    .from("signals")
    .select(colonnes)
    .eq("status", "active")
    .eq("is_demo", true)
    .eq("compte", compte)
    .not("published_at", "is", null)
    .order("published_at", { ascending: false }));
}

export async function historiqueDemo(limite = 100,
                                     compte = "demo"): Promise<Position[]> {
  // PAS de "cancelled" ici, contrairement a l'historique reel. Le robot
  // ne publie que des cloture_tp/sl ; les lignes "annulees" cote demo
  // sont les 20 positions neutralisees A LA MAIN le 18 sept. pendant la
  // fuite (voir fuite-signals-app). Ce ne sont pas des trades, et elles
  // noieraient les vrais resultats sous des lignes sans chiffre.
  return lirePositions((colonnes) => supabase
    .from("signals")
    .select(colonnes)
    .in("status", ["closed_tp", "closed_sl"])
    .eq("is_demo", true)
    .eq("compte", compte)
    .not("published_at", "is", null)
    .order("closed_at", { ascending: false })
    .limit(limite));
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
export async function alertesDemo(limite = 100,
                                  compte = "demo"): Promise<Alerte[]> {
  const { data, error } = await supabase
    .from("alluxe_bot_alertes")
    .select("id, created_at, niveau, titre, corps")
    .eq("is_demo", true)
    .eq("compte", compte)
    .order("created_at", { ascending: false })
    .limit(limite);
  if (error) throw error;
  return (data ?? []) as unknown as Alerte[];
}

// `etagePyramide` vit dans `composants/positionsTri` avec le reste du
// calcul pur : il y etait recopie a l'identique, et deux definitions de
// la meme regle finissent toujours par diverger. Reexporte ici pour que
// les appelants historiques n'aient rien a changer.
export { etagePyramide } from "../composants/positionsTri";


/**
 * La fiche d'un compte de simulation : quelle methode il fait tourner,
 * avec quel capital de depart, et quand il a donne signe de vie.
 *
 * Publiee par le robot LUI-MEME au demarrage, deduite de la
 * configuration qu'il vient de charger (`gold_bot/methode.py`).
 * L'application ne la recalcule pas et ne la recopie pas : c'est
 * exactement ce qui avait fait afficher « canal 20 jours » pendant une
 * semaine alors que le robot tournait a 10.
 */
export interface CompteDemo {
  compte: string;
  resume_methode: string;
  methode: string;
  capital_depart: number;
  vu_le: string;
}

export async function comptesDemo(): Promise<CompteDemo[]> {
  const { data, error } = await supabase
    .from("alluxe_bot_comptes")
    .select("compte, resume_methode, methode, capital_depart, vu_le")
    .order("compte");
  if (error) {
    // Table pas encore migree : on ne casse pas l'ecran pour autant.
    if (/does not exist/i.test(error.message)) return [];
    throw error;
  }
  return (data ?? []) as CompteDemo[];
}
