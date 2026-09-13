/**
 * Onglet Agenda — les annonces economiques et ce que le robot en fait.
 *
 * CE QUI FAIT LA VALEUR DE CET ECRAN N'EST PAS LA LISTE.
 * N'importe qui trouve un calendrier economique gratuit en dix
 * secondes. Ce qu'on ne trouve nulle part ailleurs, c'est la LIGNE DU
 * DESSOUS : « aucun nouvel achat entre 14h10 et 14h50 ». Elle dit ce
 * que le robot fera, et elle est calculee depuis sa configuration
 * reelle — elle ne peut donc pas decrire une regle qu'il n'applique pas.
 *
 * D'ou la hierarchie visuelle : l'evenement est le titre, la regle est
 * le contenu, et elle occupe plus de place que lui.
 */

import React from "react";
import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, Evenement, ilYA } from "../services/api";
import { quand } from "../services/format";
import { espace, rayon } from "../theme";
import {
  BandeauCache, Carte, Squelette, T, useCouleurs, Vide,
} from "../composants/base";

/** Le niveau d'impact : un mot, pas une pastille rouge clignotante. */
function Impact({ niveau }: { niveau: Evenement["impact"] }) {
  const c = useCouleurs();
  const texte = niveau === "high" ? "importante"
              : niveau === "medium" ? "moyenne" : "mineure";
  const couleur = niveau === "high" ? c.vigilance : c.encrePale;
  return (
    <View style={{
      paddingHorizontal: espace.s, paddingVertical: 2,
      borderRadius: rayon.s, borderWidth: StyleSheet.hairlineWidth,
      borderColor: couleur,
    }}>
      <T v="legende" couleur={couleur}>{texte}</T>
    </View>
  );
}

function LigneEvenement({ e }: { e: Evenement }) {
  const c = useCouleurs();
  const fort = e.impact === "high";
  return (
    <Carte style={{ marginBottom: espace.m }}
           accent={fort ? c.vigilance : undefined}>
      <View style={{ flexDirection: "row", justifyContent: "space-between",
                     alignItems: "flex-start" }}>
        <View style={{ flex: 1, paddingRight: espace.m }}>
          <T v="sousTitre">{e.name_fr}</T>
          <T v="legende" style={{ marginTop: 3 }}>
            {e.country} · {quand(e.event_time)}
          </T>
        </View>
        <Impact niveau={e.impact} />
      </View>

      {/* LA PARTIE QU'ON NE TROUVE PAS AILLEURS. */}
      <View style={{ marginTop: espace.m, paddingTop: espace.m,
                     borderTopWidth: StyleSheet.hairlineWidth,
                     borderTopColor: c.filet }}>
        <T v="etiquette">Ce que fait le robot</T>
        <T v="corps" couleur={c.encreDouce} style={{ marginTop: espace.xs }}>
          {e.eve_policy}
        </T>
      </View>

      {e.forecast !== null || e.previous !== null ? (
        <View style={{ flexDirection: "row", marginTop: espace.m }}>
          {e.previous !== null ? (
            <View style={{ marginRight: espace.xl }}>
              <T v="etiquette">Precedent</T>
              <T v="chiffre" style={{ fontSize: 14 }}>{e.previous}</T>
            </View>
          ) : null}
          {e.forecast !== null ? (
            <View style={{ marginRight: espace.xl }}>
              <T v="etiquette">Attendu</T>
              <T v="chiffre" style={{ fontSize: 14 }}>{e.forecast}</T>
            </View>
          ) : null}
          {e.actual !== null ? (
            <View>
              <T v="etiquette">Publie</T>
              <T v="chiffre" couleur={c.encre} style={{ fontSize: 14 }}>
                {e.actual}
              </T>
            </View>
          ) : null}
        </View>
      ) : null}
    </Carte>
  );
}

export function EcranAgenda() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [evenements, setEvenements] = React.useState<Evenement[]>([]);
  const [cache, setCache] = React.useState<string | null>(null);
  const [pret, setPret] = React.useState(false);
  const [rafraichit, setRafraichit] = React.useState(false);

  const charger = React.useCallback(async () => {
    const r = await api.evenements();
    setEvenements(r.donnee?.evenements ?? []);
    setCache(r.duCache && r.ageMinutes !== null
      ? `Hors ligne — dernieres donnees ${ilYA(r.ageMinutes)}` : null);
    setPret(true);
  }, []);

  React.useEffect(() => { charger(); }, [charger]);

  if (!pret) {
    return (
      <ScrollView contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.l }}>
        {[0, 1, 2, 3].map((i) => (
          <Squelette key={i} largeur="100%" hauteur={92}
                     style={{ marginBottom: espace.m }} />
        ))}
      </ScrollView>
    );
  }

  // Groupe par jour : quatorze cartes a la suite sont illisibles.
  const parJour = new Map<string, Evenement[]>();
  for (const e of evenements) {
    const cle = new Date(e.event_time).toLocaleDateString("fr-FR", {
      weekday: "long", day: "numeric", month: "long",
    });
    const liste = parJour.get(cle);
    if (liste) liste.push(e);
    else parJour.set(cle, [e]);
  }

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
      refreshControl={
        <RefreshControl refreshing={rafraichit} tintColor={c.laiton}
          onRefresh={async () => {
            setRafraichit(true); await charger(); setRafraichit(false);
          }} />
      }
    >
      <T v="titreGrand">Agenda</T>
      <T v="petit" style={{ marginTop: 2, marginBottom: espace.l }}>
        Les annonces qui bougent les marches, et ce que le robot fera
        autour.
      </T>

      {cache ? <BandeauCache texte={cache} /> : null}

      {[...parJour.entries()].map(([jour, liste]) => (
        <View key={jour}>
          <T v="etiquette" style={{ marginTop: espace.l,
                                    marginBottom: espace.s }}>
            {jour}
          </T>
          {liste.map((e) => <LigneEvenement key={e.id} e={e} />)}
        </View>
      ))}

      {evenements.length === 0 ? (
        <Vide titre="Rien de prevu ces deux prochaines semaines"
              detail={"Seules les annonces des Etats-Unis et de la zone " +
                      "euro sont affichees : ce sont celles qui bougent " +
                      "reellement les cryptos."} />
      ) : null}
    </ScrollView>
  );
}
