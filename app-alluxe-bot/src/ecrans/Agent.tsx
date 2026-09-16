/**
 * Onglet Agent -- Alluxe, l'assistant personnel.
 *
 * PREMIERE VERSION (16 sept.), VOLONTAIREMENT LIMITEE A LA LECTURE.
 * Alluxe repond en lisant l'etat du robot, les alertes et Luna (voir
 * ops/agent_alluxe.py) -- il ne peut RIEN changer pour l'instant. Un
 * pouvoir d'action (redemarrer le robot, changer un reglage) est une
 * decision separee, a prendre explicitement plus tard.
 *
 * REVEIL VOCAL AJOUTE (2e passage, meme soir) : dire "Alluxe" ouvre
 * l'application (ServiceReveilVocal.kt, Porcupine en arriere-plan) et
 * cet ecran lance alors tout seul l'ecoute (expo-speech-recognition) --
 * la question est transcrite, envoyee, et la reponse lue a voix haute
 * (expo-speech). Un bouton micro permet aussi de dicter a la demande,
 * sans etre passe par le mot de reveil. AUCUN TELEPHONE POUR TESTER LE
 * REVEIL EN CONDITIONS REELLES -- le code compile et suit la
 * documentation Porcupine/expo-speech-recognition, mais seul un essai
 * reel sur l'appareil de l'operateur confirmera que ca marche.
 *
 * Poll toutes les 2 s tant que l'ecran est ouvert (comme Luna/Alertes),
 * pas de Supabase Realtime : aucune autre partie de l'app ne l'utilise
 * encore, inutile d'introduire un mecanisme de plus pour ce premier
 * passage.
 */
import React from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { useRoute } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Speech from "expo-speech";
import {
  ExpoSpeechRecognitionModule, useSpeechRecognitionEvent,
} from "expo-speech-recognition";
import { Ionicons } from "@expo/vector-icons";
import { Message, conversation, envoyerMessage } from "../services/agent";
import {
  arreterReveilVocal, demarrerReveilVocal, reveilVocalActif, reveilVocalDisponible,
} from "../services/reveilVocal";
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

/** Bandeau discret pour activer/desactiver le reveil vocal en arriere-plan. */
function BandeauReveilVocal() {
  const c = useCouleurs();
  const [actif, setActif] = React.useState<boolean | null>(null);
  const [enCours, setEnCours] = React.useState(false);

  React.useEffect(() => {
    if (!reveilVocalDisponible) { setActif(false); return; }
    reveilVocalActif().then(setActif);
  }, []);

  if (!reveilVocalDisponible) {
    return (
      <T v="legende" style={{ paddingHorizontal: espace.l, marginBottom: espace.s }}>
        Reveil vocal : indisponible sur cet appareil.
      </T>
    );
  }
  if (actif === null) return null;

  const basculer = async () => {
    setEnCours(true);
    try {
      if (actif) { await arreterReveilVocal(); setActif(false); }
      else { await demarrerReveilVocal(); setActif(true); }
    } catch {
      // Le service natif journalise deja la vraie cause (cle/modele absents).
    } finally {
      setEnCours(false);
    }
  };

  return (
    <Pressable onPress={basculer} disabled={enCours} style={{
      flexDirection: "row", alignItems: "center", justifyContent: "space-between",
      backgroundColor: c.creux, borderRadius: rayon.s,
      paddingVertical: espace.s, paddingHorizontal: espace.m,
      marginHorizontal: espace.l, marginBottom: espace.m,
    }}>
      <T v="petit">
        Reveil vocal ("Alluxe") : {actif ? "actif" : "coupe"}
      </T>
      <Ionicons name={actif ? "mic" : "mic-off-outline"}
                size={18} color={actif ? c.gain : c.encrePale} />
    </Pressable>
  );
}

export function EcranAgent() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const route = useRoute<any>();
  const [liste, setListe] = React.useState<Message[] | null>(null);
  const [texte, setTexte] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [ecoute, setEcoute] = React.useState(false);
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

  const envoyer = React.useCallback(async (contenu: string) => {
    if (!contenu.trim() || envoi) return;
    setEnvoi(true);
    setTexte("");
    try {
      await envoyerMessage(contenu.trim());
      await charger();
    } catch (err: any) {
      setErreur(err?.message ?? "Impossible d'envoyer le message");
    } finally {
      setEnvoi(false);
    }
  }, [envoi, charger]);

  const surEnvoyer = () => envoyer(texte);

  const ecouter = React.useCallback(async () => {
    try {
      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!permission.granted) {
        setErreur("Micro refuse -- autorise-le dans les reglages du telephone.");
        return;
      }
      setEcoute(true);
      ExpoSpeechRecognitionModule.start({ lang: "fr-FR", interimResults: false });
    } catch (err: any) {
      setEcoute(false);
      setErreur(err?.message ?? "Impossible de demarrer l'ecoute");
    }
  }, []);

  useSpeechRecognitionEvent("result", (e) => {
    const transcription = e.results[0]?.transcript;
    if (e.isFinal && transcription) {
      setTexte("");
      envoyer(transcription);
    }
  });
  useSpeechRecognitionEvent("end", () => setEcoute(false));
  useSpeechRecognitionEvent("error", (e) => {
    setEcoute(false);
    if (e.error !== "no-speech" && e.error !== "aborted") {
      setErreur(`Ecoute : ${e.message || e.error}`);
    }
  });

  // Ouvert via le reveil vocal ("alluxebot://reveil", voir App.tsx) :
  // lance l'ecoute tout seul, une seule fois par ouverture.
  const deriveDuReveil = route?.params?.autoEcoute === true;
  React.useEffect(() => {
    if (deriveDuReveil) ecouter();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deriveDuReveil, route?.params?.horodatage]);

  return (
    <View style={{ flex: 1, backgroundColor: c.fond, paddingTop: marges.top + espace.s }}>
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between", marginBottom: espace.m,
                     paddingHorizontal: espace.l }}>
        <T v="titreGrand">Alluxe</T>
        <Logo hauteur={40} />
      </View>

      <BandeauReveilVocal />

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
          placeholder={ecoute ? "Je t'ecoute..." : "Ecris, ou appuie sur le micro..."}
          placeholderTextColor={c.encrePale}
          multiline
          editable={!ecoute}
          style={{
            flex: 1, borderWidth: TRAIT, borderColor: c.filet, borderRadius: rayon.s,
            padding: espace.m, minHeight: 44, maxHeight: 120, color: c.encre,
            marginRight: espace.s, textAlignVertical: "top",
            backgroundColor: ecoute ? c.creux : "transparent",
          }}
        />
        <Pressable
          onPress={ecoute ? () => ExpoSpeechRecognitionModule.stop() : ecouter}
          style={{
            width: 44, height: 44, borderRadius: rayon.s,
            backgroundColor: ecoute ? c.perte : c.creux,
            alignItems: "center", justifyContent: "center", marginRight: espace.s,
          }}
        >
          <Ionicons name={ecoute ? "stop" : "mic-outline"} size={20}
                    color={ecoute ? "#fff" : c.encre} />
        </Pressable>
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
