/**
 * Onglet Demo -- la simulation a 500 EUR virtuels, EN DIRECT.
 *
 * Demandee le 18 sept. pour valider la strategie D1 Turtle sur un
 * capital cible avant de le deposer reellement (voir run_demo.py).
 * Meme presentation que l'onglet Direct (nom / % / gain-perte en euros,
 * en direct), sur les VRAIES cotations Bitvavo mais SANS aucun ordre
 * reel -- jamais melangee avec le robot reel (colonne `is_demo`, voir
 * supabase/migrations/20260918234500_marquer_demo.sql, apres la fuite du
 * 18 sept. ou une position simulee etait apparue dans l'app comme si
 * elle etait reelle).
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Position, etagePyramide } from "../services/robot";
import { useSuiviPositions } from "../services/suiviPositions";
import { euros, miseConseillee, nomCrypto, pourcent, resultatEnDirect }
  from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

// Capital de depart de la simulation (voir robot.demo.json, start_balance).
// Aucune table ne le publie -- c'est une constante, pas un compte reel.
const CAPITAL_DEMO_EUR = 500;

function LignePositionDemo({ p, capital, prixActuel }: {
  p: Position; capital: number; prixActuel: number | undefined;
}) {
  const c = useCouleurs();

  if (prixActuel == null) {
    return (
      <View style={{
        flexDirection: "row", justifyContent: "space-between", alignItems: "center",
        backgroundColor: c.surface, borderRadius: rayon.l,
        paddingVertical: espace.m, paddingHorizontal: espace.l, marginBottom: espace.s,
      }}>
        <T v="sousTitre">{nomCrypto(p.pair)}</T>
        <T v="petit" couleur={c.encreDouce}>cotation...</T>
      </View>
    );
  }

  const { pctPrix, eur } = resultatEnDirect(
    p.entry_price, p.stop_loss, prixActuel, p.side, p.position_size_pct ?? 0, capital,
  );
  const positif = eur >= 0;
  const couleur = positif ? c.gain : c.perte;
  // La MISE, en euros : ce que la position engage reellement. Le robot ne
  // publie que le RISQUE en pourcentage -- la somme engagee s'en deduit
  // par la distance au stop (voir miseConseillee).
  const mise = miseConseillee(p.entry_price, p.stop_loss,
                              p.position_size_pct ?? 0, capital);
  const etage = etagePyramide(p);

  return (
    <View style={{
      flexDirection: "row", justifyContent: "space-between", alignItems: "center",
      backgroundColor: c.surface, borderRadius: rayon.l,
      paddingVertical: espace.m, paddingHorizontal: espace.l, marginBottom: espace.s,
    }}>
      <View>
        <T v="sousTitre">{nomCrypto(p.pair)}</T>
        <T v="petit" couleur={c.encreDouce}>{p.side === "buy" ? "Achat" : "Vente"}</T>
        <View style={{ flexDirection: "row", alignItems: "center",
                       marginTop: espace.xs }}>
          <T v="petit" couleur={c.encreDouce}>
            {mise > 0 ? `${euros(mise)} misés` : "mise inconnue"}
          </T>
          {/* L'etage s'affiche TOUJOURS, meme au premier. Il n'apparaissait
              au depart qu'a partir du 2e -- or toutes les positions sont au
              1er tant que le pyramidage ne s'est pas declenche, donc
              l'information n'etait jamais visible. Demande explicite de
              l'operateur : "je ne vois toujours pas les etages 1 ou 2 ou 3". */}
          <T v="petit" couleur={etage > 1 ? c.jaune : c.encreDouce}>
            {" · étage " + etage}
          </T>
        </View>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <T v="chiffre" couleur={couleur}>{euros(eur)}</T>
        <T v="petit" couleur={couleur}>{pourcent(pctPrix)}</T>
      </View>
    </View>
  );
}

export function EcranDemo() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [rafraichit, setRafraichit] = React.useState(false);
  const { positions, capital, prixLive, erreur, rafraichir } =
    useSuiviPositions(true, CAPITAL_DEMO_EUR);

  const gainTotal = React.useMemo(() => {
    if (!positions) return 0;
    return positions.reduce((somme, p) => {
      const prixActuel = prixLive[p.pair];
      if (prixActuel == null) return somme;
      return somme + resultatEnDirect(
        p.entry_price, p.stop_loss, prixActuel, p.side, p.position_size_pct ?? 0, capital,
      ).eur;
    }, 0);
  }, [positions, prixLive, capital]);

  const surRafraichir = async () => {
    setRafraichit(true);
    await rafraichir();
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
        <T v="titreGrand">Demo</T>
        <Logo hauteur={40} />
      </View>

      <Carte accent style={{ marginBottom: espace.l, alignItems: "center" }}>
        <T v="petit" couleur={c.encreDouce}>Capital virtuel (500 EUR de depart)</T>
        <T v="titreGrand" style={{ marginTop: espace.xs }}>
          {euros(capital + gainTotal)}
        </T>
        <T v="petit" couleur={gainTotal >= 0 ? c.gain : c.perte} style={{ marginTop: espace.xs }}>
          {euros(gainTotal)} sur les positions ouvertes
        </T>
      </Carte>

      <T v="sousTitre" style={{ marginBottom: espace.s }}>
        Positions en cours {positions ? `(${positions.length})` : ""}
      </T>
      {!!erreur && <T v="petit" couleur={c.perte}>{erreur}</T>}
      {positions === null ? (
        <Chargement />
      ) : positions.length === 0 ? (
        <Vide titre="Aucune position ouverte"
              detail="Meme moteur que le robot reel, sur capital virtuel." />
      ) : (
        positions.map((p) => (
          <LignePositionDemo key={p.id} p={p} capital={capital}
                              prixActuel={prixLive[p.pair]} />
        ))
      )}
    </ScrollView>
  );
}
