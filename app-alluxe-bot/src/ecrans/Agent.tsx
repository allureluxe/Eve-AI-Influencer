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
 * CONVERSATION, PAS DICTEE (19 sept.). L'operateur : "si j'enregistre un
 * message ca marche, mais avoir une conversation ca marche pas". Le micro,
 * la reconnaissance et l'envoi fonctionnaient donc -- le defaut etait la
 * REGLE : il fallait redire "Alluxe" avant chaque phrase. Le mot de
 * reveil n'ouvre plus que l'echange ; pendant 90 s apres chaque reponse,
 * tout ce qui est dit part directement, et chaque phrase relance le
 * compte a rebours. Passe ce delai, il faut rappeler son nom -- sinon une
 * conversation tenue a cote du telephone finirait envoyee.
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
import { Message, conversation, ecouterConversation, envoyerMessage } from "../services/agent";
import {
  arreterReveilVocal, demarrerReveilVocal, reveilVocalActif, reveilVocalDisponible,
} from "../services/reveilVocal";
import { espace, rayon, TRAIT } from "../theme";
import { Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

// 800 ms : l'operateur voulait qu'il reponde "du tac au tac". Le moteur
// repond en 0,3 s -- c'est l'attente du sondage qui se voyait, des deux
// cotes (2 s ici, 2 s cote serveur avant de voir le message).
const RYTHME_MS = 800;

/**
 * LE VOCABULAIRE QU'ON SOUFFLE A LA RECONNAISSANCE.
 *
 * "Mes paroles sont mal traduites" (operateur, 19 sept.). Normal : le
 * moteur francais ne connait ni "Alluxe", ni "Bitvavo", ni la plupart
 * des cryptos. Il les remplace donc par les mots existants les plus
 * proches, et la phrase devient incomprehensible.
 *
 * `contextualStrings` les lui donne a l'avance : il les reconnait au
 * lieu de les deviner. C'est le seul moyen d'ameliorer la transcription
 * sans changer de moteur.
 */
const VOCABULAIRE = [
  "Alluxe", "Luna", "Allure", "Bitvavo",
  "Bitcoin", "Ethereum", "Solana", "Cardano", "Dogecoin", "Chainlink",
  "crypto", "cryptos", "trading", "robot", "démo", "position", "positions",
  "stop", "bénéfice", "perte", "capital", "pyramide", "étage", "renfort",
  "abonnés", "Instagram", "TikTok", "publication",
];

/** Les reglages d'ecoute, au meme endroit : ils etaient recopies a deux
 *  endroits et commencaient deja a diverger. */
function reglagesEcoute(continu: boolean) {
  return {
    lang: "fr-FR",
    interimResults: false,
    // `continuous` n'etait PAS passe au depart : la reconnaissance
    // s'arretait au premier silence et tout reposait sur la relance.
    continuous: continu,
    addsPunctuation: true,
    // Plusieurs propositions plutot qu'une : on garde celle qui contient
    // son nom (voir le gestionnaire "result"). La premiere n'est pas
    // toujours la bonne sur un mot invente.
    maxAlternatives: 3,
    contextualStrings: VOCABULAIRE,
    androidIntentOptions: {
      // Android coupe par defaut apres ~1 s de silence. 3 s ne
      // suffisaient pas non plus : le 19 sept., les phrases de
      // l'operateur arrivaient tronquees en plein milieu ("s'il te plait
      // arrete de dire" -- coupe la). Quelqu'un qui cherche ses mots
      // marque facilement 3 s de pause.
      //
      // 4,5 s. Le prix a payer est un leger delai avant la reponse quand
      // on a fini de parler ; c'est preferable a une phrase amputee, qui
      // oblige a tout recommencer.
      EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS: 4500,
      EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS: 4500,
      EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS: 2000,
    },
  };
}

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

/**
 * Distance d'edition : combien de lettres il faut changer pour passer
 * d'un mot a l'autre. "aluxe" -> "alluxe" vaut 1, "alusse" -> "alluxe"
 * vaut 2.
 *
 * Pourquoi ca remplace la liste de variantes (19 sept.) : "il entend mais
 * ne repond pas". La transcription arrivait bien, mais aucune de mes
 * variantes devinees ne tombait juste -- et j'en devinais depuis le
 * debut, faute de telephone pour essayer. Une liste ne peut pas couvrir
 * ce qu'un correcteur francais invente pour un mot qui n'existe pas ;
 * une mesure de ressemblance, si.
 */
function _distance(a: string, b: string): number {
  const precedente = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) precedente[j] = j;
  for (let i = 1; i <= a.length; i++) {
    let coinHautGauche = precedente[0];
    precedente[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const memoire = precedente[j];
      precedente[j] = Math.min(
        precedente[j] + 1,            // suppression
        precedente[j - 1] + 1,        // insertion
        coinHautGauche + (a[i - 1] === b[j - 1] ? 0 : 1), // substitution
      );
      coinHautGauche = memoire;
    }
  }
  return precedente[b.length];
}

/**
 * Replie les graphies d'un meme SON. Le correcteur francais ecrit le "x"
 * de "Alluxe" de cinq facons au moins -- x, ks, cs, ss, c -- et double
 * les consonnes au hasard. Apres ce repli, "alluxe", "alusse", "alukse"
 * et "alucse" deviennent tous "aluse" : le meme mot a l'oreille, ecrit
 * de quatre facons.
 *
 * C'est ce repli qui remplace la liste de variantes devinees. Comparer
 * les sons plutot que les lettres evite d'elargir la tolerance, ce qui
 * ferait declencher sur "alarme" ou "alerte" -- deux mots qu'il va
 * forcement prononcer en parlant du robot.
 */
function _phonetique(mot: string): string {
  return mot
    .replace(/que$/, "")
    .replace(/x|ks|cs|ss|c/g, "s")
    .replace(/(.)\1+/g, "$1");
}

/** Ce mot ressemble-t-il assez a "Alluxe" pour etre son nom ? */
function _cestSonNom(mot: string): boolean {
  const m = _normaliserMot(mot);
  // Trop court : "a", "al", "lu" declencheraient sur n'importe quoi.
  if (m.length < 4) return false;
  // Son nom commence par un A (le H de "hallux" est muet). Sans cette
  // regle, "de luxe" -- deux mots courants recolles -- passait pour son
  // nom a deux lettres pres.
  const debut = m[0] === "h" ? m.slice(1) : m;
  if (debut[0] !== "a") return false;
  const son = _phonetique(debut);
  return _distance(son, "aluse") <= 1 || _distance(son, "alus") <= 1;
}

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
    if (_cestSonNom(mots[i])) {
      index = i;
      motsConsommes = 1;
      break;
    }
    if (i + 1 < mots.length && _cestSonNom(mots[i] + mots[i + 1])) {
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
      backgroundColor: deLui ? c.jauneAplat : c.surface,
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
  // CONVERSATION OUVERTE.
  //
  // Retour de l'operateur le 19 sept. : "si j'enregistre un message ca
  // marche, mais avoir une conversation ca marche pas". La dictee
  // fonctionnait donc (micro, reconnaissance, envoi), et le defaut etait
  // ailleurs : il fallait redire "Alluxe" AVANT CHAQUE PHRASE. Ce n'est
  // pas une conversation, c'est une suite d'ordres.
  //
  // Desormais le mot de reveil n'est exige que pour OUVRIR l'echange.
  // Pendant les 90 s qui suivent chaque reponse, tout ce qui est dit part
  // directement -- comme quand on parle a quelqu'un. Passe ce delai sans
  // rien dire, il faut de nouveau l'appeler : sans cette fermeture, une
  // conversation tenue a cote du telephone finirait envoyee.
  const [conversationOuverte, setConversationOuverte] = React.useState(false);
  const ouverteJusqua = React.useRef(0);
  const DUREE_CONVERSATION_MS = 90_000;
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
    // Charge l'historique une fois, puis recoit les nouveaux messages
    // immediatement par Supabase Realtime. Le polling reste un filet de
    // securite pour les appareils/reseaux qui perdent la souscription.
    conversation().then((msgs) => {
      const derniere = [...msgs].reverse().find((m) => m.role === "assistant");
      if (derniere) derniereLue.current = derniere.id;
      setListe(msgs);
    }).catch(() => {});

    const arreterTempsReel = ecouterConversation((message) => {
      setListe((avant) => {
        if (!avant) return [message];
        if (avant.some((m) => m.id === message.id)) return avant;
        return [...avant, message].slice(-50);
      });
      if (message.role === "assistant" && message.id > derniereLue.current) {
        derniereLue.current = message.id;
        parler(message.contenu);
      }
    });

    const id = setInterval(charger, 5000);
    return () => {
      arreterTempsReel();
      clearInterval(id);
      seTaire();
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
      ExpoSpeechRecognitionModule.start(reglagesEcoute(mode === "continu"));
    } catch (err: any) {
      if (mode === "unique") setEcoute(false); else setEcouteContinue(false);
      setErreur(err?.message ?? "Impossible de demarrer l'ecoute");
    }
  }, []);

  const ecouter = React.useCallback(() => demarrerReconnaissance("unique"), [demarrerReconnaissance]);

  /** Ouvre l'echange sans avoir a prononcer son nom.
   *
   *  Filet de securite pose le 19 sept. : "il entend mais ne repond pas".
   *  Le mot de reveil reste pratique, mais il ne doit pas etre le SEUL
   *  chemin -- s'il n'est pas reconnu sur un appareil, tout le mode
   *  conversation devient inutilisable, et c'est exactement ce qui s'est
   *  passe. Un appui remplace le mot. */
  const ouvrirConversation = React.useCallback(() => {
    ouverteJusqua.current = Date.now() + DUREE_CONVERSATION_MS;
    setConversationOuverte(true);
    if (!ecouteContinueRef.current) {
      setEcouteContinue(true);
      demarrerReconnaissance("continu");
    }
    parler("Je vous ecoute, Monsieur.");
  }, [demarrerReconnaissance]);

  const basculerEcouteContinue = React.useCallback(() => {
    if (ecouteContinue) {
      setEcouteContinue(false);
      setConversationOuverte(false);
      ouverteJusqua.current = 0;
      if (modeEcouteRef.current === "continu") ExpoSpeechRecognitionModule.stop();
    } else {
      setEcouteContinue(true);
      demarrerReconnaissance("continu");
    }
  }, [ecouteContinue, demarrerReconnaissance]);

  useSpeechRecognitionEvent("result", (e) => {
    if (!e.isFinal) return;
    // `maxAlternatives: 3` rend plusieurs propositions. Sur un mot
    // invente comme "Alluxe", la premiere n'est souvent pas la bonne --
    // mais l'une des suivantes l'est. On garde celle qui contient son
    // nom ; a defaut, la premiere, comme avant.
    const propositions = (e.results ?? [])
      .map((r: any) => r?.transcript)
      .filter(Boolean) as string[];
    const transcription =
      propositions.find((t) => _apresAlluxe(t) !== null) ?? propositions[0];
    if (!transcription) return;
    setDernierEntendu(transcription);
    if (modeEcouteRef.current === "continu") {
      const apres = _apresAlluxe(transcription);
      const encoreOuverte = Date.now() < ouverteJusqua.current;

      if (apres === null && !encoreOuverte) return; // ni "Alluxe", ni echange en cours

      // Tout ce qui est dit relance le compte a rebours : on ne coupe pas
      // quelqu'un qui reflechit entre deux phrases.
      ouverteJusqua.current = Date.now() + DUREE_CONVERSATION_MS;
      setConversationOuverte(true);
      setTimeout(() => {
        if (Date.now() >= ouverteJusqua.current) setConversationOuverte(false);
      }, DUREE_CONVERSATION_MS + 500);

      const question = apres === null ? transcription : apres;
      if (question.trim()) envoyer(question.trim());
      else parler("Oui, Monsieur ?"); // il a dit son nom, sans rien derriere
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
          ExpoSpeechRecognitionModule.start(reglagesEcoute(true));
        } catch { /* le prochain "end" relancera */ }
      }, 150);
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
          {!ecouteContinue
            ? "Ecoute en continu sur cet ecran (sans reveil vocal)"
            : conversationOuverte
              ? "Je vous ecoute, Monsieur -- parlez normalement"
              : "Appelez-moi : dites \"Alluxe\""}
        </T>
        <Ionicons
          name={conversationOuverte ? "chatbubbles"
                : ecouteContinue ? "ear" : "ear-outline"}
          size={18}
          color={conversationOuverte ? c.gain
                 : ecouteContinue ? c.jaune : c.encrePale} />
      </Pressable>

      <Pressable onPress={ouvrirConversation} style={{
        flexDirection: "row", alignItems: "center", justifyContent: "center",
        gap: espace.xs,
        backgroundColor: conversationOuverte ? c.jauneAplat : c.creux,
        borderRadius: rayon.s, paddingVertical: espace.m,
        marginHorizontal: espace.l, marginBottom: espace.m,
      }}>
        <Ionicons name="mic" size={18}
                  color={conversationOuverte ? c.surJaune : c.encre} />
        <T v="petit" couleur={conversationOuverte ? c.surJaune : c.encre}>
          {conversationOuverte ? "Parlez, je vous ecoute"
                               : "Parler a Alluxe (sans dire son nom)"}
        </T>
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
            width: 44, height: 44, borderRadius: rayon.s, backgroundColor: c.jauneAplat,
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
