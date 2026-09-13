/**
 * Connexion par lien magique. Pas de mot de passe.
 *
 * POURQUOI PAS DE MOT DE PASSE
 * ----------------------------
 * Un mot de passe sur une application financiere, c'est un mot de passe
 * reutilise depuis ailleurs neuf fois sur dix. On n'en stocke aucun, on
 * n'en perd aucun, et il n'y a rien a voler dans une fuite.
 *
 * L'ecran ne dit JAMAIS si l'adresse existe deja. « Nous t'avons envoye
 * un lien » dans les deux cas : repondre « ce compte n'existe pas »
 * permettrait a n'importe qui de tester des adresses pour savoir qui
 * est inscrit.
 */

import React from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, TextInput, View }
  from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { supabase } from "../services/supabase";
import { espace, polices, rayon } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

export function EcranConnexion() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [email, setEmail] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [envoye, setEnvoye] = React.useState(false);
  const [erreur, setErreur] = React.useState<string | null>(null);

  const valide = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim());

  async function envoyer() {
    setEnvoi(true);
    setErreur(null);
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim().toLowerCase(),
      options: { emailRedirectTo: "eve://connexion" },
    });
    setEnvoi(false);

    // ON N'ANNONCE PAS L'ECHEC D'EXISTENCE. Seules les vraies pannes
    // (reseau, service) sont dites ; le reste affiche le meme ecran de
    // confirmation, qu'un compte existe ou non.
    if (error && /network|fetch|timeout|rate/i.test(error.message)) {
      setErreur(/rate/i.test(error.message)
        ? "Trop de demandes. Attends une minute."
        : "Pas de connexion. Reessaie.");
      return;
    }
    setEnvoye(true);
  }

  if (envoye) {
    return (
      <View style={{ flex: 1, backgroundColor: c.fond,
                     paddingTop: marges.top, paddingHorizontal: espace.xl,
                     justifyContent: "center" }}>
        <T v="etiquette" couleur={c.jaune}>Verifie ta boite mail</T>
        <T style={{ fontFamily: polices.titre, fontSize: 30, color: c.encre,
                    lineHeight: 38, marginTop: espace.m }}>
          Un lien de connexion est parti
        </T>
        <T v="corps" couleur={c.encreDouce}
           style={{ marginTop: espace.l, lineHeight: 25 }}>
          Ouvre le message envoye a {email.trim().toLowerCase()} et appuie
          sur le lien. Il te ramene directement ici, connecte.
        </T>
        <T v="petit" style={{ marginTop: espace.xl }}>
          Rien recu au bout de deux minutes ? Regarde dans les
          indesirables.
        </T>
        <View style={{ marginTop: espace.l }}>
          <Bouton titre="Utiliser une autre adresse" variante="discret"
                  onPress={() => { setEnvoye(false); setEmail(""); }} />
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: c.fond }}
    >
      <View style={{ flex: 1, paddingTop: marges.top,
                     paddingHorizontal: espace.xl, justifyContent: "center" }}>
        <Logo hauteur={72} />
        <T v="corps" couleur={c.encreDouce}
           style={{ marginTop: espace.l, marginBottom: espace.xxl }}>
          Les signaux d'un robot qui trade son propre argent.
        </T>

        <T v="etiquette" style={{ marginBottom: espace.s }}>
          Ton adresse e-mail
        </T>
        <TextInput
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          textContentType="emailAddress"
          placeholder="toi@exemple.fr"
          placeholderTextColor={c.encrePale}
          onSubmitEditing={() => { if (valide) envoyer(); }}
          style={{
            backgroundColor: c.surface, color: c.encre,
            borderWidth: StyleSheet.hairlineWidth, borderColor: c.filet,
            borderRadius: rayon.s, paddingHorizontal: espace.l,
            paddingVertical: espace.m + 2, fontSize: 17,
            fontFamily: polices.interface, marginBottom: espace.l,
          }}
        />

        {erreur ? (
          <T v="petit" couleur={c.perte} style={{ marginBottom: espace.m }}>
            {erreur}
          </T>
        ) : null}

        <Bouton
          titre={envoi ? "Envoi..." : "Recevoir mon lien de connexion"}
          onPress={envoyer}
          desactive={!valide || envoi}
        />

        <T v="legende" style={{ marginTop: espace.l, lineHeight: 17 }}>
          Pas de mot de passe : on t'envoie un lien a chaque connexion.
          Ton adresse ne sert qu'a ca et n'est transmise a personne.
        </T>
      </View>
    </KeyboardAvoidingView>
  );
}
