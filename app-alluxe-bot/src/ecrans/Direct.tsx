/**
 * Onglet Direct -- le capital reel et les positions en cours, EN DIRECT.
 *
 * Contrairement a Allure, aucun masquage : c'est l'outil prive de
 * l'operateur, les chiffres sont ceux du compte reel.
 *
 * Refonte du 18-19 sept., sur retour direct de l'operateur : "style
 * trading, juste le nom de la crypto, le pourcentage et le benefice ou
 * negatif en euro, en direct, pas toutes les 10 secondes". Voir
 * `useSuiviPositions` (Realtime pour la liste, prix Bitvavo en direct
 * pour le calcul) et `resultatEnDirect` (le calcul lui-meme).
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { EtatCapital, Position, etagePyramide, etatCapital } from "../services/robot";
import { useSuiviPositions } from "../services/suiviPositions";
import { euros, miseConseillee, nomCrypto, pourcent, resultatEnDirect }
  from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

function LignePositionDirecte({ p, capital, prixActuel }: {
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

export function EcranDirect() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [capitalEtat, setCapitalEtat] = React.useState<EtatCapital | null>(null);
  const [rafraichit, setRafraichit] = React.useState(false);
  const { positions, capital, prixLive, erreur, rafraichir } = useSuiviPositions(false, 0);

  React.useEffect(() => {
    etatCapital().then(setCapitalEtat).catch(() => {});
  }, []);

  const surRafraichir = async () => {
    setRafraichit(true);
    await Promise.all([rafraichir(), etatCapital().then(setCapitalEtat).catch(() => {})]);
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
        {capitalEtat ? (
          <>
            <T v="titreGrand" style={{ marginTop: espace.xs }}>
              {euros(capitalEtat.capital_eur)}
            </T>
            <T v="petit"
               couleur={capitalEtat.variation_jour_pct >= 0 ? c.gain : c.perte}
               style={{ marginTop: espace.xs }}>
              {pourcent(capitalEtat.variation_jour_pct)} aujourd'hui
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
        positions.map((p) => (
          <LignePositionDirecte key={p.id} p={p} capital={capital}
                                 prixActuel={prixLive[p.pair]} />
        ))
      )}
    </ScrollView>
  );
}
