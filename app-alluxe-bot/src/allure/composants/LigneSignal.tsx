/**
 * Une ligne compacte pour un signal, dans une liste. Le detail complet
 * (CarteSignal) ne s'affiche plus qu'au clic sur cette ligne.
 *
 * POURQUOI CE CHANGEMENT (14 sept.). Retour reel de l'operateur :
 * « chaque espace a ete utilise, ce n'est pas fluide, c'est trop
 * compacte » -- au sens inverse de son intention : la carte detaillee
 * affichait tout, pour chaque signal, d'un coup, sur un seul ecran qui
 * n'en finissait pas de defiler. Une liste de lignes courtes se lit
 * d'un regard ; le detail vient seulement pour qui clique.
 */

import React from "react";
import { Pressable, View } from "react-native";
import { espace, rayon } from "../../theme";
import { nomCrypto, pourcent } from "../services/format";
import { Signal } from "../services/api";
import { T, useCouleurs } from "../../composants/base";

export function LigneSignal({ signal, onPress }: {
  signal: Signal;
  onPress: () => void;
}) {
  const c = useCouleurs();
  const clos = signal.status !== "active";
  const achat = signal.side === "buy";
  const resultat = signal.result_pct;
  const couleurResultat = resultat === null ? c.encreDouce
    : resultat > 0 ? c.gain : resultat < 0 ? c.perte : c.encreDouce;

  return (
    <Pressable onPress={onPress}
               style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}>
      <View style={{
        flexDirection: "row", alignItems: "center",
        backgroundColor: c.surface, borderRadius: rayon.l,
        paddingVertical: espace.m, paddingHorizontal: espace.l,
        marginBottom: espace.s,
        shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 8,
        shadowOffset: { width: 0, height: 2 }, elevation: 1,
      }}>
        <View style={{ flex: 1 }}>
          <T v="sousTitre">{nomCrypto(signal.pair)}</T>
          <T v="legende" style={{ marginTop: 1 }}>
            {achat ? "achat" : "vente"}
          </T>
        </View>

        {clos && resultat !== null ? (
          <T v="chiffre" couleur={couleurResultat} style={{ fontSize: 17 }}>
            {pourcent(resultat)}
          </T>
        ) : (
          <View style={{
            paddingHorizontal: espace.s + 2, paddingVertical: 3,
            borderRadius: rayon.rond, backgroundColor: c.jaunePale,
          }}>
            <T v="legende" couleur={c.olive}>en cours</T>
          </View>
        )}

        <T v="corps" couleur={c.encrePale}
           style={{ marginLeft: espace.m, fontSize: 20 }}>
          ›
        </T>
      </View>
    </Pressable>
  );
}

/** Une case floutee : un signal existe, son contenu ne se montre pas.
 *
 * Ne recopie AUCUNE donnee reelle -- ni le nom de la crypto, ni le
 * sens, rien. Un flou pose sur un vrai signal donnerait l'information
 * en pretendant la vendre (deja tranche le 12 sept., voir Signaux.tsx :
 * « annoncer BTC vient de passer a l'achat, abonne-toi, serait donner
 * le signal tout en pretendant le vendre »). Ceci est un GABARIT vide,
 * pas un vrai signal recouvert.
 */
export function LigneFloutee() {
  const c = useCouleurs();
  return (
    <View style={{
      flexDirection: "row", alignItems: "center",
      backgroundColor: c.creux, borderRadius: rayon.l,
      paddingVertical: espace.m, paddingHorizontal: espace.l,
      marginBottom: espace.s, opacity: 0.6,
    }}>
      <View style={{ flex: 1 }}>
        <View style={{ width: "40%", height: 14, borderRadius: rayon.s,
                       backgroundColor: c.filetDoux }} />
        <View style={{ width: "25%", height: 10, borderRadius: rayon.s,
                       backgroundColor: c.filetDoux, marginTop: espace.xs }} />
      </View>
      <T v="legende" couleur={c.encrePale}>Allure Plus</T>
    </View>
  );
}
