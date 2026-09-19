/**
 * Onglet Discussion -- ecrire au robot et recevoir ses reponses.
 *
 * REMPLACE TELEGRAM. Decision de l'operateur le 19 septembre : « je n'ai
 * plus besoin des messages Telegram [...] l'onglet Discussion, je veux
 * que ce soit ici que je reçois les messages et là où je peux écrire,
 * comme la demande rapport allure. En gros, ce que fait Telegram, tu
 * mets tout dans le mode discussion d'Alluxbot. »
 *
 * Les alertes du robot arrivaient deja dans l'application (onglet
 * Alertes, table `alluxe_bot_alertes`). Ce qui manquait etait l'autre
 * sens : pouvoir ECRIRE. C'est fait ici, avec les memes commandes que
 * Telegram comprenait -- la meme interpretation, partagee dans
 * `gold_bot/commandes.py`, et non recopiee.
 *
 * Le rapport ALLURE arrivait en fichier joint sur Telegram ; il arrive
 * ici dans la reponse et s'ouvre en plein ecran. Il ne passe par aucune
 * adresse publique : « on ne met pas les finances de quelqu'un sur le
 * web ouvert pour economiser un clic » (ecoute_telegram.py).
 */
import React from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable,
  ScrollView, TextInput, View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { Message, RACCOURCIS, ecrire, messages, rapport, suivre }
  from "../services/discussion";
import { quand } from "../services/format";
import { espace, rayon } from "../theme";
import { Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

/** Le rapport ALLURE, en plein ecran. */
function VisionneuseRapport({ html, titre, surFermeture }: {
  html: string | null; titre: string; surFermeture: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  return (
    <Modal visible animationType="slide" onRequestClose={surFermeture}>
      <View style={{ flex: 1, backgroundColor: c.fond,
                     paddingTop: marges.top }}>
        <View style={{ flexDirection: "row", alignItems: "center",
                       justifyContent: "space-between",
                       paddingHorizontal: espace.l, paddingVertical: espace.s }}>
          <T v="sousTitre" style={{ flexShrink: 1 }}>{titre}</T>
          <Pressable onPress={surFermeture} accessibilityRole="button"
                     accessibilityLabel="Fermer le rapport"
                     style={{ padding: espace.s }}>
            <Ionicons name="close" size={24} color={c.encre} />
          </Pressable>
        </View>
        {html == null ? (
          <View style={{ flex: 1, justifyContent: "center" }}>
            <Chargement />
          </View>
        ) : (
          <WebView
            originWhitelist={["*"]}
            source={{ html }}
            style={{ flex: 1, backgroundColor: c.fond }}
          />
        )}
      </View>
    </Modal>
  );
}

function Bulle({ m, surRapport }: {
  m: Message; surRapport: (m: Message) => void;
}) {
  const c = useCouleurs();
  const deLui = m.auteur === "operateur";
  // Une ALERTE du robot (achat, cloture, arret) ne se lit pas comme une
  // reponse a une question : elle arrive sans qu'on ait rien demande.
  // Un liseré sur le bord la distingue sans couper le fil en deux --
  // Telegram, lui, n'avait aucune distinction, et une alerte critique
  // s'y perdait entre deux rapports.
  const alerte = m.niveau != null;
  const grave = m.niveau === "critical" || m.niveau === "warning";
  return (
    <View style={{ alignItems: deLui ? "flex-end" : "flex-start",
                   marginBottom: espace.m }}>
      <View style={{
        maxWidth: "88%",
        backgroundColor: deLui ? c.jauneAplat : c.surface,
        borderRadius: rayon.l, paddingVertical: espace.m,
        paddingHorizontal: espace.l,
        ...(alerte ? { borderLeftWidth: 3,
                       borderLeftColor: grave ? c.perte : c.olive } : null),
      }}>
        <T v="corps" couleur={deLui ? c.surJaune : c.encre}>{m.texte}</T>

        {/* Une demande pas encore traitee : le robot passe chaque minute.
            Le dire evite de croire que le message s'est perdu. */}
        {deLui && !m.traite && (
          <View style={{ flexDirection: "row", alignItems: "center",
                         gap: 4, marginTop: espace.xs }}>
            <ActivityIndicator size="small" color={c.surJaune} />
            <T v="legende" couleur={c.surJaune}>en cours…</T>
          </View>
        )}

        {!!m.rapport_titre && (
          <Pressable
            onPress={() => surRapport(m)}
            accessibilityRole="button"
            accessibilityLabel="Ouvrir le rapport ALLURE"
            style={{ flexDirection: "row", alignItems: "center",
                     gap: espace.s, marginTop: espace.m,
                     paddingVertical: espace.s, paddingHorizontal: espace.m,
                     borderRadius: rayon.s, backgroundColor: c.creux }}
          >
            <Ionicons name="document-text-outline" size={18} color={c.encre} />
            <T v="petit" style={{ flexShrink: 1 }}>Ouvrir la page ALLURE</T>
          </Pressable>
        )}
      </View>
      <T v="legende" couleur={c.encrePale} style={{ marginTop: 2 }}>
        {quand(m.created_at)}
      </T>
    </View>
  );
}

export function EcranDiscussion() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [fil, setFil] = React.useState<Message[] | null>(null);
  const [texte, setTexte] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [erreur, setErreur] = React.useState("");
  const [ouvert, setOuvert] = React.useState<Message | null>(null);
  const [htmlOuvert, setHtmlOuvert] = React.useState<string | null>(null);
  const defilement = React.useRef<ScrollView>(null);

  const charger = React.useCallback(async () => {
    try {
      setFil(await messages());
      setErreur("");
    } catch (e: any) {
      // La table peut ne pas encore exister sur une base pas migree :
      // on le dit, au lieu d'afficher un fil vide qui laisserait croire
      // que le robot ne repond pas.
      setErreur(/does not exist/i.test(e?.message ?? "")
        ? "La conversation n'est pas encore installée côté serveur."
        : (e?.message ?? "lecture impossible"));
      setFil([]);
    }
  }, []);

  React.useEffect(() => { charger(); }, [charger]);
  // En direct : la reponse du robot doit apparaitre seule.
  React.useEffect(() => suivre(charger), [charger]);

  const envoyer = async (quoi?: string) => {
    const contenu = (quoi ?? texte).trim();
    if (!contenu || envoi) return;
    setEnvoi(true);
    try {
      await ecrire(contenu);
      setTexte("");
      await charger();
    } catch (e: any) {
      setErreur(e?.message ?? "envoi impossible");
    } finally {
      setEnvoi(false);
    }
  };

  const ouvrirRapport = async (m: Message) => {
    setOuvert(m);
    setHtmlOuvert(null);
    try { setHtmlOuvert(await rapport(m.id)); } catch { setHtmlOuvert(""); }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: c.fond }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={{ flex: 1, paddingTop: marges.top + espace.s,
                     paddingHorizontal: espace.l }}>
        <View style={{ flexDirection: "row", alignItems: "center",
                       justifyContent: "space-between", marginBottom: espace.s }}>
          <T v="titreGrand">Discussion</T>
          <Logo hauteur={40} />
        </View>

        {!!erreur && (
          <T v="petit" couleur={c.perte} style={{ marginBottom: espace.s }}>
            {erreur}
          </T>
        )}

        <ScrollView
          ref={defilement}
          style={{ flex: 1 }}
          contentContainerStyle={{ paddingBottom: espace.l }}
          onContentSizeChange={() =>
            defilement.current?.scrollToEnd({ animated: true })}
        >
          {fil === null ? (
            <Chargement />
          ) : fil.length === 0 ? (
            <Vide titre="Écris au robot"
                  detail="« rapport allure » pour la page complète, « etat » pour le point en deux lignes." />
          ) : (
            fil.map((m) => (
              <Bulle key={m.id} m={m} surRapport={ouvrirRapport} />
            ))
          )}
        </ScrollView>

        {/* Les commandes a portee de doigt : il dicte a la voix, et
            « rapport allure » mal transcrit ne serait pas compris. */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
                    style={{ flexGrow: 0, marginBottom: espace.s }}
                    contentContainerStyle={{ gap: espace.s }}>
          {RACCOURCIS.map((r) => (
            <Pressable
              key={r.texte}
              onPress={() => envoyer(r.texte)}
              accessibilityRole="button"
              accessibilityLabel={`${r.texte} — ${r.aide}`}
              style={{ paddingVertical: 6, paddingHorizontal: espace.m,
                       borderRadius: rayon.rond, backgroundColor: c.creux }}
            >
              <T v="petit" couleur={c.encreDouce}>{r.texte}</T>
            </Pressable>
          ))}
        </ScrollView>

        <View style={{ flexDirection: "row", alignItems: "flex-end",
                       gap: espace.s, paddingBottom: marges.bottom + espace.s }}>
          <TextInput
            value={texte}
            onChangeText={setTexte}
            placeholder="Écris au robot…"
            placeholderTextColor={c.encrePale}
            multiline
            onSubmitEditing={() => envoyer()}
            style={{
              flex: 1, maxHeight: 120, color: c.encre,
              backgroundColor: c.surface, borderRadius: rayon.l,
              paddingHorizontal: espace.l, paddingVertical: espace.m,
              fontSize: 15,
            }}
          />
          <Pressable
            onPress={() => envoyer()}
            disabled={!texte.trim() || envoi}
            accessibilityRole="button"
            accessibilityLabel="Envoyer"
            style={{
              width: 44, height: 44, borderRadius: rayon.s,
              alignItems: "center", justifyContent: "center",
              backgroundColor: texte.trim() ? c.jauneAplat : c.creux,
            }}
          >
            {envoi ? <ActivityIndicator size="small" color={c.surJaune} />
                   : <Ionicons name="arrow-up" size={20}
                               color={texte.trim() ? c.surJaune : c.encrePale} />}
          </Pressable>
        </View>
      </View>

      {!!ouvert && (
        <VisionneuseRapport
          html={htmlOuvert}
          titre={ouvert.rapport_titre ?? "Rapport ALLURE"}
          surFermeture={() => { setOuvert(null); setHtmlOuvert(null); }}
        />
      )}
    </KeyboardAvoidingView>
  );
}
