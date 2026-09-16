/**
 * Onglet Compte -- segment Contact.
 *
 * Les liens legaux rejoignent le contact plutot que "A propos" : on
 * cherche l'un en cherchant l'autre.
 */

import React from "react";
import { Linking, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace } from "../../theme";
import { Carte, Separateur, T, useCouleurs } from "../../composants/base";

export function EcranContact({ onRetour }: { onRetour: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <Pressable onPress={onRetour} style={{ marginBottom: espace.l }}>
        <T v="sousTitre" couleur={c.encreDouce}>‹ Retour</T>
      </Pressable>

      <Carte>
        <T v="corps" couleur={c.encre}
           style={{ paddingVertical: espace.s,
                    textDecorationLine: "underline" }}
           onPress={() => Linking.openURL("mailto:contact@allure-trading.fr")}>
          Nous ecrire
        </T>
        <T v="petit" style={{ marginTop: espace.xs }}>
          contact@allure-trading.fr
        </T>
        <Separateur marge={espace.l} />
        {[
          ["Conditions d'utilisation", "https://allure-trading.fr/cgu"],
          ["Politique de confidentialite", "https://allure-trading.fr/confidentialite"],
        ].map(([libelle, url]) => (
          <T key={url} v="corps" couleur={c.encre}
             style={{ paddingVertical: espace.s,
                      textDecorationLine: "underline" }}
             onPress={() => Linking.openURL(url)}>
            {libelle}
          </T>
        ))}
      </Carte>
    </ScrollView>
  );
}
