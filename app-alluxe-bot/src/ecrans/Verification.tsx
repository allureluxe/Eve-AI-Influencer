/**
 * Verification d'identite, PAS une connexion.
 *
 * Decision explicite de l'operateur (15 sept.) : cette application n'a
 * ni inscription ni ecran de connexion email/mot de passe -- elle est
 * exclusivement pour lui. L'authentification Supabase se fait en
 * arriere-plan avec un compte de service dedie (voir App.tsx), invisible
 * ici.
 *
 * Ce que cet ecran verifie, c'est autre chose : SI JAMAIS il y a un doute
 * sur l'identite de la personne qui tient le telephone, une question est
 * posee. La question affichee reste volontairement "annee de naissance"
 * (anodine, previsible) mais la reponse attendue est un vrai secret.
 *
 * LA REPONSE N'EST JAMAIS DANS CE FICHIER, NI NULLE PART DANS CE DEPOT
 * (public). La comparaison se fait cote serveur, via la fonction
 * `verifier_identite` (voir la migration verification_identite.sql) :
 * l'appli envoie la tentative, le serveur repond vrai/faux, jamais la
 * valeur elle-meme.
 */
import React from "react";
import { TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { supabase } from "../services/supabase";
import { espace, polices, rayon } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

export function EcranVerification({ surReussite }: { surReussite: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [reponse, setReponse] = React.useState("");
  const [erreur, setErreur] = React.useState("");
  const [enCours, setEnCours] = React.useState(false);

  const verifier = async () => {
    setEnCours(true);
    setErreur("");
    const { data, error } = await supabase.rpc("verifier_identite", { reponse });
    setEnCours(false);
    if (error) {
      setErreur("Verification impossible. Reessaie.");
      return;
    }
    if (data === true) {
      surReussite();
    } else {
      setErreur("Ce n'est pas ca.");
      setReponse("");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.fond, justifyContent: "center",
                   paddingHorizontal: espace.l, paddingTop: marges.top,
                   paddingBottom: marges.bottom }}>
      <View style={{ alignItems: "center", marginBottom: espace.xl }}>
        <Logo hauteur={64} />
        <T v="titreGrand" style={{ marginTop: espace.m }}>Alluxe Bot</T>
        <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.xs }}>
          Quelle est ton annee de naissance ?
        </T>
      </View>

      <TextInput
        value={reponse}
        onChangeText={(v) => { setReponse(v); setErreur(""); }}
        placeholder="Annee"
        placeholderTextColor={c.encreDouce}
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
        style={{
          borderWidth: 2, borderColor: erreur ? c.perte : c.filet,
          borderRadius: rayon.s, padding: espace.m, marginBottom: espace.s,
          color: c.encre, fontFamily: polices.interface,
          backgroundColor: c.surface, textAlign: "center",
          letterSpacing: 2,
        }}
      />
      {!!erreur && (
        <T v="petit" couleur={c.perte} style={{ textAlign: "center", marginBottom: espace.m }}>
          {erreur}
        </T>
      )}
      <Bouton titre={enCours ? "Verification..." : "Continuer"}
             onPress={verifier} desactive={enCours || reponse.length === 0} />
    </View>
  );
}
