/**
 * J'aime / pas j'aime et commentaires sur le contenu du robot (signaux,
 * point du matin) -- distinct de social.ts, qui porte les posts crees
 * par les utilisateurs eux-memes.
 *
 * Demande de l'operateur, 14 sept. : « rajoute sur chaque position, ou
 * analyse et signaux, la possibilite aux utilisateurs de laisser un
 * commentaire, un j'aime ou un negatif ».
 */

import { supabase } from "../../services/supabase";

export type TypeReaction = "jaime" | "pas_jaime";
export type Cible = "signal" | "note";

export interface CompteurReaction {
  jaime_count: number;
  pas_jaime_count: number;
  comments_count: number;
  ma_reaction: TypeReaction | null;
}

export interface CommentaireGenerique {
  id: string;
  auteur: string;
  created_at: string;
  texte: string;
}

const TABLES = {
  signal: {
    vue: "signals_avec_reactions",
    reactions: "signal_reactions",
    commentaires: "signal_comments",
    cle: "signal_id",
  },
  note: {
    vue: "notes_avec_reactions",
    reactions: "note_reactions",
    commentaires: "note_comments",
    cle: "note_id",
  },
} as const;

async function idUtilisateur(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.user?.id ?? null;
}

const reactions = {
  async compteurs(cible: Cible, id: string): Promise<CompteurReaction | null> {
    const { vue } = TABLES[cible];
    const { data, error } = await supabase.from(vue).select("*")
      .eq("id", id).maybeSingle();
    if (error || !data) return null;
    return data as CompteurReaction;
  },

  /** `type: null` retire la reaction ; sinon la pose ou la change. */
  async reagir(cible: Cible, id: string, type: TypeReaction | null): Promise<void> {
    const { reactions: table, cle } = TABLES[cible];
    const uid = await idUtilisateur();
    if (!uid) throw new Error("non connecte");
    if (type === null) {
      await supabase.from(table).delete().eq(cle, id).eq("user_id", uid);
      return;
    }
    await supabase.from(table).upsert(
      { [cle]: id, user_id: uid, type }, { onConflict: `${cle},user_id` });
  },

  async commentaires(cible: Cible, id: string): Promise<CommentaireGenerique[]> {
    const { commentaires: table, cle } = TABLES[cible];
    const { data, error } = await supabase.from(table).select("*")
      .eq(cle, id).order("created_at", { ascending: true });
    if (error) throw error;
    return (data ?? []) as CommentaireGenerique[];
  },

  async commenter(cible: Cible, id: string, texte: string): Promise<void> {
    const { commentaires: table, cle } = TABLES[cible];
    const uid = await idUtilisateur();
    if (!uid) throw new Error("non connecte");
    const { error } = await supabase.from(table)
      .insert({ [cle]: id, auteur: uid, texte });
    if (error) throw error;
  },
};

export { reactions };
