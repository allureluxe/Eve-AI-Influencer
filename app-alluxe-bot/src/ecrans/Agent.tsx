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
 * sans etre passe par le mot de reveil.
 *
 * ECOUTE EN CONTINU AJOUTEE (18 sept.) : repli gratuit au reveil vocal
 * pour l'operateur qui n'a pas pu creer de compte Picovoice (leur
 * inscription exige un e-mail "professionnel", refuse Gmail/Yahoo/
 * Outlook -- aucun frais, juste un mur d'inscription). Sans Porcupine,
 * pas d'ecoute possible appli fermee -- mais tant que cet ecran est
 * OUVERT, un bouton bascule une ecoute en boucle (expo-speech-
 * recognition, deja utilise pour la dictee) qui ne reagit que si la
 * phrase reconnue contient "Alluxe" (variantes phonetiques tolerees,
 * voir `_apresAlluxe`) -- tout le reste est ignore, jamais envoye. Dire
 * "Alluxe, [question]" en une seule phrase.
 *
 * AUCUN TELEPHONE POUR TESTER NI L'UN NI L'AUTRE EN CONDITIONS REELLES
 * -- le code compile et suit la documentation Porcupine/expo-speech-
 * recognition, mais seul un essai reel sur l'appareil de l'operateur
 * confirmera que ca marche, et la liste de variantes phonetiques de
 * "Alluxe" ci-dessous devra probablement s'affiner sur ce qu'il
 * entendra vraiment reconnu.
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
import { parler, seTaire } from "../services/voix";
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

// Variantes plausibles de ce que la reconnaissance vocale peut transcrire
// pour "Alluxe" -- un mot invente, donc pas dans son dictionnaire. Liste
// a affiner une fois de vrais essais faits sur l'appareil de l'operateur.
const VARIANTES_ALLUXE = [
  "alluxe", "aluxe", "allux", "alux", "alloxe", "aluxes", "alluxes", "aluxx",
  // Ce qu'un correcteur FRANCAIS propose pour un mot qu'il ne connait
  // pas : il le rapproche de mots existants. Liste elargie le 19 sept.
  // apres "l'ecoute en continu ne fonctionne toujours pas" -- la
  // transcription reelle s'affiche maintenant a l'ecran (voir
  // `dernierEntendu`), ce qui permettra de completer cette liste avec ce
  // que le telephone entend VRAIMENT, au lieu de deviner.
  "aluxe", "alukse", "aluxie", "alusse", "aluc", "alucse", "halux",
  "haluxe", "allukse", "alusque", "aluxque", "alluc", "alouxe", "aloux",
];

function _normaliserMot(mot: string): string {
  return mot
    .normalize("NFD").replace(/[̀-ͯ]/g, "") // enleve les accents
    .toLowerCase().replace(/[^a-z]/g, "");
}

/**
 * Si la phrase reconnue contient "Alluxe" (ou une variante proche), rend
 * ce qui suit ce mot (peut etre une chaine vide si seul le mot a ete dit).
 * Rend `null` si le mot de reveil n'apparait pas du tout -- la phrase est
 * alors ignoree, jamais envoyee a l'agent.
 */
function _apresAlluxe(transcription: string): string | null {
  const mots = transcription.split(/\s+/).filter(Boolean);

  // "Alluxe" n'existe pas en francais : la reconnaissance le rend tres
  // souvent en DEUX mots -- "a luxe", "à lux", "al ux". Chercher un mot
  // entier, un par un, ne pouvait alors JAMAIS aboutir, et la phrase
  // etait ignoree en silence. C'est la cause la plus probable du
  // "l'ecoute en continu ne fonctionne pas" du 19 sept.
  //
  // On teste donc chaque mot ET chaque paire de mots consecutifs
  // recollee, puis on repart apres le dernier mot consomme.
  let index = -1;
  let motsConsommes = 1;
  for (let i = 0; i < mots.length; i++) {
    if (VARIANTES_ALLUXE.includes(_normaliserMot(mots[i]))) {
      index = i;
      motsConsommes = 1;
      break;
    }
    if (i + 1 < mots.length
        && VARIANTES_ALLUXE.includes(_normaliserMot(mots[i] + mots[i + 1]))) {
      index = i;
      motsConsommes = 2;
      break;
    }
  }
  if (index === -1) return null;
  return mots.slice(index + motsConsommes).join(" ").trim();
}

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
  // Ce que le telephone a VRAIMENT transcrit, affiche a l'ecran.
  // Sans ca, une phrase ignoree (mot de reveil non reconnu) ne
  // laissait aucune trace : ni Monsieur ni moi ne pouvions savoir
  // pourquoi "ca ne marche pas".
  const [dernierEntendu, setDernierEntendu] = React.useState("");
  const [ecoute, setEcoute] = React.useState(false);
  const [ecouteContinue, setEcouteContinue] = React.useState(false);
  const [erreur, setErreur] = React.useState("");
  const derniereLue = React.useRef<number>(0);
  const scrollRef = React.useRef<ScrollView>(null);
  // Quel mode a demarre la reconnaissance EN COURS -- necessaire car les
  // evenements "result"/"end" sont partages entre la dictee ponctuelle
  // (bouton micro / reveil Picovoice) et l'ecoute en continu, qui ne se
  // comportent pas pareil (l'une envoie tout, l'autre filtre sur "Alluxe").
  const modeEcouteRef = React.useRef<"unique" | "continu" | null>(null);
  const ecouteContinueRef = React.useRef(false);
  React.useEffect(() => { ecouteContinueRef.current = ecouteContinue; }, [ecouteContinue]);

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
          parler(derniere.contenu);
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
    return () => {
      clearInterval(id);
      seTaire();
      // Coupe le micro en quittant l'ecran -- sinon l'ecoute en continu
      // (si active) continuerait en arriere-plan sans que rien ne le
      // montre, ce qu'on ne veut jamais.
      ecouteContinueRef.current = false;
      ExpoSpeechRecognitionModule.stop();
    };
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

  const demarrerReconnaissance = React.useCallback(async (mode: "unique" | "continu") => {
    try {
      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!permission.granted) {
        setErreur("Micro refuse -- autorise-le dans les reglages du telephone.");
        if (mode === "continu") setEcouteContinue(false);
        return;
      }
      modeEcouteRef.current = mode;
      if (mode === "unique") setEcoute(true);
      ExpoSpeechRecognitionModule.start({
        lang: "fr-FR",
        interimResults: false,
        // `continuous` n'etait PAS passe : la reconnaissance s'arretait au
        // premier silence et tout reposait sur la relance dans "end".
        continuous: mode === "continu",
        androidIntentOptions: {
          // Sans ca, Android coupe apres ~1 s de silence : le temps de
          // dire "Alluxe" puis de formuler sa question, c'est deja fini.
          EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS: 3000,
          EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS: 3000,
        },
      });
    } catch (err: any) {
      if (mode === "unique") setEcoute(false); else setEcouteContinue(false);
      setErreur(err?.message ?? "Impossible de demarrer l'ecoute");
    }
  }, []);

  const ecouter = React.useCallback(() => demarrerReconnaissance("unique"), [demarrerReconnaissance]);

  const basculerEcouteContinue = React.useCallback(() => {
    if (ecouteContinue) {
      setEcouteContinue(false);
      if (modeEcouteRef.current === "continu") ExpoSpeechRecognitionModule.stop();
    } else {
      setEcouteContinue(true);
      demarrerReconnaissance("continu");
    }
  }, [ecouteContinue, demarrerReconnaissance]);

  useSpeechRecognitionEvent("result", (e) => {
    const transcription = e.results[0]?.transcript;
    if (!e.isFinal || !transcription) return;
    setDernierEntendu(transcription);
    if (modeEcouteRef.current === "continu") {
      const question = _apresAlluxe(transcription);
      if (question === null) return; // pas de "Alluxe" entendu -- ignore, jamais envoye
      if (question) envoyer(question);
      else parler("Oui, Monsieur ?"); // mot seul, sans question derriere
      return;
    }
    setTexte("");
    envoyer(transcription);
  });
  useSpeechRecognitionEvent("end", () => {
    if (modeEcouteRef.current === "continu" && ecouteContinueRef.current) {
      // Boucle : la reconnaissance s'arrete seule apres chaque silence,
      // meme avec continuous:true sur certaines versions d'Android. Tant
      // que l'operateur n'a pas coupe le bouton, on relance.
      //
      // AVEC UN DELAI, et dans un try : relancer dans la foulee donne un
      // ERROR_RECOGNIZER_BUSY sur Android, dont l'erreur remontait dans
      // le gestionnaire "error" et COUPAIT l'ecoute continue -- le bouton
      // se desactivait tout seul au bout de quelques secondes.
      setTimeout(() => {
        if (!ecouteContinueRef.current) return;
        try {
          ExpoSpeechRecognitionModule.start({
            lang: "fr-FR", interimResults: false, continuous: true,
            androidIntentOptions: {
              EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS: 3000,
              EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS: 3000,
            },
          });
        } catch { /* le prochain "end" relancera */ }
      }, 400);
      return;
    }
    setEcoute(false);
  });
  useSpeechRecognitionEvent("error", (e) => {
    const enContinu = modeEcouteRef.current === "continu";
    if (e.error === "no-speech" || e.error === "aborted") {
      // Frequent et normal en ecoute continue (silence entre deux phrases) :
      // le gestionnaire "end" se charge deja de relancer, rien a signaler.
      if (!enContinu) setEcoute(false);
      return;
    }
    setEcoute(false);
    // "busy" et "network" sont passagers : couper l'ecoute continue
    // dessus, c'est l'eteindre toute seule au bout de quelques secondes.
    const passagere = ["busy", "network", "client", "no-match"]
      .some((m) => String(e.error || "").includes(m));
    if (enContinu && !passagere) setEcouteContinue(false);
    setErreur(`Ecoute : ${e.message || e.error}`);
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
      <Pressable onPress={basculerEcouteContinue} style={{
        flexDirection: "row", alignItems: "center", justifyContent: "space-between",
        backgroundColor: c.creux, borderRadius: rayon.s,
        paddingVertical: espace.s, paddingHorizontal: espace.m,
        marginHorizontal: espace.l, marginBottom: espace.m,
      }}>
        <T v="petit" style={{ flex: 1, marginRight: espace.s }}>
          {ecouteContinue
            ? "Ecoute en continu : active -- dis \"Alluxe, ...\""
            : "Ecoute en continu sur cet ecran (sans reveil vocal)"}
        </T>
        <Ionicons name={ecouteContinue ? "ear" : "ear-outline"}
                  size={18} color={ecouteContinue ? c.gain : c.encrePale} />
      </Pressable>

      {/* CE QUE LE TELEPHONE A VRAIMENT ENTENDU.
          Tant que ca n'etait pas affiche, une phrase ignoree parce que le
          mot de reveil n'etait pas reconnu ne laissait aucune trace : de
          l'exterieur, "ca ne marche pas". Maintenant on voit la
          transcription, donc on sait s'il faut corriger l'oreille ou la
          liste des variantes. */}
      {ecouteContinue && !!dernierEntendu && (
        <T v="petit" couleur={c.encreDouce}
           style={{ marginBottom: espace.m, paddingHorizontal: espace.l }}>
          entendu : « {dernierEntendu} »
        </T>
      )}

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
          placeholder={
            ecouteContinue ? "Ecoute en continu -- dis \"Alluxe, ...\""
              : ecoute ? "Je t'ecoute..." : "Ecris, ou appuie sur le micro..."
          }
          placeholderTextColor={c.encrePale}
          multiline
          editable={!ecoute && !ecouteContinue}
          style={{
            flex: 1, borderWidth: TRAIT, borderColor: c.filet, borderRadius: rayon.s,
            padding: espace.m, minHeight: 44, maxHeight: 120, color: c.encre,
            marginRight: espace.s, textAlignVertical: "top",
            backgroundColor: (ecoute || ecouteContinue) ? c.creux : "transparent",
          }}
        />
        <Pressable
          onPress={ecoute ? () => ExpoSpeechRecognitionModule.stop() : ecouter}
          disabled={ecouteContinue}
          style={{
            width: 44, height: 44, borderRadius: rayon.s,
            backgroundColor: ecoute ? c.perte : c.creux,
            alignItems: "center", justifyContent: "center", marginRight: espace.s,
            opacity: ecouteContinue ? 0.4 : 1,
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
