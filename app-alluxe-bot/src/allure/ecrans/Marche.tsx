/**
 * Onglet Marche — les cours et l'agenda, sous un meme toit.
 *
 * POURQUOI ILS SONT REGROUPES
 * ---------------------------
 * Huit ecrans pour une barre du bas, c'est six de trop : au-dela de
 * cinq ou six onglets, les libelles deviennent illisibles et plus
 * personne ne trouve rien.
 *
 * Le regroupement n'est pas arbitraire. « Quel est le cours ? » et
 * « qu'est-ce qui va bouger le marche cette semaine ? » sont la meme
 * question posee a deux echelles de temps. On les met cote a cote,
 * separees par un selecteur, plutot que de les eparpiller.
 */

import React from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace, rayon, TRAIT } from "../../theme";
import { T, useCouleurs } from "../../composants/base";
import { EcranCours } from "./Cours";
import { EcranAgenda } from "./Agenda";

export function Segments<T extends string>({ options, choisi, onChoisir }: {
  options: readonly (readonly [T, string])[];
  choisi: T;
  onChoisir: (v: T) => void;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", paddingHorizontal: espace.l,
                   paddingBottom: espace.s }}>
      {options.map(([cle, libelle]) => {
        const actif = cle === choisi;
        return (
          <T
            key={cle}
            v="sousTitre"
            couleur={actif ? c.surJaune : c.encre}
            onPress={() => onChoisir(cle)}
            style={{
              flex: 1, textAlign: "center", overflow: "hidden",
              backgroundColor: actif ? c.jaune : "transparent",
              borderWidth: TRAIT,
              borderColor: actif ? c.jaune : c.filetDoux,
              borderRadius: rayon.s,
              paddingVertical: espace.s + 2,
              marginRight: cle === options[options.length - 1][0]
                ? 0 : espace.s,
            }}
          >
            {libelle}
          </T>
        );
      })}
    </View>
  );
}

const ONGLETS = [["cours", "Cours"], ["agenda", "Agenda"]] as const;
type Vue = (typeof ONGLETS)[number][0];

export function EcranMarche() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [vue, setVue] = React.useState<Vue>("cours");

  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   paddingTop: marges.top + espace.s }}>
      <Segments options={ONGLETS} choisi={vue} onChoisir={setVue} />
      {vue === "cours" ? <EcranCours /> : <EcranAgenda />}
    </View>
  );
}
