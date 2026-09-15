/**
 * Connexion, simplifiee par rapport a celle d'Allure.
 *
 * Alluxe Bot est un outil PRIVE, pour un seul utilisateur (l'operateur),
 * qui a deja un compte Allure (e-mail + mot de passe). Pas d'inscription
 * ici, pas de pseudo a resoudre : juste se connecter avec le compte qui
 * existe deja. Un compte sans le droit d'administrateur se connecte,
 * mais ne verra aucune donnee (voir la politique RLS cote base).
 */
import React from "react";
import { KeyboardAvoidingView, Platform, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { supabase } from "../services/supabase";
import { espace, polices, rayon } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

function messageErreur(brut: string): string {
  if (/network|fetch|timeout/i.test(brut)) return "Pas de connexion. Reessaie.";
  if (/invalid login credentials/i.test(brut))
    return "E-mail ou mot de passe incorrect.";
  if (/email not confirmed/i.test(brut))
    return "Confirme d'abord ton adresse (voir l'app Allure).";
  return "Quelque chose s'est mal passe. Reessaie.";
}

export function EcranConnexion() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [email, setEmail] = React.useState("");
  const [motDePasse, setMotDePasse] = React.useState("");
  const [enCours, setEnCours] = React.useState(false);
  const [erreur, setErreur] = React.useState("");

  const seConnecter = async () => {
    if (!email.trim() || !motDePasse) {
      setErreur("E-mail et mot de passe requis.");
      return;
    }
    setEnCours(true);
    setErreur("");
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(), password: motDePasse,
    });
    setEnCours(false);
    if (error) setErreur(messageErreur(error.message));
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: c.fond }}
    >
      <View style={{ flex: 1, justifyContent: "center", paddingHorizontal: espace.l,
                     paddingTop: marges.top, paddingBottom: marges.bottom }}>
        <View style={{ alignItems: "center", marginBottom: espace.xl }}>
          <Logo hauteur={64} />
          <T v="titreGrand" style={{ marginTop: espace.m }}>Alluxe Bot</T>
          <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.xs }}>
            Acces reserve
          </T>
        </View>

        <TextInput
          value={email}
          onChangeText={setEmail}
          placeholder="E-mail"
          placeholderTextColor={c.encreDouce}
          autoCapitalize="none"
          keyboardType="email-address"
          style={{
            borderWidth: 2, borderColor: c.filet, borderRadius: rayon.s,
            padding: espace.m, marginBottom: espace.s, color: c.encre,
            fontFamily: polices.interface, backgroundColor: c.surface,
          }}
        />
        <TextInput
          value={motDePasse}
          onChangeText={setMotDePasse}
          placeholder="Mot de passe"
          placeholderTextColor={c.encreDouce}
          secureTextEntry
          style={{
            borderWidth: 2, borderColor: c.filet, borderRadius: rayon.s,
            padding: espace.m, marginBottom: espace.m, color: c.encre,
            fontFamily: polices.interface, backgroundColor: c.surface,
          }}
        />
        {!!erreur && (
          <T v="petit" couleur={c.perte} style={{ marginBottom: espace.m }}>
            {erreur}
          </T>
        )}
        <Bouton titre={enCours ? "Connexion..." : "Se connecter"}
               onPress={seConnecter} desactive={enCours} />
      </View>
    </KeyboardAvoidingView>
  );
}
