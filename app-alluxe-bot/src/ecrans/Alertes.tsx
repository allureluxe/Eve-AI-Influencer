/**
 * Onglet Alertes -- remplace Telegram (decision de l'operateur, 15 sept.).
 *
 * Tout ce que le robot envoyait sur Telegram (ouverture/fermeture de
 * position, arret, vrais problemes) arrive ici desormais -- voir
 * gold_bot/notifiers.py::AlluxeBotChannel.
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Alerte, alertes } from "../services/robot";
import { espace, rayon } from "../theme";
import { Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

const RYTHME_MS = 15_000;

const COULEUR_NIVEAU: Record<Alerte["niveau"], (c: any) => string> = {
  critical: (c) => c.perte,
  warning: (c) => c.vigilance,
  trade: (c) => c.gain,
  info: (c) => c.encreDouce,
  debug: (c) => c.encrePale,
};

function quandAlerte(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("fr-FR", {
    day: "2-digit", month: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function LigneAlerte({ a }: { a: Alerte }) {
  const c = useCouleurs();
  const couleur = (COULEUR_NIVEAU[a.niveau] ?? COULEUR_NIVEAU.info)(c);
  return (
    <View style={{
      backgroundColor: c.surface, borderRadius: rayon.l,
      paddingVertical: espace.m, paddingHorizontal: espace.l,
      marginBottom: espace.s, borderLeftWidth: 4, borderLeftColor: couleur,
    }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <T v="sousTitre" style={{ flex: 1, marginRight: espace.s }}>{a.titre}</T>
        <T v="legende">{quandAlerte(a.created_at)}</T>
      </View>
      {!!a.corps && (
        <T v="petit" couleur={c.encreDouce} style={{ marginTop: 4 }}>{a.corps}</T>
      )}
    </View>
  );
}

export function EcranAlertes() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [liste, setListe] = React.useState<Alerte[] | null>(null);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [erreur, setErreur] = React.useState("");

  const charger = React.useCallback(async () => {
    try {
      setListe(await alertes());
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
        <T v="titreGrand">Alertes</T>
        <Logo hauteur={40} />
      </View>

      {!!erreur && <T v="petit" couleur={c.perte}>{erreur}</T>}
      {liste === null ? (
        <Chargement />
      ) : liste.length === 0 ? (
        <Vide titre="Aucune alerte pour l'instant" />
      ) : (
        liste.map((a) => <LigneAlerte key={a.id} a={a} />)
      )}
    </ScrollView>
  );
}
