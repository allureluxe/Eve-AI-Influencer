/**
 * Onglet Compte -- cinq segments : Profil, Abonnement, Bitvavo, A propos,
 * Contact.
 *
 * Retour reel du 14 sept. : « dans l'espace compte, fais des onglets au
 * lieu de montrer que l'abonnement, tu mets profil, et tout les autres
 * onglets ainsi que a propos et contact ».
 *
 * PAS LE GABARIT "Segments" (pastilles bordees) DE Marche.tsx -- avec
 * cinq entrees il deviendrait exactement le "4 gros onglets" reproche
 * le meme soir sur Analyse.tsx. Meme filet discret que Signaux.tsx,
 * dans un ScrollView horizontal puisque cinq libelles ne tiennent pas
 * tous sur un telephone etroit.
 */

import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace } from "../theme";
import { EnTete, Logo, T, useCouleurs } from "../composants/base";
import { EcranProfil } from "./Profil";
import { EcranCompte } from "./Compte";
import { EcranBitvavo } from "./Bitvavo";
import { EcranAPropos } from "./APropos";
import { EcranContact } from "./Contact";

const ONGLETS = [
  ["profil", "Profil"], ["abonnement", "Abonnement"], ["bitvavo", "Bitvavo"],
  ["apropos", "A propos"], ["contact", "Contact"],
] as const;
type Vue = (typeof ONGLETS)[number][0];

function OngletsCompte({ vue, onChoisir }: {
  vue: Vue; onChoisir: (v: Vue) => void;
}) {
  const c = useCouleurs();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false}
      contentContainerStyle={{
        paddingHorizontal: espace.l, borderBottomWidth: 1,
        borderBottomColor: c.filet,
      }}
    >
      {ONGLETS.map(([cle, libelle]) => (
        <T
          key={cle}
          v="petit"
          couleur={vue === cle ? c.encre : c.encrePale}
          style={{
            paddingVertical: espace.s, marginRight: espace.xl,
            borderBottomWidth: 2, marginBottom: -1,
            borderBottomColor: vue === cle ? c.jaune : "transparent",
          }}
          onPress={() => onChoisir(cle)}
        >
          {libelle}
        </T>
      ))}
    </ScrollView>
  );
}

export function EcranCompteEtBitvavo({ email }: { email: string }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [vue, setVue] = React.useState<Vue>("profil");

  return (
    <View style={{ flex: 1, backgroundColor: c.fond }}>
      <View style={{ paddingHorizontal: espace.l,
                     paddingTop: marges.top + espace.m }}>
        <EnTete titre="Compte" sousTitre={email} droite={<Logo hauteur={114} />} />
      </View>
      <OngletsCompte vue={vue} onChoisir={setVue} />
      <View style={{ flex: 1 }}>
        {vue === "profil" ? <EcranProfil email={email} /> : null}
        {vue === "abonnement" ? <EcranCompte /> : null}
        {vue === "bitvavo" ? <EcranBitvavo /> : null}
        {vue === "apropos" ? <EcranAPropos /> : null}
        {vue === "contact" ? <EcranContact /> : null}
      </View>
    </View>
  );
}
