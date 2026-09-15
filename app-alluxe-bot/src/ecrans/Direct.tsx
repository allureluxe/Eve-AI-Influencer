/**
 * Onglet Direct -- le capital reel et les positions en cours.
 *
 * Contrairement a Allure, aucun masquage : c'est l'outil prive de
 * l'operateur, les chiffres sont ceux du compte reel.
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { EtatCapital, Position, etatCapital, positionsOuvertes } from "../services/robot";
import { euros, nomCrypto, pourcent, prix } from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Chargement, Logo, Separateur, T, useCouleurs, Vide } from "../composants/base";

const RYTHME_MS = 10_000;

function LignePosition({ p }: { p: Position }) {
  const c = useCouleurs();
  const risque = p.position_size_pct;
  return (
    <View style={{
      backgroundColor: c.surface, borderRadius: rayon.l,
      paddingVertical: espace.m, paddingHorizontal: espace.l,
      marginBottom: espace.s,
    }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between",
                     alignItems: "center" }}>
        <T v="sousTitre">{nomCrypto(p.pair)} · {p.side === "buy" ? "Achat" : "Vente"}</T>
        {risque != null && (
          <T v="petit" couleur={c.encreDouce}>{pourcent(risque)} du capital</T>
        )}
      </View>
      <Separateur marge={espace.s} />
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <T v="petit" couleur={c.encreDouce}>Entree</T>
        <T v="chiffre">{prix(p.entry_price)}</T>
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <T v="petit" couleur={c.encreDouce}>Stop</T>
        <T v="chiffre">{prix(p.stop_loss)}</T>
      </View>
      {p.take_profit_1 != null && (
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <T v="petit" couleur={c.encreDouce}>Objectif</T>
          <T v="chiffre">{prix(p.take_profit_1)}</T>
        </View>
      )}
    </View>
  );
}

export function EcranDirect() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [capital, setCapital] = React.useState<EtatCapital | null>(null);
  const [positions, setPositions] = React.useState<Position[] | null>(null);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [erreur, setErreur] = React.useState("");

  const charger = React.useCallback(async () => {
    try {
      const [e, p] = await Promise.all([etatCapital(), positionsOuvertes()]);
      setCapital(e);
      setPositions(p);
      setErreur("");
    } catch (err: any) {
      setErreur(err?.message ?? "Erreur de chargement");
    }
  }, []);

  React.useEffect(() => {
    charger();
    const id = setInterval(charger, RYTHME_MS);
    return () => clearInterval(id);
  }, [charger]);

  const surRafraichir = async () => {
    setRafraichit(true);
    await charger();
    setRafraichit(false);
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.fond }}
      contentContainerStyle={{ paddingTop: marges.top + espace.s,
                               paddingHorizontal: espace.l, paddingBottom: espace.xxl }}
      refreshControl={<RefreshControl refreshing={rafraichit} onRefresh={surRafraichir} />}
    >
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between", marginBottom: espace.l }}>
        <T v="titreGrand">Direct</T>
        <Logo hauteur={40} />
      </View>

      <Carte accent style={{ marginBottom: espace.l, alignItems: "center" }}>
        <T v="petit" couleur={c.encreDouce}>Capital reel</T>
        {capital ? (
          <>
            <T v="titreGrand" style={{ marginTop: espace.xs }}>
              {euros(capital.capital_eur)}
            </T>
            <T v="petit"
               couleur={capital.variation_jour_pct >= 0 ? c.gain : c.perte}
               style={{ marginTop: espace.xs }}>
              {pourcent(capital.variation_jour_pct)} aujourd'hui
            </T>
          </>
        ) : <Chargement />}
      </Carte>

      <T v="sousTitre" style={{ marginBottom: espace.s }}>
        Positions en cours {positions ? `(${positions.length})` : ""}
      </T>
      {!!erreur && <T v="petit" couleur={c.perte}>{erreur}</T>}
      {positions === null ? (
        <Chargement />
      ) : positions.length === 0 ? (
        <Vide titre="Aucune position ouverte"
              detail="Le robot attend une occasion qui passe ses filtres." />
      ) : (
        positions.map((p) => <LignePosition key={p.id} p={p} />)
      )}
    </ScrollView>
  );
}
