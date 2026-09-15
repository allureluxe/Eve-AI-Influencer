/**
 * Onglet Objectifs -- les 40 trades de preuve, la methode, et la
 * progression vers 3 000 / 10 000 / 50 000 EUR.
 *
 * Source : table `alluxe_bot_prive`, publiee par un script sur le VPS
 * (meme principe que `ops/publier_etat_public.py`). Tant que cette
 * table n'existe pas encore, l'ecran l'affiche clairement plutot que
 * de planter.
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Objectifs as DonneesObjectifs, objectifs as chargerObjectifs } from "../services/robot";
import { euros, pourcent } from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Chargement, Logo, Separateur, T, useCouleurs, Vide } from "../composants/base";

const METHODE_PAR_DEFAUT = (
  "Strategie D1 Donchian-20 (cassure de canal), pyramidage Turtle 3 " +
  "etages, stop suiveur, stop temporel 5 jours. Palier de risque verrouille " +
  "sur la preuve : 0,6 % par trade tant que l'echantillon de 40 trades " +
  "n'a pas etabli une esperance positive."
);

function LigneObjectif({ cible, atteint, pct }: {
  cible: number; atteint: boolean; pct: number;
}) {
  const c = useCouleurs();
  return (
    <View style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <T v="sousTitre">{euros(cible, 0)}</T>
        <T v="petit" couleur={atteint ? c.gain : c.encreDouce}>
          {atteint ? "Atteint" : pourcent(pct)}
        </T>
      </View>
      <View style={{ height: 8, backgroundColor: c.creux, borderRadius: rayon.rond,
                     marginTop: espace.xs, overflow: "hidden" }}>
        <View style={{ height: "100%", width: `${Math.min(Math.max(pct, 0), 100)}%`,
                       backgroundColor: atteint ? c.gain : c.jaune }} />
      </View>
    </View>
  );
}

export function EcranObjectifs() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [donnees, setDonnees] = React.useState<DonneesObjectifs | null | undefined>(undefined);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [erreur, setErreur] = React.useState("");

  const charger = React.useCallback(async () => {
    try {
      setDonnees(await chargerObjectifs());
      setErreur("");
    } catch (err: any) {
      setErreur(err?.message ?? "Erreur de chargement");
    }
  }, []);

  React.useEffect(() => { charger(); }, [charger]);

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
        <T v="titreGrand">Objectifs</T>
        <Logo hauteur={40} />
      </View>

      {!!erreur && <T v="petit" couleur={c.perte}>{erreur}</T>}

      {donnees === undefined ? (
        <Chargement />
      ) : donnees === null ? (
        <Vide titre="Pas encore configure"
              detail="Le publieur des statistiques (40 trades, objectifs) n'a pas encore ete branche cote serveur." />
      ) : (
        <>
          <Carte accent style={{ marginBottom: espace.l }}>
            <T v="sousTitre" style={{ marginBottom: espace.s }}>
              Echantillon de preuve : {donnees.stats_40.trades} / 40 trades
            </T>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <T v="petit" couleur={c.encreDouce}>Reussite</T>
              <T v="chiffre">
                {donnees.stats_40.taux_reussite_pct != null
                  ? pourcent(donnees.stats_40.taux_reussite_pct) : "—"}
              </T>
            </View>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <T v="petit" couleur={c.encreDouce}>Facteur de profit</T>
              <T v="chiffre">{donnees.stats_40.facteur_profit ?? "—"}</T>
            </View>
            <Separateur marge={espace.s} />
            <T v="petit" couleur={c.encreDouce}>Palier actuel</T>
            <T v="sousTitre">{donnees.stats_40.palier}</T>
          </Carte>

          <T v="sousTitre" style={{ marginBottom: espace.m }}>Progression</T>
          {Object.entries(donnees.objectifs).map(([cible, v]) => (
            <LigneObjectif key={cible} cible={Number(cible)} atteint={v.atteint} pct={v.pct} />
          ))}

          <T v="sousTitre" style={{ marginTop: espace.l, marginBottom: espace.s }}>
            Methode
          </T>
          <T v="corps" couleur={c.encreDouce}>
            {donnees.methode || METHODE_PAR_DEFAUT}
          </T>
        </>
      )}
    </ScrollView>
  );
}
