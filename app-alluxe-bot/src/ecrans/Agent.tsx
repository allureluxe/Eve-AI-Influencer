/**
 * Onglet Agent -- Alluxe, l'assistant personnel.
 *
 * PREMIERE VERSION (16 sept.), VOLONTAIREMENT LIMITEE A LA LECTURE.
 * Alluxe repond en lisant l'etat du robot, les alertes et Luna (voir
 * ops/agent_alluxe.py) -- il ne peut RIEN changer pour l'instant. Un
 * pouvoir d'action (redemarrer le robot, changer un reglage) est une
 * decision separee, a prendre explicitement plus tard.
 *
 * Vraie conversation vocale complete (reveil au mot "Alluxe" + ecoute
 * en continu) PAS FAITE ici -- ca demanderait une detection de mot de
 * reveil qui tourne meme appli fermee (Picovoice ou equivalent),
 * chantier a part entiere avec ses propres coibts/permissions. Ce qui
 * EST fait : un chat texte (le clavier du telephone a deja un micro
 * pour dicter), et Alluxe LIT sa reponse a voix haute automatiquement
 * (expo-speech, sur l'appareil, gratuit) -- la moitie "vocale" qui ne
 * demande aucune nouvelle infrastructure.
 *
 * Poll toutes les 2 s tant que l'ecran est ouvert (comme Luna/Alertes),
 * pas de Supabase Realtime : aucune autre partie de l'app ne l'utilise
 * encore, inutile d'introduire un mecanisme de plus pour ce premier
 * passage.
 */
import React from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Speech from "expo-speech";
import { Ionicons } from "@expo/vector-icons";
import { Message, conversation, envoyerMessage } from "../services/agent";
import { espace, rayon, TRAIT } from "../theme";
import { Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

const RYTHME_MS = 2_000;

function Bulle({ m }: { m: Message }) {
  const c = useCouleurs();
  const deLui = m.role === "user";
  return (
    <View style={{
      alignSelf: deLui ? "flex-end" : "flex-start",
      backgroundColor: deLui ? c.jaune : c.surface,
      borderRadius: rayon.l, borderBottomRightRadius: deLui ? rayon.s : rayon.l,
      borderBottomLeftRadius: deLui ? rayon.l : rayon.s,
      paddingVertical: espace.m, paddingHorizontal: espace.l,
      marginBottom: espace.s, maxWidth: "85%",
    }}>
      <T v="corps" couleur={deLui ? c.surJaune : c.encre}>{m.contenu}</T>
    </View>
  );
}

export function EcranAgent() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [liste, setListe] = React.useState<Message[] | null>(null);
  const [texte, setTexte] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [erreur, setErreur] = React.useState("");
  const derniereLue = React.useRef<number>(0);
  const scrollRef = React.useRef<ScrollView>(null);

  const charger = React.useCallback(async () => {
    try {
      const msgs = await conversation();
      setListe(msgs);
      setErreur("");
      // Lit a voix haute la derniere reponse d'Alluxe, une seule fois.
      const derniere = [...msgs].reverse().find((m) => m.role === "assistant");
      if (derniere && derniere.id > derniereLue.current) {
        derniereLue.current = derniere.id;
        if (msgs.length > 0) {
          Speech.speak(derniere.contenu, { language: "fr-FR" });
        }
      }
    } catch (err: any) {
      setErreur(err?.message ?? "Erreur de chargement");
    }
  }, []);

  React.useEffect(() => {
    // Au tout premier chargement, ne pas parler ce qui a deja ete dit
    // avant l'ouverture de l'ecran -- seulement ce qui arrive apres.
    conversation().then((msgs) => {
      const derniere = [...msgs].reverse().find((m) => m.role === "assistant");
      if (derniere) derniereLue.current = derniere.id;
      setListe(msgs);
    }).catch(() => {});
    const id = setInterval(charger, RYTHME_MS);
    return () => { clearInterval(id); Speech.stop(); };
  }, [charger]);

  const surEnvoyer = async () => {
    if (!texte.trim() || envoi) return;
    setEnvoi(true);
    const contenu = texte.trim();
    setTexte("");
    try {
      await envoyerMessage(contenu);
      await charger();
    } catch (err: any) {
      setErreur(err?.message ?? "Impossible d'envoyer le message");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.fond, paddingTop: marges.top + espace.s }}>
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between", marginBottom: espace.m,
                     paddingHorizontal: espace.l }}>
        <T v="titreGrand">Alluxe</T>
        <Logo hauteur={40} />
      </View>

      {!!erreur && (
        <T v="petit" couleur={c.perte} style={{ marginBottom: espace.m, paddingHorizontal: espace.l }}>
          {erreur}
        </T>
      )}

      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: espace.l, paddingBottom: espace.l }}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        {liste === null ? (
          <Chargement />
        ) : liste.length === 0 ? (
          <Vide titre="Dis bonjour a Alluxe"
                detail="Il peut te donner l'etat du robot, les alertes et Luna." />
        ) : (
          liste.map((m) => <Bulle key={m.id} m={m} />)
        )}
      </ScrollView>

      <View style={{
        flexDirection: "row", alignItems: "flex-end",
        paddingHorizontal: espace.l, paddingBottom: marges.bottom + espace.m,
        paddingTop: espace.s, borderTopWidth: TRAIT, borderTopColor: c.filetDoux,
      }}>
        <TextInput
          value={texte}
          onChangeText={setTexte}
          placeholder="Ecris (ou dicte avec le micro du clavier)..."
          placeholderTextColor={c.encrePale}
          multiline
          style={{
            flex: 1, borderWidth: TRAIT, borderColor: c.filet, borderRadius: rayon.s,
            padding: espace.m, minHeight: 44, maxHeight: 120, color: c.encre,
            marginRight: espace.s, textAlignVertical: "top",
          }}
        />
        <Pressable
          onPress={surEnvoyer}
          disabled={envoi || !texte.trim()}
          style={{
            width: 44, height: 44, borderRadius: rayon.s, backgroundColor: c.jaune,
            alignItems: "center", justifyContent: "center",
            opacity: envoi || !texte.trim() ? 0.4 : 1,
          }}
        >
          <Ionicons name="arrow-up" size={20} color={c.surJaune} />
        </Pressable>
      </View>
    </View>
  );
}
