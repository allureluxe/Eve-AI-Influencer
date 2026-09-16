/**
 * Messages prives -- boite de reception, comme sur Binance.
 *
 * PAS UN ONGLET NON PLUS -- meme raisonnement que Communaute.tsx : une
 * icone depuis Accueil, un ecran a part entiere avec son "‹ Retour".
 *
 * PAS DE PSEUDO A CHERCHER SOI-MEME (14 sept.) : demarrer une
 * conversation se fait depuis un post (bouton "Message" sur une carte
 * de la Communaute, a brancher plus tard) plutot que par un annuaire de
 * comptes -- eviter qu'un inconnu puisse ecrire a n'importe qui sans
 * point de contact commun est une decision de moderation, pas un
 * oubli technique.
 */

import React from "react";
import {
  ActivityIndicator, FlatList, KeyboardAvoidingView, Platform,
  Pressable, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace, rayon } from "../../theme";
import { Separateur, T, useCouleurs, Vide } from "../../composants/base";
import { social, type MessagePrive } from "../services/social";
import { supabase } from "../../services/supabase";
import { quand } from "../services/format";

interface Conversation {
  correspondant: string;
  correspondantPseudo: string | null;
  dernier: MessagePrive;
  non_lus: number;
}

/** Le fil d'une conversation avec une seule personne. */
function EcranFil({ correspondantId, pseudo, onRetour }: {
  correspondantId: string; pseudo: string | null; onRetour: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [messages, setMessages] = React.useState<MessagePrive[] | null>(null);
  const [texte, setTexte] = React.useState("");
  const [moi, setMoi] = React.useState<string | null>(null);

  const charger = React.useCallback(async () => {
    try {
      const [msgs, session] = await Promise.all([
        social.messagesAvec(correspondantId),
        supabase.auth.getSession(),
      ]);
      setMoi(session.data.session?.user?.id ?? null);
      setMessages(msgs);
      // Marquer comme lus ceux recus qui ne le sont pas encore.
      const idMoi = session.data.session?.user?.id;
      for (const m of msgs) {
        if (m.destinataire === idMoi && !m.lu_le) social.marquerLu(m.id);
      }
    } catch {
      setMessages([]);
    }
  }, [correspondantId]);

  React.useEffect(() => { charger(); }, [charger]);

  async function envoyer() {
    const t = texte.trim();
    if (!t) return;
    setTexte("");
    try {
      await social.envoyerMessage(correspondantId, t);
      await charger();
    } catch {
      // Le champ garde le texte perdu visible pour l'utilisateur au
      // prochain essai serait mieux, mais rester simple pour l'instant.
    }
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: c.fond }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={{ paddingTop: marges.top + espace.m, paddingHorizontal: espace.l,
                     flexDirection: "row", alignItems: "center" }}>
        <Pressable onPress={onRetour} style={{ marginRight: espace.m }}>
          <T v="sousTitre" couleur={c.encreDouce}>‹</T>
        </Pressable>
        <T v="titre">{pseudo ?? "Conversation"}</T>
      </View>
      <Separateur marge={espace.m} />

      {messages === null ? (
        <ActivityIndicator style={{ marginTop: espace.xl }} />
      ) : (
        <FlatList
          data={messages}
          keyExtractor={(item) => item.id}
          inverted
          contentContainerStyle={{ paddingHorizontal: espace.l, flexDirection: "column-reverse" }}
          ListEmptyComponent={
            <Vide titre="Aucun message" detail="Ecris le premier." />
          }
          renderItem={({ item }) => {
            const deMoi = item.expediteur === moi;
            return (
              <View style={{
                alignSelf: deMoi ? "flex-end" : "flex-start",
                backgroundColor: deMoi ? c.jaune : c.creux,
                borderRadius: rayon.m, paddingHorizontal: espace.m,
                paddingVertical: espace.s, marginVertical: 4,
                maxWidth: "80%",
              }}>
                <T v="corps" couleur={deMoi ? c.surJaune : c.encre}>{item.texte}</T>
                <T v="legende" couleur={deMoi ? c.olive : c.encrePale}
                   style={{ marginTop: 2 }}>
                  {quand(item.created_at)}
                </T>
              </View>
            );
          }}
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
          placeholder="Ecrire un message..."
          placeholderTextColor={c.encrePale}
          style={{
            flex: 1, backgroundColor: c.creux, borderRadius: rayon.s,
            paddingHorizontal: espace.m, paddingVertical: espace.s + 2,
            color: c.encre, marginRight: espace.s,
          }}
          multiline
        />
        <Pressable onPress={envoyer} disabled={!texte.trim()}>
          <Ionicons name="send" size={22}
            color={texte.trim() ? c.jaune : c.encrePale} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

export function EcranMessages({ onRetour }: { onRetour: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [conversations, setConversations] = React.useState<Conversation[] | null>(null);
  const [ouverte, setOuverte] = React.useState<Conversation | null>(null);

  const charger = React.useCallback(async () => {
    try {
      const brut = await social.conversations();
      // Le pseudo de chaque correspondant : via profils_publics, la
      // seule vue qui rend un pseudo autre que le sien -- voir la
      // migration `20260914183000_profils_publics.sql`.
      const ids = brut.map((c) => c.correspondant);
      const { data: profils } = ids.length
        ? await supabase.from("profils_publics").select("id, pseudo").in("id", ids)
        : { data: [] as { id: string; pseudo: string | null }[] };
      const pseudos = new Map((profils ?? []).map((p) => [p.id, p.pseudo]));
      setConversations(brut.map((c) => ({
        ...c, correspondantPseudo: pseudos.get(c.correspondant) ?? null,
      })));
    } catch {
      setConversations([]);
    }
  }, []);

  React.useEffect(() => { charger(); }, [charger]);

  if (ouverte) {
    return (
      <EcranFil
        correspondantId={ouverte.correspondant}
        pseudo={ouverte.correspondantPseudo}
        onRetour={() => { setOuverte(null); charger(); }}
      />
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: c.fond }}>
      <View style={{ paddingTop: marges.top + espace.m, paddingHorizontal: espace.l,
                     paddingBottom: espace.m }}>
        <Pressable onPress={onRetour}>
          <T v="sousTitre" couleur={c.encreDouce}>‹ Retour</T>
        </Pressable>
        <T v="titreGrand" style={{ marginTop: espace.m }}>Messages</T>
      </View>

      {conversations === null ? (
        <ActivityIndicator style={{ marginTop: espace.xl }} />
      ) : (
        <FlatList
          data={conversations}
          keyExtractor={(item) => item.correspondant}
          contentContainerStyle={{ paddingHorizontal: espace.l }}
          ListEmptyComponent={
            <Vide titre="Aucun message"
                  detail="Les conversations demarrees depuis un post apparaitront ici." />
          }
          renderItem={({ item }) => (
            <Pressable onPress={() => setOuverte(item)}
              style={{ paddingVertical: espace.m }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <T v="sousTitre">{item.correspondantPseudo ?? "Un membre"}</T>
                {item.non_lus > 0 ? (
                  <View style={{ backgroundColor: c.jaune, borderRadius: rayon.rond,
                                 minWidth: 20, height: 20, alignItems: "center",
                                 justifyContent: "center", paddingHorizontal: 5 }}>
                    <T v="legende" couleur={c.surJaune}>{item.non_lus}</T>
                  </View>
                ) : null}
              </View>
              <T v="petit" couleur={c.encreDouce} numberOfLines={1} style={{ marginTop: 2 }}>
                {item.dernier.texte}
              </T>
              <Separateur marge={espace.m} />
            </Pressable>
          )}
        />
      )}
    </View>
  );
}
