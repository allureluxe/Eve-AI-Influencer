/**
 * La carte d'un signal. L'element le plus regarde de l'application.
 *
 * CE QUI EST AFFICHE, ET DANS QUEL ORDRE
 * --------------------------------------
 * L'ordre repond aux questions dans l'ordre ou elles viennent :
 *
 *   1. Quelle crypto, et on achete ou on vend.
 *   2. A quel prix.
 *   3. COMBIEN CA PEUT COUTER, EN EUROS. C'est la question qui compte
 *      vraiment, et c'est celle que toutes les applications du genre
 *      cachent. On la met en evidence, avec le mot « au pire ».
 *   4. Pourquoi, en francais.
 *
 * La conviction n'est PAS un badge colore ni des etoiles. C'est une
 * barre discrete : elle informe sans transformer un signal en promesse.
 */

import React from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { espace, rayon } from "../theme";
import { euros, jour, nomCrypto, perteMax, pourcent, prix, symbole }
  from "../services/format";
import { Signal } from "../services/api";
import { Carte, T, useCouleurs } from "./base";

/** La barre de conviction : discrete, jamais spectaculaire. */
function Conviction({ valeur }: { valeur: number }) {
  const c = useCouleurs();
  return (
    <View style={{ marginTop: espace.m }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between",
                     marginBottom: espace.xs }}>
        <T v="etiquette">Confiance du robot</T>
        <T v="legende">{valeur} sur 100</T>
      </View>
      <View style={{ height: 3, backgroundColor: c.creux,
                     borderRadius: rayon.rond, overflow: "hidden" }}>
        <View style={{ width: `${Math.max(2, Math.min(100, valeur))}%`,
                       height: "100%", backgroundColor: c.laiton }} />
      </View>
    </View>
  );
}

/** Une ligne « libelle ... valeur », valeur en chiffres alignes. */
function Ligne({ libelle, valeur, couleur, fort }: {
  libelle: string; valeur: string; couleur?: string; fort?: boolean;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between",
                   alignItems: "baseline", paddingVertical: espace.xs + 1 }}>
      <T v="petit">{libelle}</T>
      <T v="chiffre" couleur={couleur ?? (fort ? c.encre : c.encreDouce)}
         style={fort ? { fontSize: 16 } : null}>
        {valeur}
      </T>
    </View>
  );
}

export function CarteSignal({ signal, capital, onPress, marque }: {
  signal: Signal;
  /** Le capital declare par l'utilisateur, pour convertir en euros. */
  capital: number;
  onPress?: () => void;
  marque?: boolean;
}) {
  const c = useCouleurs();
  const clos = signal.status !== "active";
  const achat = signal.side === "buy";
  const perte = perteMax(signal.position_size_pct ?? 0.6, capital);

  const resultat = signal.result_pct;
  const couleurResultat = resultat === null ? c.encreDouce
    : resultat > 0 ? c.hausse : resultat < 0 ? c.baisse : c.encreDouce;

  return (
    <Pressable onPress={onPress} disabled={!onPress}
               style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}>
      <Carte
        style={{ marginBottom: espace.m, opacity: clos ? 0.9 : 1 }}
        accent={clos ? couleurResultat : c.laiton}
      >
        {/* --- 1. quelle crypto, quel sens --- */}
        <View style={{ flexDirection: "row", alignItems: "flex-start",
                       justifyContent: "space-between" }}>
          <View style={{ flex: 1 }}>
            <T v="titre">{nomCrypto(signal.pair)}</T>
            <View style={{ flexDirection: "row", alignItems: "center",
                           marginTop: 2 }}>
              <T v="etiquette" couleur={c.encreDouce}>
                {achat ? "achat" : "vente"}
              </T>
              <View style={{ width: 3, height: 3, borderRadius: rayon.rond,
                             backgroundColor: c.encrePale,
                             marginHorizontal: espace.s }} />
              <T v="legende">{symbole(signal.pair)}</T>
              {signal.macro_flag ? (
                <>
                  <View style={{ width: 3, height: 3, borderRadius: rayon.rond,
                                 backgroundColor: c.encrePale,
                                 marginHorizontal: espace.s }} />
                  <T v="legende" couleur={c.vigilance}>annonce a venir</T>
                </>
              ) : null}
            </View>
          </View>

          {clos && resultat !== null ? (
            <View style={{ alignItems: "flex-end" }}>
              <T v="chiffre" couleur={couleurResultat} style={{ fontSize: 20 }}>
                {pourcent(resultat)}
              </T>
              <T v="legende">
                {signal.closed_at ? jour(signal.closed_at) : ""}
              </T>
            </View>
          ) : (
            <View style={{
              paddingHorizontal: espace.s + 2, paddingVertical: 3,
              borderRadius: rayon.s, borderWidth: StyleSheet.hairlineWidth,
              borderColor: c.laiton,
            }}>
              <T v="legende" couleur={c.laiton}>en cours</T>
            </View>
          )}
        </View>

        {/* --- 2 et 3. les prix, puis ce que ca coute --- */}
        <View style={{ marginTop: espace.l, paddingTop: espace.m,
                       borderTopWidth: StyleSheet.hairlineWidth,
                       borderTopColor: c.filet }}>
          <Ligne libelle="Prix d'entree" valeur={prix(signal.entry_price)} fort />
          <Ligne libelle="Protection (stop)" valeur={prix(signal.stop_loss)} />
          {signal.take_profit_1 ? (
            <Ligne libelle="Objectif" valeur={prix(signal.take_profit_1)} />
          ) : null}
        </View>

        {/* LE CHIFFRE QUI COMPTE. Les applications du genre le cachent ;
            on le met en avant, avec les mots que l'utilisateur emploie. */}
        {!clos && perte > 0 ? (
          <View style={{
            marginTop: espace.m, padding: espace.m,
            backgroundColor: c.creux, borderRadius: rayon.s,
            flexDirection: "row", justifyContent: "space-between",
            alignItems: "center",
          }}>
            <View style={{ flex: 1, paddingRight: espace.m }}>
              <T v="etiquette">Au pire, ca te coute</T>
              <T v="legende" style={{ marginTop: 2 }}>
                sur {euros(capital, 0)} de capital
              </T>
            </View>
            <T v="chiffre" couleur={c.encre} style={{ fontSize: 19 }}>
              {euros(perte)}
            </T>
          </View>
        ) : null}

        {/* --- 4. pourquoi, en francais --- */}
        <T v="corps" couleur={c.encreDouce} style={{ marginTop: espace.l }}>
          {signal.rationale}
        </T>

        {!clos ? <Conviction valeur={signal.conviction} /> : null}

        {marque ? (
          <T v="legende" couleur={c.laiton} style={{ marginTop: espace.m }}>
            Tu as marque ce trade comme pris.
          </T>
        ) : null}
      </Carte>
    </Pressable>
  );
}
