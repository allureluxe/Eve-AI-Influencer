/**
 * Le reseau social -- phase 1 : posts, likes, commentaires, messages.
 *
 * MEME PRINCIPE QUE api.ts : ce fichier ne decide de rien, il demande.
 * Le serveur (RLS + la vue `posts_public`) filtre ce que chaque compte
 * a le droit de voir. Aucune logique d'autorisation ici.
 *
 * `resultat_pct` EST DECLARE PAR L'UTILISATEUR, JAMAIS LU DEPUIS UN VRAI
 * COMPTE D'ECHANGE. Voir la note de securite dans la migration
 * `20260914180000_social.sql`. Tout affichage de ce chiffre doit le dire
 * clairement -- ne jamais le presenter avec la meme confiance qu'un
 * `Signal` (qui, lui, vient du robot et est garanti exact).
 */

import { supabase } from "../../services/supabase";

export interface Post {
  id: string;
  auteur: string;
  auteur_pseudo: string | null;
  auteur_photo_url: string | null;
  created_at: string;
  texte: string | null;
  image_url: string | null;
  resultat_pct: number | null;
  likes_count: number;
  comments_count: number;
  jaime_par_moi: boolean;
}

export interface Commentaire {
  id: string;
  post_id: string;
  auteur: string;
  created_at: string;
  texte: string;
}

export interface MessagePrive {
  id: string;
  expediteur: string;
  destinataire: string;
  created_at: string;
  texte: string;
  lu_le: string | null;
}

const social = {
  /** Le fil : les posts les plus recents d'abord. */
  async fil(limite = 30): Promise<Post[]> {
    const { data, error } = await supabase
      .from("posts_public")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(limite);
    if (error) throw error;
    return (data ?? []) as Post[];
  },

  /**
   * Publie un post. `resultatPct` reste facultatif et n'est jamais
   * verifie -- voir la note de securite en tete de fichier.
   */
  async publier(params: {
    texte?: string; imageUrl?: string; resultatPct?: number;
  }): Promise<void> {
    const { data: session } = await supabase.auth.getSession();
    const id = session.session?.user?.id;
    if (!id) throw new Error("non connecte");
    const { error } = await supabase.from("posts").insert({
      auteur: id,
      texte: params.texte ?? null,
      image_url: params.imageUrl ?? null,
      resultat_pct: params.resultatPct ?? null,
    });
    if (error) throw error;
  },

  async supprimerPost(postId: string): Promise<void> {
    const { error } = await supabase.from("posts").delete().eq("id", postId);
    if (error) throw error;
  },

  /** Bascule le like : pose s'il n'existe pas, retire sinon. */
  async basculerJaime(postId: string, dejaAime: boolean): Promise<void> {
    const { data: session } = await supabase.auth.getSession();
    const id = session.session?.user?.id;
    if (!id) throw new Error("non connecte");
    if (dejaAime) {
      const { error } = await supabase.from("post_likes")
        .delete().eq("post_id", postId).eq("user_id", id);
      if (error) throw error;
    } else {
      const { error } = await supabase.from("post_likes")
        .insert({ post_id: postId, user_id: id });
      if (error) throw error;
    }
  },

  async commentaires(postId: string): Promise<Commentaire[]> {
    const { data, error } = await supabase
      .from("post_comments")
      .select("*")
      .eq("post_id", postId)
      .order("created_at", { ascending: true });
    if (error) throw error;
    return (data ?? []) as Commentaire[];
  },

  async commenter(postId: string, texte: string): Promise<void> {
    const { data: session } = await supabase.auth.getSession();
    const id = session.session?.user?.id;
    if (!id) throw new Error("non connecte");
    const { error } = await supabase.from("post_comments")
      .insert({ post_id: postId, auteur: id, texte });
    if (error) throw error;
  },

  /**
   * Une ligne par correspondant, avec le dernier message -- calculee
   * cote client sur un historique complet le temps que le volume reste
   * faible. A remplacer par une vue serveur si les conversations
   * grossissent (meme raisonnement que `posts_public`).
   */
  async conversations(): Promise<
    { correspondant: string; dernier: MessagePrive; non_lus: number }[]
  > {
    const { data: session } = await supabase.auth.getSession();
    const moi = session.session?.user?.id;
    if (!moi) return [];
    const { data, error } = await supabase
      .from("messages")
      .select("*")
      .order("created_at", { ascending: false });
    if (error) throw error;
    const parCorrespondant = new Map<string,
      { correspondant: string; dernier: MessagePrive; non_lus: number }>();
    for (const m of (data ?? []) as MessagePrive[]) {
      const autre = m.expediteur === moi ? m.destinataire : m.expediteur;
      const existant = parCorrespondant.get(autre);
      if (!existant) {
        parCorrespondant.set(autre, {
          correspondant: autre, dernier: m,
          non_lus: m.destinataire === moi && !m.lu_le ? 1 : 0,
        });
      } else if (m.destinataire === moi && !m.lu_le) {
        existant.non_lus += 1;
      }
    }
    return Array.from(parCorrespondant.values());
  },

  async messagesAvec(correspondantId: string): Promise<MessagePrive[]> {
    const { data: session } = await supabase.auth.getSession();
    const moi = session.session?.user?.id;
    if (!moi) return [];
    const { data, error } = await supabase
      .from("messages")
      .select("*")
      .or(`and(expediteur.eq.${moi},destinataire.eq.${correspondantId}),` +
          `and(expediteur.eq.${correspondantId},destinataire.eq.${moi})`)
      .order("created_at", { ascending: true });
    if (error) throw error;
    return (data ?? []) as MessagePrive[];
  },

  async envoyerMessage(destinataireId: string, texte: string): Promise<void> {
    const { data: session } = await supabase.auth.getSession();
    const id = session.session?.user?.id;
    if (!id) throw new Error("non connecte");
    const { error } = await supabase.from("messages")
      .insert({ expediteur: id, destinataire: destinataireId, texte });
    if (error) throw error;
  },

  async marquerLu(messageId: string): Promise<void> {
    const { error } = await supabase.from("messages")
      .update({ lu_le: new Date().toISOString() }).eq("id", messageId);
    if (error) throw error;
  },
};

export { social };
