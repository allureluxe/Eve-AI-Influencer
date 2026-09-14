/**
 * L'acces aux donnees, et la gestion du hors-ligne.
 *
 * DEUX PRINCIPES
 * --------------
 * 1. L'application ne decide JAMAIS de ce que l'utilisateur a le droit
 *    de voir. Elle demande, le serveur filtre. Il n'y a pas une ligne
 *    de logique gratuit/payant dans ce fichier — et il ne doit jamais y
 *    en avoir : un filtrage cote application est un filtrage qu'on peut
 *    retirer en ouvrant le fichier.
 *
 * 2. UNE REPONSE ANCIENNE VAUT MIEUX QU'UN ECRAN VIDE, A CONDITION DE
 *    LE DIRE. Le metro, l'ascenseur, le forfait epuise : l'utilisateur
 *    ouvre l'application hors reseau plus souvent qu'on ne croit. On
 *    sert le cache avec son age affiche. Un ecran blanc et une roue qui
 *    tourne, c'est une application qu'on desinstalle.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { supabase } from "./supabase";

export interface Signal {
  id: string;
  published_at: string;
  pair: string;
  side: "buy" | "sell";
  entry_price: number;
  stop_loss: number;
  take_profit_1: number | null;
  take_profit_2: number | null;
  risk_reward: number | null;
  position_size_pct: number | null;
  conviction: number;
  rationale: string;
  status: "active" | "closed_tp" | "closed_sl" | "cancelled";
  closed_at: string | null;
  result_pct: number | null;
  macro_flag: boolean;
}

export type Palier = "free" | "essentiel" | "plus" | "pro";

/**
 * Ce que le palier donne, tel que le SERVEUR le declare.
 *
 * L'application ne recopie jamais cette grille : elle la recoit. Une
 * copie locale se desynchroniserait le jour ou une offre change, et sa
 * forme la plus probable est la pire — l'ecran promet une capacite que
 * le serveur refuse.
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

export interface ReponseSignaux {
  tier: Palier;
  capacites: Capacites;
  actifs: Signal[];
  clotures: Signal[];
  masques: number;
}

/** Une position ouverte, avec le cours du moment. */
export interface PositionDirecte extends Signal {
  prix_courant: number | null;
  variation_pct: number | null;
  distance_stop_pct: number | null;
  /** La protection est passee au-dessus du prix d'achat. */
  a_l_abri: boolean;
}

export interface ReponseDirect {
  tier: Palier;
  positions: PositionDirecte[];
  cotations_a: string | null;
  cotations_disponibles: boolean;
}

export interface Offre {
  tier: Palier;
  rang: number;
  nom: string;
  accroche: string;
  toutes_paires: boolean;
  retard_minutes: number;
  positions_direct: boolean;
  note_du_matin: boolean;
  historique_complet: boolean;
  export_csv: boolean;
  produit_id: string | null;
  prix_indicatif_eur: number | null;
  produit_id_annuel: string | null;
  /** Prix TOTAL de l'annee, deja remise de 10 % sur le tarif mensuel x 12. */
  prix_indicatif_annuel_eur: number | null;
}

export interface NoteMarche {
  id: string;
  published_at: string;
  headline: string;
  body_fr: string;
  trend_score: number | null;
  volatility_score: number | null;
  fear_greed: number | null;
  btc_dominance: number | null;
}

export interface Evenement {
  id: string;
  event_time: string;
  name_fr: string;
  country: string;
  impact: "low" | "medium" | "high";
  eve_policy: string;
  actual: number | null;
  forecast: number | null;
  previous: number | null;
}

export interface Performance {
  fiable: boolean;
  trades: number;
  minimum?: number;
  message?: string;
  depart?: number;
  courbe: { date: string; capital: number }[];
  stats: {
    capital_final: number;
    variation_pct: number;
    taux_reussite: number;
    gain_moyen: number;
    perte_moyenne: number;
    recul_max_pct: number;
    facteur_profit: number | null;
  } | null;
  hypotheses?: string[];
}

/** Ce que rend chaque lecture : la donnee, et d'ou elle vient. */
export interface Resultat<T> {
  donnee: T | null;
  /** Vrai si la donnee vient du cache faute de reseau. */
  duCache: boolean;
  /** Age du cache en minutes. Null quand la donnee est fraiche. */
  ageMinutes: number | null;
  /** Renseigne quand meme le cache est vide. */
  erreur: string | null;
}

const PREFIXE = "eve:cache:";

async function ecrireCache(cle: string, donnee: unknown): Promise<void> {
  try {
    await AsyncStorage.setItem(
      PREFIXE + cle,
      JSON.stringify({ a: Date.now(), d: donnee }),
    );
  } catch {
    // Un cache qui n'a pas pu s'ecrire n'est pas une raison d'echouer :
    // la donnee fraiche est deja affichee.
  }
}

async function lireCache<T>(cle: string): Promise<{ d: T; age: number } | null> {
  try {
    const brut = await AsyncStorage.getItem(PREFIXE + cle);
    if (!brut) return null;
    const { a, d } = JSON.parse(brut);
    return { d, age: Math.round((Date.now() - a) / 60_000) };
  } catch {
    return null;
  }
}

/**
 * Appelle une fonction Edge, avec repli sur le cache.
 *
 * Le jeton de session part dans l'en-tete : c'est lui, et lui seul, qui
 * dit au serveur qui demande. L'application n'annonce jamais son propre
 * palier.
 */
async function appeler<T>(chemin: string, options?: {
  methode?: string;
  corps?: unknown;
  cache?: boolean;
}): Promise<Resultat<T>> {
  const cache = options?.cache !== false;
  try {
    const { data: session } = await supabase.auth.getSession();
    const jeton = session.session?.access_token;
    if (!jeton) {
      return { donnee: null, duCache: false, ageMinutes: null,
               erreur: "connexion requise" };
    }

    const { data, error } = await supabase.functions.invoke<T>(chemin, {
      method: (options?.methode ?? "GET") as "GET" | "POST",
      body: options?.corps as Record<string, unknown> | undefined,
    });
    if (error) throw error;

    if (cache) await ecrireCache(chemin, data);
    return { donnee: data as T, duCache: false, ageMinutes: null, erreur: null };
  } catch (e) {
    if (!cache) {
      return { donnee: null, duCache: false, ageMinutes: null,
               erreur: message(e) };
    }
    const vieux = await lireCache<T>(chemin);
    if (vieux) {
      return { donnee: vieux.d, duCache: true, ageMinutes: vieux.age,
               erreur: null };
    }
    return { donnee: null, duCache: false, ageMinutes: null, erreur: message(e) };
  }
}

function message(e: unknown): string {
  const brut = e instanceof Error ? e.message : String(e);
  // Les messages techniques ne disent rien a l'utilisateur. On traduit
  // les deux seuls cas qu'il peut comprendre et sur lesquels il peut agir.
  if (/network|fetch|timeout/i.test(brut)) return "Pas de connexion.";
  if (/401|jwt|unauthor/i.test(brut)) return "Reconnecte-toi.";
  return "Service momentanement indisponible.";
}

export const api = {
  signaux: () => appeler<ReponseSignaux>("signals"),
  direct: () => appeler<ReponseDirect>("direct"),
  note: () => appeler<{ note: NoteMarche | null }>("market-note"),
  evenements: () => appeler<{ evenements: Evenement[] }>("events"),
  performance: () => appeler<Performance>("performance"),
  marquerPris: (signalId: string) =>
    appeler<{ ok: boolean }>("signal-taken", {
      methode: "POST", corps: { signal_id: signalId }, cache: false,
    }),
};

/** « il y a 3 minutes ». Utilise pour l'age du cache. */
export function ilYA(minutes: number): string {
  if (minutes < 1) return "a l'instant";
  if (minutes === 1) return "il y a 1 minute";
  if (minutes < 60) return `il y a ${minutes} minutes`;
  const h = Math.round(minutes / 60);
  if (h < 24) return `il y a ${h} heure${h > 1 ? "s" : ""}`;
  const j = Math.round(h / 24);
  return `il y a ${j} jour${j > 1 ? "s" : ""}`;
}
