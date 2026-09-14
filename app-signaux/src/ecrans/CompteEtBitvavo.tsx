/**
 * Onglet Compte — Compte et Bitvavo, sous un meme toit.
 *
 * Meme principe que AnalyseEtMarche.tsx : Bitvavo (ou passer ses
 * ordres, le parrainage) se consulte rarement, une fois qu'on sait
 * faire -- c'est plus proche d'un reglage que d'un flux qu'on ouvre
 * tous les jours. Il rejoint Compte plutot que d'occuper une case a
 * lui seul dans la barre du bas.
 */

import React from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace } from "../theme";
import { useCouleurs } from "../composants/base";
import { Segments } from "./Marche";
import { EcranCompte } from "./Compte";
import { EcranBitvavo } from "./Bitvavo";

const ONGLETS = [["compte", "Compte"], ["bitvavo", "Bitvavo"]] as const;
type Vue = (typeof ONGLETS)[number][0];

export function EcranCompteEtBitvavo({ email, onRevoirPresentation }: {
  email: string;
  onRevoirPresentation: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [vue, setVue] = React.useState<Vue>("compte");

  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   paddingTop: marges.top + espace.s }}>
      <Segments options={ONGLETS} choisi={vue} onChoisir={setVue} />
      {vue === "compte"
        ? <EcranCompte email={email} onRevoirPresentation={onRevoirPresentation} />
        : <EcranBitvavo />}
    </View>
  );
}
