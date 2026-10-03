/**
 * Verification d'identite -- VERSION WEB (3 oct. 2026).
 *
 * Meme ecran que sur le telephone (« annee »), mais ici c'est AUSSI la
 * connexion : une page web publique ne peut pas embarquer le mot de
 * passe du compte de service comme l'APK (son code se lit dans le
 * navigateur). La reponse part a la fonction Edge `connexion-web`, qui
 * la compare cote serveur et rend un jeton a usage unique ; ce jeton
 * devient la session Supabase. Pas d'empreinte ni de coffre : ils
 * n'existent pas dans un navigateur.
 */
import React from "react";
import { TextInput, View } from "react-native";
import Constants from "expo-constants";
import { supabase } from "../services/supabase";
import { espace, polices, rayon } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string>;

async function ouvrirSession(reponse: string): Promise<"ok" | "faux" | "bloque"> {
  const rep = await fetch(`${extra.supabaseUrl}/functions/v1/connexion-web`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: extra.supabaseAnonKey,
      Authorization: `Bearer ${extra.supabaseAnonKey}`,
    },
    body: JSON.stringify({ reponse }),
  });
  if (rep.status === 401) return "faux";
  if (rep.status === 429) return "bloque";
  if (!rep.ok) throw new Error(`connexion-web ${rep.status}`);
  const { token_hash } = await rep.json();
  const { error } = await supabase.auth.verifyOtp({ token_hash, type: "magiclink" });
  if (error) throw error;
  return "ok";
}

export function EcranVerification({ surReussite }: { surReussite: () => void }) {
  const c = useCouleurs();
  const [reponse, setReponse] = React.useState("");
  const [erreur, setErreur] = React.useState("");
  const [enCours, setEnCours] = React.useState(false);

  const verifier = async () => {
    setEnCours(true);
    setErreur("");
    try {
      const resultat = await ouvrirSession(reponse);
      if (resultat === "ok") { surReussite(); return; }
      setErreur(resultat === "bloque"
        ? "Trop d'essais. Reessaie dans un quart d'heure."
        : "Ce n'est pas ca.");
      setReponse("");
    } catch {
      setErreur("Verification impossible. Reessaie.");
    } finally {
      setEnCours(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.fond, justifyContent: "center",
                   paddingHorizontal: espace.l, alignItems: "center" }}>
      <View style={{ width: "100%", maxWidth: 420 }}>
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
          onSubmitEditing={() => { if (reponse && !enCours) verifier(); }}
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
    </View>
  );
}
