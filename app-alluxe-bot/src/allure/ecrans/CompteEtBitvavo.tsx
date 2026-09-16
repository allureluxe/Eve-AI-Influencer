/**
 * Onglet Compte -- un menu, cinq pages.
 *
 * Retour reel du 14 sept., DEUXIEME PASSAGE : les cinq segments en
 * onglets horizontaux laissaient un grand vide sous chaque page courte
 * -- « ca fait moche, mets les sous-onglets un en dessous des autres et
 * quand on clique on va sur une autre page ». Meme principe partout
 * ailleurs dans l'application (Signaux, Direct, Communaute) : une
 * liste, un clic, une page a part avec son "‹ Retour" -- jamais un
 * onglet horizontal de plus.
 */

import React from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace, rayon } from "../../theme";
import { EnTete, Logo, Separateur, T, useCouleurs } from "../../composants/base";
import { EcranProfil } from "./Profil";
import { EcranCompte } from "./Compte";
import { EcranBitvavo } from "./Bitvavo";
import { EcranAPropos } from "./APropos";
import { EcranContact } from "./Contact";

const MENU = [
  ["profil", "Profil", "person-outline"],
  ["abonnement", "Abonnement", "star-outline"],
  ["bitvavo", "Bitvavo", "swap-horizontal-outline"],
  ["apropos", "A propos", "information-circle-outline"],
  ["contact", "Contact", "mail-outline"],
] as const;
type Vue = (typeof MENU)[number][0];

function LigneMenu({ icone, libelle, onPress }: {
  icone: keyof typeof Ionicons.glyphMap; libelle: string; onPress: () => void;
}) {
  const c = useCouleurs();
  return (
    <Pressable onPress={onPress} style={{
      flexDirection: "row", alignItems: "center",
      paddingVertical: espace.l,
    }}>
      <View style={{
        width: 36, height: 36, borderRadius: rayon.m,
        backgroundColor: c.creux, alignItems: "center", justifyContent: "center",
        marginRight: espace.m,
      }}>
        <Ionicons name={icone} size={19} color={c.encre} />
      </View>
      <T v="sousTitre" style={{ flex: 1 }}>{libelle}</T>
      <Ionicons name="chevron-forward" size={18} color={c.encrePale} />
    </Pressable>
  );
}

export function EcranCompteEtBitvavo({ email }: { email: string }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [vue, setVue] = React.useState<Vue | null>(null);

  if (vue) {
    const retour = () => setVue(null);
    return (
      <>
        {vue === "profil" ? <EcranProfil email={email} onRetour={retour} /> : null}
        {vue === "abonnement" ? <EcranCompte onRetour={retour} /> : null}
        {vue === "bitvavo" ? <EcranBitvavo onRetour={retour} /> : null}
        {vue === "apropos" ? <EcranAPropos onRetour={retour} /> : null}
        {vue === "contact" ? <EcranContact onRetour={retour} /> : null}
      </>
    );
  }

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <EnTete titre="Compte" sousTitre={email} droite={<Logo hauteur={114} />} />

      {MENU.map(([cle, libelle, icone], i) => (
        <View key={cle}>
          <LigneMenu icone={icone} libelle={libelle} onPress={() => setVue(cle)} />
          {i < MENU.length - 1 ? <Separateur /> : null}
        </View>
      ))}
    </ScrollView>
  );
}
