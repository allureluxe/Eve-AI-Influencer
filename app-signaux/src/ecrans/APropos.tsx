/**
 * Onglet Compte -- segment A propos.
 *
 * Reprend le meme argumentaire factuel que l'ancien pied de page de
 * Compte.tsx et que la page Accueil : ce qu'Allure fait, ce qu'elle ne
 * fait jamais. Repete a dessein -- c'est l'endroit ou quelqu'un vient
 * expres pour verifier, pas ou il tombe par hasard.
 */

import React from "react";
import { Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace } from "../theme";
import { Carte, Etiquette, T, useCouleurs } from "../composants/base";

export function EcranAPropos({ onRetour }: { onRetour: () => void }) {
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
        <Etiquette>Ce qu'Allure fait</Etiquette>
        <T v="corps" style={{ marginTop: espace.s }}>
          Depuis fin aout, un robot achete et vend des cryptos avec un
          vrai compte Bitvavo -- pas une simulation. Chaque ouverture et
          chaque cloture de position passe par l'application, gagnante
          ou perdante, sans tri.
        </T>
      </Carte>

      <Carte style={{ marginTop: espace.l }}>
        <Etiquette>Ce qu'Allure ne fait pas</Etiquette>
        {[
          "Allure ne touche jamais a ton argent. Aucune connexion a ton " +
          "compte, aucun ordre passe a ta place.",
          "Allure ne te demande jamais tes cles d'echange, ni ton mot de " +
          "passe Bitvavo ou Binance. Personne de serieux ne le fait.",
          "Allure ne promet aucun gain. Les signaux publies sont ceux " +
          "d'un robot qui engage son propre argent, et il perd " +
          "regulierement.",
        ].map((texte, i) => (
          <T key={i} v="petit" style={{ marginTop: espace.m, lineHeight: 20 }}>
            {texte}
          </T>
        ))}
      </Carte>

      <T v="legende" style={{ textAlign: "center", marginTop: espace.xxl,
                              lineHeight: 17 }}>
        Allure publie des analyses de marche. Ce n'est pas un conseil en
        investissement personnalise. Nous ne detenons aucun fonds.
      </T>
    </ScrollView>
  );
}
