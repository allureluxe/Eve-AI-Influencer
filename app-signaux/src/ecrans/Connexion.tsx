/**
 * Connexion par pseudo et mot de passe.
 *
 * DECISION DE L'OPERATEUR (13 septembre, au soir), qui remplace le lien
 * magique par e-mail d'origine. L'ecran precedent expliquait pourquoi
 * un mot de passe etait evite sur une application financiere -- ce
 * raisonnement reste vrai en soi, mais l'operateur a tranche pour la
 * simplicite : les gens s'inscrivent et se connectent tout de suite,
 * sans quitter l'application pour aller cliquer un lien dans leur
 * boite mail.
 *
 * Supabase Auth n'a pas de notion de pseudo : il identifie un compte
 * par e-mail. Le pseudo est donc resolu en e-mail cote serveur avant
 * la connexion (fonction `email_pour_pseudo`, voir la migration
 * 20260913200000) -- l'application ne lit et ne stocke jamais l'e-mail
 * d'un autre compte que le sien.
 */

import React from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, TextInput, View }
  from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { supabase } from "../services/supabase";
import { espace, polices, rayon } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

const PSEUDO_VALIDE = /^.{3,20}$/;
const EMAIL_VALIDE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function messageErreur(brut: string): string {
  if (/network|fetch|timeout/i.test(brut)) return "Pas de connexion. Reessaie.";
  if (/rate/i.test(brut)) return "Trop de tentatives. Attends une minute.";
  if (/already registered|already exists/i.test(brut))
    return "Ce pseudo ou cet e-mail est deja pris.";
  if (/invalid login credentials/i.test(brut))
    return "Pseudo ou mot de passe incorrect.";
  if (/password.*(least|character)/i.test(brut))
    return "Le mot de passe doit faire au moins 6 caracteres.";
  return "Quelque chose s'est mal passe. Reessaie.";
}

export function EcranConnexion() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [inscription, setInscription] = React.useState(false);
  const [pseudo, setPseudo] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [motDePasse, setMotDePasse] = React.useState("");
  const [enCours, setEnCours] = React.useState(false);
  const [erreur, setErreur] = React.useState<string | null>(null);

  const pseudoOk = PSEUDO_VALIDE.test(pseudo.trim());
  const emailOk = EMAIL_VALIDE.test(email.trim());
  const motDePasseOk = motDePasse.length >= 6;
  const valide = inscription
    ? pseudoOk && emailOk && motDePasseOk
    : pseudoOk && motDePasseOk;

  async function valider() {
    if (!valide || enCours) return;
    setEnCours(true);
    setErreur(null);

    if (inscription) {
      const { error } = await supabase.auth.signUp({
        email: email.trim().toLowerCase(),
        password: motDePasse,
        options: { data: { pseudo: pseudo.trim() } },
      });
      setEnCours(false);
      if (error) { setErreur(messageErreur(error.message)); return; }
      return; // signUp connecte directement (confirmation par e-mail desactivee).
    }

    // Connexion : le pseudo n'existe nulle part cote Supabase Auth,
    // il faut d'abord retrouver l'e-mail associe.
    const { data: emailTrouve, error: erreurRecherche } = await supabase
      .rpc("email_pour_pseudo", { p_pseudo: pseudo.trim() });
    if (erreurRecherche || !emailTrouve) {
      setEnCours(false);
      setErreur("Pseudo ou mot de passe incorrect.");
      return;
    }
    const { error } = await supabase.auth.signInWithPassword({
      email: emailTrouve, password: motDePasse,
    });
    setEnCours(false);
    if (error) setErreur(messageErreur(error.message));
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

        <T v="etiquette" style={{ marginBottom: espace.s }}>Pseudo</T>
        <TextInput
          value={pseudo}
          onChangeText={setPseudo}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="tonpseudo"
          placeholderTextColor={c.encrePale}
          style={styles.champ(c)}
        />

        {inscription ? (
          <>
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
              style={styles.champ(c)}
            />
            <T v="legende" style={{ marginTop: -espace.m + 4, marginBottom: espace.l }}>
              Sert seulement a recuperer ton compte si tu oublies ton
              mot de passe.
            </T>
          </>
        ) : null}

        <T v="etiquette" style={{ marginBottom: espace.s }}>Mot de passe</T>
        <TextInput
          value={motDePasse}
          onChangeText={setMotDePasse}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          textContentType={inscription ? "newPassword" : "password"}
          placeholder="********"
          placeholderTextColor={c.encrePale}
          onSubmitEditing={valider}
          style={styles.champ(c)}
        />

        {erreur ? (
          <T v="petit" couleur={c.perte} style={{ marginBottom: espace.m }}>
            {erreur}
          </T>
        ) : null}

        <Bouton
          titre={enCours ? "..." : (inscription ? "Creer mon compte" : "Me connecter")}
          onPress={valider}
          desactive={!valide || enCours}
        />

        <View style={{ marginTop: espace.l }}>
          <Bouton
            titre={inscription
              ? "J'ai deja un compte" : "Je n'ai pas de compte"}
            variante="discret"
            onPress={() => { setInscription(!inscription); setErreur(null); }}
          />
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = {
  champ: (c: ReturnType<typeof useCouleurs>) => ({
    backgroundColor: c.surface, color: c.encre,
    borderWidth: StyleSheet.hairlineWidth, borderColor: c.filet,
    borderRadius: rayon.s, paddingHorizontal: espace.l,
    paddingVertical: espace.m + 2, fontSize: 17,
    fontFamily: polices.interface, marginBottom: espace.l,
  }),
};
