/**
 * J'aime / pas j'aime + commentaires, sous un signal ou une note.
 *
 * Un seul composant pour les deux (`cible`), pas deux quasi-identiques
 * -- meme raisonnement que le reste de l'application : trois lignes
 * dupliquees valent mieux qu'une abstraction premature, mais ici c'est
 * la MEME UI pour deux tables, donc un seul composant parametre.
 */

import React from "react";
import { ActivityIndicator, Pressable, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { espace, rayon } from "../../theme";
import { Separateur, T, useCouleurs, Vide } from "../../composants/base";
import {
  reactions, type Cible, type CommentaireGenerique, type CompteurReaction,
  type TypeReaction,
} from "../services/reactions";
import { quand } from "../services/format";

export function BarreReactions({ cible, id }: { cible: Cible; id: string }) {
  const c = useCouleurs();
  const [compte, setCompte] = React.useState<CompteurReaction | null>(null);
  const [ouvert, setOuvert] = React.useState(false);
  const [commentaires, setCommentaires] = React.useState<CommentaireGenerique[] | null>(null);
  const [texte, setTexte] = React.useState("");

  const charger = React.useCallback(async () => {
    setCompte(await reactions.compteurs(cible, id));
  }, [cible, id]);

  React.useEffect(() => { charger(); }, [charger]);

  async function basculer(type: TypeReaction) {
    if (!compte) return;
    const ancien = compte.ma_reaction;
    const nouveau = ancien === type ? null : type;
    // Mise a jour optimiste : on retire l'ancienne reaction du compte
    // qui la portait, on ajoute la nouvelle au sien.
    let jaime = compte.jaime_count, pasJaime = compte.pas_jaime_count;
    if (ancien === "jaime") jaime -= 1;
    if (ancien === "pas_jaime") pasJaime -= 1;
    if (nouveau === "jaime") jaime += 1;
    if (nouveau === "pas_jaime") pasJaime += 1;
    setCompte({ ...compte, ma_reaction: nouveau, jaime_count: jaime, pas_jaime_count: pasJaime });
    try {
      await reactions.reagir(cible, id, nouveau);
    } catch {
      // Pas grave : le prochain chargement retablit le vrai compte.
    } finally {
      charger();
    }
  }

  async function basculerCommentaires() {
    const prochain = !ouvert;
    setOuvert(prochain);
    if (prochain && commentaires === null) {
      try {
        setCommentaires(await reactions.commentaires(cible, id));
      } catch {
        setCommentaires([]);
      }
    }
  }

  async function envoyer() {
    const t = texte.trim();
    if (!t) return;
    setTexte("");
    try {
      await reactions.commenter(cible, id, t);
      setCommentaires(await reactions.commentaires(cible, id));
      charger();
    } catch {
      // Le champ vide sans le commentaire publie serait pire : on
      // laisse simplement l'utilisateur reessayer.
    }
  }

  return (
    <View style={{ marginTop: espace.l, paddingTop: espace.m,
                   borderTopWidth: 1, borderTopColor: c.filetDoux }}>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Pressable onPress={() => basculer("jaime")}
          style={{ flexDirection: "row", alignItems: "center", marginRight: espace.xl }}>
          <Ionicons
            name={compte?.ma_reaction === "jaime" ? "thumbs-up" : "thumbs-up-outline"}
            size={19} color={compte?.ma_reaction === "jaime" ? c.gain : c.encreDouce} />
          <T v="petit" style={{ marginLeft: espace.s }}>{compte?.jaime_count ?? 0}</T>
        </Pressable>
        <Pressable onPress={() => basculer("pas_jaime")}
          style={{ flexDirection: "row", alignItems: "center", marginRight: espace.xl }}>
          <Ionicons
            name={compte?.ma_reaction === "pas_jaime" ? "thumbs-down" : "thumbs-down-outline"}
            size={19} color={compte?.ma_reaction === "pas_jaime" ? c.perte : c.encreDouce} />
          <T v="petit" style={{ marginLeft: espace.s }}>{compte?.pas_jaime_count ?? 0}</T>
        </Pressable>
        <Pressable onPress={basculerCommentaires}
          style={{ flexDirection: "row", alignItems: "center" }}>
          <Ionicons name="chatbubble-outline" size={18} color={c.encreDouce} />
          <T v="petit" style={{ marginLeft: espace.s }}>{compte?.comments_count ?? 0}</T>
        </Pressable>
      </View>

      {ouvert ? (
        <View style={{ marginTop: espace.m }}>
          {commentaires === null ? (
            <ActivityIndicator />
          ) : commentaires.length === 0 ? (
            <Vide titre="Aucun commentaire" detail="Sois le premier a repondre." />
          ) : (
            commentaires.map((item) => (
              <View key={item.id} style={{ marginBottom: espace.s }}>
                <T v="legende">{quand(item.created_at)}</T>
                <T v="petit" style={{ marginTop: 2 }}>{item.texte}</T>
                <Separateur marge={espace.s} />
              </View>
            ))
          )}
          <View style={{ flexDirection: "row", alignItems: "center", marginTop: espace.s }}>
            <TextInput
              value={texte}
              onChangeText={setTexte}
              placeholder="Ecrire un commentaire..."
              placeholderTextColor={c.encrePale}
              style={{
                flex: 1, backgroundColor: c.creux, borderRadius: rayon.s,
                paddingHorizontal: espace.m, paddingVertical: espace.s + 2,
                color: c.encre, marginRight: espace.s,
              }}
            />
            <Pressable onPress={envoyer} disabled={!texte.trim()}>
              <Ionicons name="send" size={20}
                color={texte.trim() ? c.jaune : c.encrePale} />
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}
