/**
 * Données de l'onglet alluxe.ia (remplace Luna, 7 oct. 2026).
 *
 * Tout est écrit par le serveur (ops/alluxe_ia_tableau.py) ; l'appli lit, et ne
 * change QUE le statut d'une cible (« fait », « ignoré ») ou d'un Reel préparé
 * (« publié »). Lecture réservée aux admins (migration 20261007200000).
 *
 * L'assistant commentaires ne commente RIEN lui-même : il propose, l'opérateur
 * publie à la main. Commenter par robot fait bloquer ou masquer un compte.
 */
import { supabase } from "./supabase";

export interface CompteReseau {
  reseau: string;
  abonnes: number | null;
  publications: number | null;
  portee_7j: number | null;
  vues_7j: number | null;
  visites_profil_7j: number | null;
  clics_site_7j: number | null;
  maj_le: string;
}

export interface Media {
  media_id: string;
  type: "REEL" | "CARROUSEL" | "PHOTO" | string;
  legende: string | null;
  lien: string | null;
  vignette: string | null;
  publie_le: string | null;
  portee: number | null;
  vues: number | null;
  likes: number | null;
  commentaires: number | null;
  enregistrements: number | null;
  partages: number | null;
  duree_moyenne_s: number | null;
}

export interface Cible {
  id: string;
  jour: string;
  lien: string;
  legende: string | null;
  likes: number | null;
  commentaires: number | null;
  hashtag: string | null;
  commentaire_propose: string | null;
  statut: "a_faire" | "fait" | "ignore";
}

export interface APublier {
  id: string;
  titre: string;
  reseau: string;
  chemin_video: string | null;
  legende: string | null;
  musique: string | null;
  statut: "a_publier" | "publie";
  cree_le: string;
}

export async function comptes(): Promise<CompteReseau[]> {
  const { data, error } = await supabase.from("alluxe_ia_compte").select("*");
  if (error) throw error;
  return (data ?? []) as CompteReseau[];
}

export async function medias(limite = 40): Promise<Media[]> {
  const { data, error } = await supabase.from("alluxe_ia_medias").select("*")
    .order("publie_le", { ascending: false }).limit(limite);
  if (error) throw error;
  return (data ?? []) as Media[];
}

export async function cibles(): Promise<Cible[]> {
  const { data, error } = await supabase.from("alluxe_ia_cibles").select("*")
    .order("jour", { ascending: false }).order("likes", { ascending: false }).limit(40);
  if (error) throw error;
  return (data ?? []) as Cible[];
}

export async function marquerCible(id: string, statut: Cible["statut"]): Promise<void> {
  const { error } = await supabase.from("alluxe_ia_cibles").update({ statut }).eq("id", id);
  if (error) throw error;
}

export async function aPublier(): Promise<APublier[]> {
  const { data, error } = await supabase.from("alluxe_ia_a_publier").select("*")
    .order("cree_le", { ascending: false }).limit(30);
  if (error) throw error;
  return (data ?? []) as APublier[];
}

export async function marquerPublie(id: string, statut: APublier["statut"]): Promise<void> {
  const { error } = await supabase.from("alluxe_ia_a_publier").update({ statut }).eq("id", id);
  if (error) throw error;
}

/** Lien de téléchargement temporaire (1 h) d'une vidéo du seau privé. */
export async function lienVideo(chemin: string): Promise<string | null> {
  const { data, error } = await supabase.storage.from("luna").createSignedUrl(chemin, 3600, { download: true });
  if (error || !data) return null;
  return data.signedUrl;
}
