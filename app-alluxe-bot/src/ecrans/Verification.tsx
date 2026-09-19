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
 *
 * DEVERROUILLAGE PAR EMPREINTE/FACE ID AJOUTE (18 sept.) : retour reel de
 * l'operateur, taper la reponse a chaque ouverture "ca me saoule". La
 * question secrete reste le SEUL moyen de prouver l'identite au serveur
 * (c'est elle qui est verifiee cote Supabase) -- la biometrie ne fait que
 * REJOUER cette meme reponse, deja tapee une premiere fois et gardee dans
 * le coffre securise du telephone (`expo-secure-store`, chiffre par le
 * systeme, jamais lisible depuis JS ni depuis ce depot). Sans empreinte
 * enregistree sur l'appareil, ou au premier lancement, on retombe sur la
 * saisie normale -- rien ne casse.
 */
import React from "react";
import { Pressable, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import { Ionicons } from "@expo/vector-icons";
import { supabase } from "../services/supabase";
import { espace, polices, rayon } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

const CLE_COFFRE = "alluxe_bot_reponse_identite";

async function verifierAupresDuServeur(reponse: string): Promise<boolean> {
  const { data, error } = await supabase.rpc("verifier_identite", { reponse });
  if (error) throw error;
  return data === true;
}

export function EcranVerification({ surReussite }: { surReussite: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [reponse, setReponse] = React.useState("");
  const [erreur, setErreur] = React.useState("");
  const [enCours, setEnCours] = React.useState(false);
  const [biometrieDisponible, setBiometrieDisponible] = React.useState(false);
  // null tant qu'on n'a pas fini de regarder si une empreinte a deja ete
  // enregistree -- evite d'afficher un instant le clavier avant de
  // basculer sur Face ID.
  const [pretALessai, setPretALessai] = React.useState<boolean | null>(null);

  const essayerBiometrie = React.useCallback(async () => {
    try {
      const enregistree = await SecureStore.getItemAsync(CLE_COFFRE);
      const materiel = await LocalAuthentication.hasHardwareAsync();
      const enrole = materiel && await LocalAuthentication.isEnrolledAsync();
      setBiometrieDisponible(!!enrole);
      if (!enregistree || !enrole) {
        setPretALessai(false);
        return;
      }
      const resultat = await LocalAuthentication.authenticateAsync({
        promptMessage: "Alluxe Bot",
        cancelLabel: "Taper la reponse a la place",
        disableDeviceFallback: false,
      });
      if (resultat.success) {
        surReussite();
      } else {
        setPretALessai(false);
      }
    } catch {
      setPretALessai(false);
    }
  }, [surReussite]);

  React.useEffect(() => { essayerBiometrie(); }, [essayerBiometrie]);

  const verifier = async () => {
    setEnCours(true);
    setErreur("");
    try {
      const ok = await verifierAupresDuServeur(reponse);
      if (ok) {
        // Garde la reponse dans le coffre chiffre du systeme (jamais dans
        // AsyncStorage en clair) pour que la prochaine ouverture puisse la
        // rejouer via l'empreinte/Face ID, sans la retaper.
        try { await SecureStore.setItemAsync(CLE_COFFRE, reponse); } catch { /* pas grave */ }
        surReussite();
      } else {
        setErreur("Ce n'est pas ca.");
        setReponse("");
      }
    } catch {
      setErreur("Verification impossible. Reessaie.");
    } finally {
      setEnCours(false);
    }
  };

  if (pretALessai === null) {
    return (
      <View style={{ flex: 1, backgroundColor: c.fond, alignItems: "center",
                     justifyContent: "center" }}>
        <Logo hauteur={64} />
      </View>
    );
  }

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

      {biometrieDisponible && (
        <Pressable onPress={essayerBiometrie} style={{
          flexDirection: "row", alignItems: "center", justifyContent: "center",
          marginTop: espace.l,
        }}>
          <Ionicons name="finger-print-outline" size={18} color={c.encreDouce} />
          <T v="petit" couleur={c.encreDouce} style={{ marginLeft: espace.xs }}>
            Reessayer par empreinte / Face ID
          </T>
        </Pressable>
      )}
    </View>
  );
}
