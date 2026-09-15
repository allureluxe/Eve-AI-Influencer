/**
 * Onglet Discussion -- parler au robot et qu'il agisse.
 *
 * PAS ENCORE CONSTRUIT (15 sept.). Ca demande un pont securise entre
 * cette application et le VPS qui heberge le robot -- un vrai agent
 * avec acces a des outils reels (diagnostics, reglages, redemarrage...),
 * pas un chatbot qui repond sans rien pouvoir faire. C'est la partie la
 * plus complexe du chantier, delibirement construite APRES les 3 autres
 * onglets (donnees deja fiables et testees).
 */
import React from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace } from "../theme";
import { Logo, T, useCouleurs } from "../composants/base";

export function EcranDiscussion() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  return (
    <View style={{ flex: 1, backgroundColor: c.fond, paddingTop: marges.top + espace.s,
                   paddingHorizontal: espace.l }}>
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between", marginBottom: espace.l }}>
        <T v="titreGrand">Discussion</T>
        <Logo hauteur={40} />
      </View>
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center",
                     paddingBottom: espace.xxl }}>
        <T v="sousTitre" style={{ textAlign: "center", marginBottom: espace.s }}>
          Bientot disponible
        </T>
        <T v="corps" couleur={c.encreDouce} style={{ textAlign: "center" }}>
          L'agent qui parle et agit vraiment sur le robot arrive dans une
          prochaine mise a jour.
        </T>
      </View>
    </View>
  );
}
