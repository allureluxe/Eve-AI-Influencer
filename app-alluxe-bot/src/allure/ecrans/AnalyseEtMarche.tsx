/**
 * Onglet Analyse — Analyse et Marche, sous un meme toit.
 *
 * Meme principe que Marche.tsx (qui combine deja Cours et Agenda) :
 * six onglets en bas, c'etait trop -- retour reel de l'operateur le
 * 14 sept., « trop d'onglets, trop de texte par ecran ». On reduit le
 * nombre de cases dans la barre sans jeter le contenu : « le point du
 * matin et l'historique » (Analyse) et « les cours et l'agenda »
 * (Marche) sont deux lectures voisines -- l'une explique ce qui s'est
 * passe, l'autre ce qui pourrait bouger. Un selecteur plutot qu'un
 * onglet de plus.
 */

import React from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace } from "../../theme";
import { Logo, T, useCouleurs } from "../../composants/base";
import { Segments } from "./Marche";
import { EcranAnalyse } from "./Analyse";
import { EcranMarche } from "./Marche";

const ONGLETS = [["analyse", "Analyse"], ["marche", "Marche"]] as const;
type Vue = (typeof ONGLETS)[number][0];

export function EcranAnalyseEtMarche({ versAbonnement }: {
  versAbonnement: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [vue, setVue] = React.useState<Vue>("analyse");

  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   paddingTop: marges.top + espace.s }}>
      {/* Titre et logo D'ABORD, le selecteur en dessous -- retour reel
          du 14 sept. : « inverse le titre et logo en haut et les 2
          onglets en dessous ». */}
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between",
                     paddingHorizontal: espace.l, marginBottom: espace.m }}>
        <T v="titreGrand">{vue === "analyse" ? "Analyse" : "Marche"}</T>
        <Logo hauteur={114} />
      </View>
      <Segments options={ONGLETS} choisi={vue} onChoisir={setVue} />
      {vue === "analyse"
        ? <EcranAnalyse versAbonnement={versAbonnement} />
        : <EcranMarche />}
    </View>
  );
}
