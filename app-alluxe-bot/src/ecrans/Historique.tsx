/**
 * Onglet Historique -- les trades clotures, gains et pertes.
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Position, etatCapital, historique } from "../services/robot";
import { euros, gainRealiseDe, nomCrypto, pourcent, quand } from "../services/format";
import { espace, rayon } from "../theme";
import { Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

const LIBELLE_STATUT: Record<string, string> = {
  closed_tp: "Objectif atteint",
  closed_sl: "Stop touche",
  cancelled: "Annule",
};

function LigneHistorique({ p, capital }: { p: Position; capital: number }) {
  const c = useCouleurs();
  const gagnant = (p.result_pct ?? 0) > 0;
  // Un "+2 %" ne dit rien tant qu'on ignore combien etait engage dessus.
  // Demande du 19 sept. : les montants en euros, comme partout ailleurs.
  const gain = gainRealiseDe(p, capital);
  const couleur = p.result_pct == null ? c.encreDouce : gagnant ? c.gain : c.perte;
  return (
    <View style={{
      flexDirection: "row", justifyContent: "space-between", alignItems: "center",
      backgroundColor: c.surface, borderRadius: rayon.l,
      paddingVertical: espace.m, paddingHorizontal: espace.l, marginBottom: espace.s,
    }}>
      <View>
        <T v="sousTitre">{nomCrypto(p.pair)}</T>
        <T v="legende" style={{ marginTop: 2 }}>
          {LIBELLE_STATUT[p.status] ?? p.status}
          {p.closed_at ? " · " + quand(p.closed_at) : ""}
        </T>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <T v="chiffre" couleur={couleur}>
          {gain != null ? euros(gain) : "—"}
        </T>
        <T v="petit" couleur={couleur}>
          {p.result_pct != null ? pourcent(p.result_pct) : ""}
        </T>
      </View>
    </View>
  );
}

export function EcranHistorique() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [trades, setTrades] = React.useState<Position[] | null>(null);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [erreur, setErreur] = React.useState("");
  const [capital, setCapital] = React.useState(0);
  React.useEffect(() => {
    etatCapital().then((e) => { if (e) setCapital(e.capital_eur); }).catch(() => {});
  }, []);

  const charger = React.useCallback(async () => {
    try {
      setTrades(await historique());
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

  const gains = trades?.filter((t) => (t.result_pct ?? 0) > 0).length ?? 0;
  const pertes = trades?.filter((t) => (t.result_pct ?? 0) <= 0).length ?? 0;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.fond }}
      contentContainerStyle={{ paddingTop: marges.top + espace.s,
                               paddingHorizontal: espace.l, paddingBottom: espace.xxl }}
      refreshControl={<RefreshControl refreshing={rafraichit} onRefresh={surRafraichir} />}
    >
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between", marginBottom: espace.l }}>
        <T v="titreGrand">Historique</T>
        <Logo hauteur={40} />
      </View>

      {trades && trades.length > 0 && (
        <T v="petit" couleur={c.encreDouce} style={{ marginBottom: espace.m }}>
          {gains} gain{gains > 1 ? "s" : ""}, {pertes} perte{pertes > 1 ? "s" : ""}
        </T>
      )}

      {!!erreur && <T v="petit" couleur={c.perte}>{erreur}</T>}
      {trades === null ? (
        <Chargement />
      ) : trades.length === 0 ? (
        <Vide titre="Aucun trade cloture pour l'instant" />
      ) : (
        trades.map((t) => <LigneHistorique key={t.id} p={t} capital={capital} />)
      )}
    </ScrollView>
  );
}
