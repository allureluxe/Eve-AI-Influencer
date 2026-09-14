/**
 * Connexion par pseudo et mot de passe, inscription verifiee par e-mail.
 *
 * DECISION DE L'OPERATEUR (13 septembre, tard le soir), qui remplace le
 * lien magique par e-mail d'origine. Deux volontes, prises l'une apres
 * l'autre :
 *  1. pseudo + mot de passe plutot qu'un lien a chaque connexion --
 *     la CONNEXION ne quitte jamais l'application ;
 *  2. l'e-mail doit quand meme etre VERIFIE avant le premier acces --
 *     un compte non confirme ne peut pas se connecter, meme avec le
 *     bon mot de passe.
 *
 * Le compromis : `signUp` cree le compte mais AUCUNE session tant que
 * le lien de confirmation (envoye par Supabase) n'a pas ete ouvert.
 * L'ouverture de ce lien est geree dans App.tsx (schema `allure://`).
 *
 * Supabase Auth n'a pas de notion de pseudo : il identifie un compte
 * par e-mail. Le pseudo est resolu en e-mail cote serveur pour la
 * connexion (fonction `email_pour_pseudo`, migration 20260913200000)
 * -- l'application ne lit et ne stocke jamais l'e-mail d'un autre
 * compte que le sien.
 */

import React from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
        TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as WebBrowser from "expo-web-browser";
import { Ionicons } from "@expo/vector-icons";
import { supabase } from "../services/supabase";
import { espace, polices, rayon } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

const PSEUDO_VALIDE = /^.{3,20}$/;
const EMAIL_VALIDE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const NOM_VALIDE = /^.{2,40}$/;

function messageErreur(brut: string): string {
  if (/network|fetch|timeout/i.test(brut)) return "Pas de connexion. Reessaie.";
  if (/rate/i.test(brut)) return "Trop de tentatives. Attends une minute.";
  if (/already registered|already exists/i.test(brut))
    return "Ce pseudo ou cet e-mail est deja pris.";
  if (/email not confirmed/i.test(brut))
    return "Confirme d'abord ton adresse : regarde le lien recu par e-mail.";
  if (/invalid login credentials/i.test(brut))
    return "Pseudo ou mot de passe incorrect.";
  if (/password.*(least|character)/i.test(brut))
    return "Le mot de passe doit faire au moins 6 caracteres.";
  return "Quelque chose s'est mal passe. Reessaie.";
}

/**
 * Google et Facebook, via l'OAuth deja gere par Supabase Auth --
 * Instagram n'offre pas ce type de connexion pour une application
 * comme celle-ci (retour reel, 14 sept.).
 *
 * INACTIF TANT QUE LES FOURNISSEURS NE SONT PAS CONFIGURES cote
 * Supabase (Authentication > Providers, avec un identifiant Google/
 * Facebook cree par l'operateur -- lui seul peut creer ces acces).
 * L'appel est deja le bon : une fois les fournisseurs actives, ces
 * boutons fonctionnent sans toucher au code de l'application.
 */
async function connexionOAuth(
  fournisseur: "google" | "facebook",
): Promise<string | null> {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: fournisseur,
    options: { redirectTo: "allure://connexion", skipBrowserRedirect: true },
  });
  if (error || !data?.url) {
    if (/provider is not enabled/i.test(error?.message ?? "")) {
      return "Cette connexion n'est pas encore activee.";
    }
    return messageErreur(error?.message ?? "");
  }
  const resultat = await WebBrowser.openAuthSessionAsync(data.url, "allure://connexion");
  if (resultat.type !== "success" || !resultat.url) return null;
  const brut = resultat.url.split("#")[1] ?? resultat.url.split("?")[1] ?? "";
  const params = new URLSearchParams(brut);
  const access_token = params.get("access_token");
  const refresh_token = params.get("refresh_token");
  if (access_token && refresh_token) {
    await supabase.auth.setSession({ access_token, refresh_token });
  }
  return null;
}

export function EcranConnexion() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [inscription, setInscription] = React.useState(false);
  const [enAttenteDeConfirmation, setEnAttenteDeConfirmation] = React.useState(false);

  const [pseudo, setPseudo] = React.useState("");
  const [nom, setNom] = React.useState("");
  const [prenom, setPrenom] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [telephone, setTelephone] = React.useState("");
  const [age, setAge] = React.useState("");
  const [adresse, setAdresse] = React.useState("");
  const [sexe, setSexe] = React.useState<"homme" | "femme" | "non precise">("non precise");
  const [motDePasse, setMotDePasse] = React.useState("");
  const [enCours, setEnCours] = React.useState(false);
  const [erreur, setErreur] = React.useState<string | null>(null);
  const [enCoursOAuth, setEnCoursOAuth] = React.useState<"google" | "facebook" | null>(null);

  const pseudoOk = PSEUDO_VALIDE.test(pseudo.trim());
  const emailOk = EMAIL_VALIDE.test(email.trim());
  const motDePasseOk = motDePasse.length >= 6;
  const nomOk = !inscription || NOM_VALIDE.test(nom.trim());
  const prenomOk = !inscription || NOM_VALIDE.test(prenom.trim());
  const valide = inscription
    ? pseudoOk && emailOk && motDePasseOk && nomOk && prenomOk
    : pseudoOk && motDePasseOk;

  async function valider() {
    if (!valide || enCours) return;
    setEnCours(true);
    setErreur(null);

    // TOUT est enveloppe, et setEnCours(false) part dans un `finally`.
    // Sans ca, la moindre exception inattendue (reseau coupe en plein
    // appel, reponse malformee...) laissait le bouton bloque sur "..."
    // pour toujours -- observe en reel le 13 sept. : "le bouton connexion
    // reste bloque". Le clic suivant ne faisait plus rien puisque
    // `enCours` ne redescendait jamais a `false`.
    try {
      if (inscription) {
        const { data, error } = await supabase.auth.signUp({
          email: email.trim().toLowerCase(),
          password: motDePasse,
          options: {
            emailRedirectTo: "allure://connexion",
            data: {
              pseudo: pseudo.trim(),
              nom: nom.trim(),
              prenom: prenom.trim(),
              telephone: telephone.trim() || null,
              age: age.trim() || null,
              adresse: adresse.trim() || null,
              sexe,
            },
          },
        });
        if (error) { setErreur(messageErreur(error.message)); return; }
        // Un compte pas encore confirme n'a pas de session : `data.session`
        // est nul. C'est le signal qu'il faut attendre l'e-mail.
        if (!data.session) { setEnAttenteDeConfirmation(true); return; }
        return;
      }

      // Connexion : le pseudo n'existe nulle part cote Supabase Auth,
      // il faut d'abord retrouver l'e-mail associe.
      const { data: emailTrouve, error: erreurRecherche } = await supabase
        .rpc("email_pour_pseudo", { p_pseudo: pseudo.trim() });
      if (erreurRecherche || !emailTrouve) {
        setErreur("Pseudo ou mot de passe incorrect.");
        return;
      }
      const { error } = await supabase.auth.signInWithPassword({
        email: emailTrouve, password: motDePasse,
      });
      if (error) setErreur(messageErreur(error.message));
    } catch {
      setErreur("Quelque chose s'est mal passe. Reessaie.");
    } finally {
      setEnCours(false);
    }
  }

  if (enAttenteDeConfirmation) {
    return (
      <View style={{ flex: 1, backgroundColor: c.fond,
                     paddingTop: marges.top, paddingHorizontal: espace.xl,
                     justifyContent: "center" }}>
        <T v="etiquette" couleur={c.jaune}>Verifie ta boite mail</T>
        <T style={{ fontFamily: polices.titre, fontSize: 30, color: c.encre,
                    lineHeight: 38, marginTop: espace.m }}>
          Un lien de confirmation est parti
        </T>
        <T v="corps" couleur={c.encreDouce}
           style={{ marginTop: espace.l, lineHeight: 25 }}>
          Ouvre le message envoye a {email.trim().toLowerCase()} et appuie
          sur le lien pour activer ton compte. Tu pourras ensuite te
          connecter avec ton pseudo et ton mot de passe.
        </T>
        <T v="petit" style={{ marginTop: espace.xl }}>
          Rien recu au bout de deux minutes ? Regarde dans les
          indesirables.
        </T>
        <View style={{ marginTop: espace.l }}>
          <Bouton titre="Retour" variante="discret"
                  onPress={() => { setEnAttenteDeConfirmation(false); setInscription(false); }} />
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: c.fond }}
    >
      <ScrollView
        contentContainerStyle={{ flexGrow: 1, paddingTop: marges.top,
                                 paddingHorizontal: espace.xl,
                                 paddingBottom: espace.xl,
                                 justifyContent: "center" }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={{ alignItems: "center", marginBottom: espace.l }}>
          <Logo hauteur={104} />
        </View>
        <T v="corps" couleur={c.encreDouce}
           style={{ textAlign: "center", marginBottom: espace.xl }}>
          Les signaux d'un robot qui trade son propre argent.
        </T>

        {inscription ? (
          <>
            <Champ c={c} etiquette="Prenom" valeur={prenom} onChange={setPrenom}
                   placeholder="Ton prenom" />
            <Champ c={c} etiquette="Nom" valeur={nom} onChange={setNom}
                   placeholder="Ton nom" />
          </>
        ) : null}

        <Champ c={c} etiquette="Pseudo" valeur={pseudo} onChange={setPseudo}
               placeholder="tonpseudo" autoCap={false} />

        {inscription ? (
          <>
            <Champ c={c} etiquette="Ton adresse e-mail" valeur={email}
                   onChange={setEmail} placeholder="toi@exemple.fr"
                   type="email-address" autoCap={false} />
            <T v="legende" style={{ marginTop: -espace.m + 4, marginBottom: espace.l }}>
              Un lien de confirmation y sera envoye : c'est obligatoire
              pour activer ton compte.
            </T>

            <Champ c={c} etiquette="Telephone (facultatif)" valeur={telephone}
                   onChange={setTelephone} placeholder="06 12 34 56 78"
                   type="phone-pad" />
            <Champ c={c} etiquette="Age (facultatif)" valeur={age}
                   onChange={setAge} placeholder="30" type="number-pad" />
            <Champ c={c} etiquette="Adresse (facultatif)" valeur={adresse}
                   onChange={setAdresse} placeholder="Ta ville, ton pays" />

            <T v="etiquette" style={{ marginBottom: espace.s }}>
              Sexe (facultatif, pour nos statistiques)
            </T>
            <View style={{ flexDirection: "row", marginBottom: espace.l }}>
              {(["homme", "femme", "non precise"] as const).map((v) => (
                <View key={v} style={{ flex: 1,
                                       marginRight: v !== "non precise" ? espace.s : 0 }}>
                  <Bouton
                    titre={v === "non precise" ? "Je ne dis pas" :
                          v === "homme" ? "Homme" : "Femme"}
                    variante={sexe === v ? "plein" : "contour"}
                    onPress={() => setSexe(v)}
                  />
                </View>
              ))}
            </View>
          </>
        ) : null}

        <Champ c={c} etiquette="Mot de passe" valeur={motDePasse}
               onChange={setMotDePasse} placeholder="********" secret
               onSoumettre={valider} />

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

        <View style={{ flexDirection: "row", alignItems: "center",
                       marginTop: espace.xxl, marginBottom: espace.l }}>
          <View style={{ flex: 1, height: StyleSheet.hairlineWidth,
                         backgroundColor: c.filet }} />
          <T v="petit" couleur={c.encrePale} style={{ marginHorizontal: espace.m }}>
            Autre
          </T>
          <View style={{ flex: 1, height: StyleSheet.hairlineWidth,
                         backgroundColor: c.filet }} />
        </View>

        <BoutonOAuth icone="logo-google" titre="Continuer avec Google"
          onPress={async () => {
            setEnCoursOAuth("google"); setErreur(null);
            const echec = await connexionOAuth("google");
            if (echec) setErreur(echec);
            setEnCoursOAuth(null);
          }}
          enCours={enCoursOAuth === "google"} c={c} />

        <View style={{ height: espace.m }} />

        <BoutonOAuth icone="logo-facebook" titre="Continuer avec Facebook"
          onPress={async () => {
            setEnCoursOAuth("facebook"); setErreur(null);
            const echec = await connexionOAuth("facebook");
            if (echec) setErreur(echec);
            setEnCoursOAuth(null);
          }}
          enCours={enCoursOAuth === "facebook"} c={c} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function BoutonOAuth({ icone, titre, onPress, enCours, c }: {
  icone: keyof typeof Ionicons.glyphMap; titre: string;
  onPress: () => void; enCours: boolean; c: ReturnType<typeof useCouleurs>;
}) {
  return (
    <Pressable
      onPress={enCours ? undefined : onPress}
      style={{
        flexDirection: "row", alignItems: "center", justifyContent: "center",
        borderWidth: StyleSheet.hairlineWidth, borderColor: c.filet,
        borderRadius: rayon.s, paddingVertical: espace.m + 2,
      }}
    >
      <Ionicons name={icone} size={18} color={c.encre}
                style={{ marginRight: espace.s }} />
      <T v="sousTitre" couleur={c.encre}>{enCours ? "..." : titre}</T>
    </Pressable>
  );
}

function Champ({ c, etiquette, valeur, onChange, placeholder, secret,
                type, autoCap = true, onSoumettre }: {
  c: ReturnType<typeof useCouleurs>; etiquette: string; valeur: string;
  onChange: (v: string) => void; placeholder: string; secret?: boolean;
  type?: "default" | "email-address" | "phone-pad" | "number-pad";
  autoCap?: boolean; onSoumettre?: () => void;
}) {
  return (
    <>
      <T v="etiquette" style={{ marginBottom: espace.s }}>{etiquette}</T>
      <TextInput
        value={valeur}
        onChangeText={onChange}
        autoCapitalize={autoCap ? "words" : "none"}
        autoCorrect={false}
        secureTextEntry={secret}
        keyboardType={type ?? "default"}
        placeholder={placeholder}
        placeholderTextColor={c.encrePale}
        onSubmitEditing={onSoumettre}
        style={styles.champ(c)}
      />
    </>
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
