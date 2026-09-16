/**
 * Communaute -- le fil des posts, comme le "Square" de Binance.
 *
 * PAS UN SIXIEME ONGLET. Demande explicite du 14 sept. : « essaye de
 * faire un peu comme Binance fait ». Binance ne donne pas au fil social
 * une case a lui dans la barre du bas -- il se rejoint par une icone
 * depuis l'accueil, et reste un ecran a part entiere une fois ouvert.
 * Meme choix ici : une icone dans l'en-tete d'Accueil.tsx ouvre cet
 * ecran, avec son propre "‹ Retour".
 *
 * LE RESULTAT AFFICHE EST DECLARE, JAMAIS VERIFIE -- voir la note de
 * securite dans social.ts et la migration `20260914180000_social.sql`.
 * Chaque badge de resultat porte le mot "declare" : ne jamais le
 * confondre avec un signal du robot, qui lui est garanti exact.
 */

import React from "react";
import {
  ActivityIndicator, FlatList, Image, KeyboardAvoidingView, Platform,
  Pressable, RefreshControl, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace, rayon } from "../../theme";
import {
  Bouton, Carte, Separateur, T, useCouleurs, Vide,
} from "../../composants/base";
import { social, type Commentaire, type Post } from "../services/social";
import { quand } from "../services/format";

/** L'avatar : la photo si elle existe, sinon les initiales du pseudo. */
function Avatar({ pseudo, photoUrl, taille = 36 }: {
  pseudo: string | null; photoUrl: string | null; taille?: number;
}) {
  const c = useCouleurs();
  if (photoUrl) {
    return <Image source={{ uri: photoUrl }}
      style={{ width: taille, height: taille, borderRadius: taille / 2 }} />;
  }
  const initiale = (pseudo ?? "?").charAt(0).toUpperCase();
  return (
    <View style={{
      width: taille, height: taille, borderRadius: taille / 2,
      backgroundColor: c.jaune, alignItems: "center", justifyContent: "center",
    }}>
      <T v="sousTitre" couleur={c.surJaune}>{initiale}</T>
    </View>
  );
}

/** Le badge d'un resultat declare -- jamais confondu avec un vrai signal. */
function BadgeResultat({ valeur }: { valeur: number }) {
  const c = useCouleurs();
  const positif = valeur >= 0;
  return (
    <View style={{
      flexDirection: "row", alignItems: "baseline", alignSelf: "flex-start",
      backgroundColor: c.creux, borderRadius: rayon.s,
      paddingHorizontal: espace.m, paddingVertical: espace.s,
      marginTop: espace.s,
    }}>
      <T v="chiffre" couleur={positif ? c.gain : c.perte} style={{ fontSize: 17 }}>
        {positif ? "+" : ""}{valeur.toFixed(1)} %
      </T>
      <T v="legende" style={{ marginLeft: espace.s }}>declare par l'auteur</T>
    </View>
  );
}

/** Le fil de commentaires d'un post, plein ecran. */
function EcranCommentaires({ post, onRetour }: {
  post: Post; onRetour: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [commentaires, setCommentaires] = React.useState<Commentaire[] | null>(null);
  const [texte, setTexte] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);

  const charger = React.useCallback(async () => {
    try {
      setCommentaires(await social.commentaires(post.id));
    } catch {
      setCommentaires([]);
    }
  }, [post.id]);

  React.useEffect(() => { charger(); }, [charger]);

  async function envoyer() {
    const t = texte.trim();
    if (!t) return;
    setEnvoi(true);
    try {
      await social.commenter(post.id, t);
      setTexte("");
      await charger();
    } catch {
      // Un commentaire perdu n'est pas grave : l'utilisateur voit qu'il
      // n'est pas apparu et peut reessayer.
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: c.fond }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={{ paddingTop: marges.top + espace.m, paddingHorizontal: espace.l }}>
        <Pressable onPress={onRetour}>
          <T v="sousTitre" couleur={c.encreDouce}>‹ Retour</T>
        </Pressable>
        <T v="titre" style={{ marginTop: espace.m, marginBottom: espace.m }}>
          Commentaires
        </T>
      </View>

      {commentaires === null ? (
        <ActivityIndicator style={{ marginTop: espace.xl }} />
      ) : (
        <FlatList
          data={commentaires}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ paddingHorizontal: espace.l, paddingBottom: espace.l }}
          ListEmptyComponent={
            <Vide titre="Aucun commentaire" detail="Sois le premier a repondre." />
          }
          renderItem={({ item }) => (
            <View style={{ marginBottom: espace.m }}>
              <T v="legende">{quand(item.created_at)}</T>
              <T v="corps" style={{ marginTop: 2 }}>{item.texte}</T>
              <Separateur marge={espace.m} />
            </View>
          )}
        />
      )}

      <View style={{
        flexDirection: "row", alignItems: "center",
        paddingHorizontal: espace.l, paddingTop: espace.s,
        paddingBottom: marges.bottom + espace.s,
        borderTopWidth: 1, borderTopColor: c.filetDoux,
      }}>
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
          multiline
        />
        <Pressable onPress={envoyer} disabled={envoi || !texte.trim()}>
          <Ionicons name="send" size={22}
            color={texte.trim() ? c.jaune : c.encrePale} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

/** Composer un post -- texte et resultat declare, pas encore d'image. */
function EcranComposer({ onPublie, onAnnuler }: {
  onPublie: () => void; onAnnuler: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [texte, setTexte] = React.useState("");
  const [resultat, setResultat] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [erreur, setErreur] = React.useState<string | null>(null);

  async function publier() {
    const t = texte.trim();
    if (!t) { setErreur("Ecris quelque chose avant de publier."); return; }
    setEnvoi(true);
    setErreur(null);
    try {
      const r = resultat.trim() ? Number(resultat.trim().replace(",", ".")) : undefined;
      await social.publier({ texte: t, resultatPct: Number.isFinite(r) ? r : undefined });
      onPublie();
    } catch {
      setErreur("La publication a echoue. Reessaie.");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: c.fond }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={{ flex: 1, paddingTop: marges.top + espace.m,
                     paddingHorizontal: espace.l }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between",
                       alignItems: "center", marginBottom: espace.l }}>
          <Pressable onPress={onAnnuler}>
            <T v="sousTitre" couleur={c.encreDouce}>Annuler</T>
          </Pressable>
          <T v="titre">Nouveau post</T>
          <Pressable onPress={publier} disabled={envoi}>
            <T v="sousTitre" couleur={c.jaune}>Publier</T>
          </Pressable>
        </View>

        <TextInput
          value={texte}
          onChangeText={setTexte}
          placeholder="Que veux-tu partager ?"
          placeholderTextColor={c.encrePale}
          multiline
          style={{
            minHeight: 120, backgroundColor: c.creux, borderRadius: rayon.m,
            padding: espace.m, color: c.encre, textAlignVertical: "top",
            fontSize: 16,
          }}
        />

        <T v="etiquette" style={{ marginTop: espace.l, marginBottom: espace.s }}>
          Resultat a partager (facultatif)
        </T>
        <TextInput
          value={resultat}
          onChangeText={setResultat}
          placeholder="Ex : 4,2"
          placeholderTextColor={c.encrePale}
          keyboardType="numeric"
          style={{
            backgroundColor: c.creux, borderRadius: rayon.s,
            paddingHorizontal: espace.m, paddingVertical: espace.m,
            color: c.encre, fontSize: 16,
          }}
        />
        <T v="legende" style={{ marginTop: espace.s }}>
          En pourcentage. C'est toi qui le declares : ce n'est pas verifie,
          l'application le dira clairement a cote de ton post.
        </T>

        {erreur ? (
          <T v="petit" couleur={c.perte} style={{ marginTop: espace.m }}>
            {erreur}
          </T>
        ) : null}
      </View>
    </KeyboardAvoidingView>
  );
}

/** Une carte de post dans le fil. */
function CartePost({ post, onChange, onOuvrirCommentaires }: {
  post: Post; onChange: (p: Post) => void; onOuvrirCommentaires: () => void;
}) {
  const c = useCouleurs();
  const [enCours, setEnCours] = React.useState(false);

  async function liker() {
    if (enCours) return;
    setEnCours(true);
    const avant = post;
    onChange({
      ...post, jaime_par_moi: !post.jaime_par_moi,
      likes_count: post.likes_count + (post.jaime_par_moi ? -1 : 1),
    });
    try {
      await social.basculerJaime(post.id, avant.jaime_par_moi);
    } catch {
      onChange(avant);
    } finally {
      setEnCours(false);
    }
  }

  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Avatar pseudo={post.auteur_pseudo} photoUrl={post.auteur_photo_url} />
        <View style={{ marginLeft: espace.m }}>
          <T v="sousTitre">{post.auteur_pseudo ?? "Un membre"}</T>
          <T v="legende">{quand(post.created_at)}</T>
        </View>
      </View>

      {post.texte ? (
        <T v="corps" style={{ marginTop: espace.m }}>{post.texte}</T>
      ) : null}

      {post.image_url ? (
        <Image source={{ uri: post.image_url }}
          style={{ width: "100%", height: 220, borderRadius: rayon.m,
                   marginTop: espace.m }} />
      ) : null}

      {post.resultat_pct !== null ? <BadgeResultat valeur={post.resultat_pct} /> : null}

      <View style={{ flexDirection: "row", alignItems: "center",
                     marginTop: espace.m, paddingTop: espace.m,
                     borderTopWidth: 1, borderTopColor: c.filetDoux }}>
        <Pressable onPress={liker}
          style={{ flexDirection: "row", alignItems: "center", marginRight: espace.xl }}>
          <Ionicons
            name={post.jaime_par_moi ? "heart" : "heart-outline"}
            size={20} color={post.jaime_par_moi ? c.perte : c.encreDouce} />
          <T v="petit" style={{ marginLeft: espace.s }}>{post.likes_count}</T>
        </Pressable>
        <Pressable onPress={onOuvrirCommentaires}
          style={{ flexDirection: "row", alignItems: "center" }}>
          <Ionicons name="chatbubble-outline" size={19} color={c.encreDouce} />
          <T v="petit" style={{ marginLeft: espace.s }}>{post.comments_count}</T>
        </Pressable>
      </View>
    </Carte>
  );
}

export function EcranCommunaute({ onRetour }: { onRetour: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [posts, setPosts] = React.useState<Post[] | null>(null);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [composer, setComposer] = React.useState(false);
  const [commentairesDe, setCommentairesDe] = React.useState<Post | null>(null);

  const charger = React.useCallback(async () => {
    try {
      setPosts(await social.fil());
    } catch {
      setPosts([]);
    }
  }, []);

  React.useEffect(() => { charger(); }, [charger]);

  function majPost(maj: Post) {
    setPosts((avant) => (avant ?? []).map((p) => (p.id === maj.id ? maj : p)));
  }

  if (commentairesDe) {
    return <EcranCommentaires post={commentairesDe}
      onRetour={() => setCommentairesDe(null)} />;
  }

  if (composer) {
    return (
      <EcranComposer
        onAnnuler={() => setComposer(false)}
        onPublie={() => { setComposer(false); charger(); }}
      />
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: c.fond }}>
      <View style={{ paddingTop: marges.top + espace.m, paddingHorizontal: espace.l,
                     paddingBottom: espace.m }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between",
                       alignItems: "center" }}>
          <Pressable onPress={onRetour}>
            <T v="sousTitre" couleur={c.encreDouce}>‹ Retour</T>
          </Pressable>
          <T v="titreGrand">Communaute</T>
          <Pressable onPress={() => setComposer(true)}>
            <Ionicons name="add-circle" size={28} color={c.jaune} />
          </Pressable>
        </View>
      </View>

      {posts === null ? (
        <ActivityIndicator style={{ marginTop: espace.xl }} />
      ) : (
        <FlatList
          data={posts}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{
            paddingHorizontal: espace.l,
            paddingBottom: marges.bottom + espace.xxxl,
          }}
          refreshControl={
            <RefreshControl refreshing={rafraichit} tintColor={c.jaune}
              onRefresh={async () => {
                setRafraichit(true); await charger(); setRafraichit(false);
              }} />
          }
          ListEmptyComponent={
            <Vide titre="Personne n'a encore publie"
                  detail="Sois le premier a partager quelque chose." />
          }
          renderItem={({ item }) => (
            <CartePost post={item} onChange={majPost}
              onOuvrirCommentaires={() => setCommentairesDe(item)} />
          )}
        />
      )}

      {posts !== null && posts.length === 0 ? (
        <View style={{ paddingHorizontal: espace.l }}>
          <Bouton titre="Publier le premier post" onPress={() => setComposer(true)} />
        </View>
      ) : null}
    </View>
  );
}
