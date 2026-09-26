/**
 * Luna -- lecture du personnage et de la file de generation, ecriture
 * d'une nouvelle demande. Toute la generation reelle (script/photo/
 * voix/video) tourne sur le VPS via `ops/executer_luna.py` (cron) ;
 * l'application ne fait jamais qu'ajouter une ligne `en_attente` et
 * regarder son statut changer -- meme principe que le reste
 * d'Alluxe Bot, aucun acces direct au VPS depuis le telephone.
 */
import { supabase } from "./supabase";

export interface Persona {
  prenom: string;
  age: number;
  metier: string;
  contexte: string;
  caractere: string[];
  passions: string[];
}

/** `null` tant que la table n'existe pas encore (migration pas encore
 * appliquee) ou que le cron ne l'a pas encore remplie une premiere fois. */
export async function persona(): Promise<Persona | null> {
  const { data, error } = await supabase
    .from("luna_persona")
    .select("prenom, age, metier, contexte, caractere, passions")
    .eq("id", "luna")
    .maybeSingle();
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return null;
    throw error;
  }
  return data as unknown as Persona | null;
}

export type StatutPublication = "en_attente" | "en_cours" | "terminee" | "echec";

export interface Publication {
  id: string;
  created_at: string;
  demande: string;
  statut: StatutPublication;
  media_type: "auto" | "photo" | "video";
  reference_path: string | null;
  aspect_ratio: string;
  duration_seconds: number;
  quality: "brouillon" | "finale";
  provider: string | null;
  provider_task_id: string | null;
  generation_status: "queued" | "generating" | "succeeded" | "failed";
  publish_requested: boolean;
  published_at: string | null;
  published_platform: string | null;
  published_media_id: string | null;
  legende: string;
  scene_prompt: string;
  chemin_photo: string | null;
  chemin_voix: string | null;
  chemin_video: string | null;
  erreurs: Record<string, string>;
}

const COLONNES_PUBLICATION =
  "id, created_at, demande, statut, media_type, reference_path, aspect_ratio, duration_seconds, quality, provider, provider_task_id, generation_status, publish_requested, published_at, published_platform, published_media_id, legende, scene_prompt, chemin_photo, chemin_voix, chemin_video, erreurs";

export async function publications(limite = 30): Promise<Publication[]> {
  const { data, error } = await supabase
    .from("luna_publications")
    .select(COLONNES_PUBLICATION)
    .order("created_at", { ascending: false })
    .limit(limite);
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return [];
    throw error;
  }
  return (data ?? []) as unknown as Publication[];
}

/** Depose une demande de generation. `demande` vide : Luna improvise
 * seule (meme comportement que `python3 alluxe.py` sans argument). */
export async function demanderGeneration(demande: string): Promise<void> {
  const { error } = await supabase
    .from("luna_publications")
    .insert({ demande: demande.trim() });
  if (error) throw error;
}

const CACHE_URLS = new Map<string, { url: string; expire: number }>();

/** URL signee (1h) vers un fichier du bucket prive `luna`. Mise en
 * cache en memoire pour ne pas re-signer a chaque re-rendu de liste. */
export async function urlSignee(cheminStockage: string): Promise<string | null> {
  const dejaConnue = CACHE_URLS.get(cheminStockage);
  if (dejaConnue && dejaConnue.expire > Date.now()) return dejaConnue.url;
  const { data, error } = await supabase.storage
    .from("luna")
    .createSignedUrl(cheminStockage, 3600);
  if (error || !data) return null;
  CACHE_URLS.set(cheminStockage, { url: data.signedUrl, expire: Date.now() + 55 * 60 * 1000 });
  return data.signedUrl;
}
