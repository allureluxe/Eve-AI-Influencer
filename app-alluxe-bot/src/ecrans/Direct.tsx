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
 *
 * LA LIGNE DE POSITION ET LE TRI VIVENT DANS `composants/ListePositions`,
 * partages avec l'onglet Demo. Demande de l'operateur le 19 sept. : « tu
 * fais le mode demo et reel identiques, si je fais une modif sur l'un ca
 * la fait sur l'autre ». Deux copies ne resteraient pas identiques
 * longtemps ; un seul code, si.
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { EtatCapital, Position, etatCapital, historique } from "../services/robot";
import { useSuiviPositions } from "../services/suiviPositions";
import { euros, pourcent } from "../services/format";
import { espace } from "../theme";
import { Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";
import { BarreDeTri, LigneFermee, LignePosition, Tri, trier } from "../composants/ListePositions";
import { etagesAffiches, resteAInvestir } from "../composants/positionsTri";
import { CourbeCapital } from "../composants/CourbeCapital";

export function EcranDirect({ navigation }: { navigation?: any }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [capitalEtat, setCapitalEtat] = React.useState<EtatCapital | null>(null);
  // L'HISTORIQUE MANQUAIT AU REEL, et seulement au reel.
  // « Je veux que reel soit a l'identique que demo, sauf les chiffres. »
  // L'ecran Demo montrait ses trades fermes depuis le 20 septembre ;
  // celui du compte qui engage de l'argent, non.
  const [fermees, setFermees] = React.useState<Position[] | null>(null);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [tri, setTri] = React.useState<Tri>("gain");
  const [descendant, setDescendant] = React.useState(true);
  const { positions, capital, prixLive, erreur, rafraichir } = useSuiviPositions(false, 0);

  React.useEffect(() => {
    etatCapital().then(setCapitalEtat).catch(() => {});
    historique(100).then(setFermees).catch(() => setFermees([]));
  }, []);

  const surRafraichir = async () => {
    setRafraichit(true);
    await Promise.all([
      rafraichir(),
      etatCapital().then(setCapitalEtat).catch(() => {}),
      historique(100).then(setFermees).catch(() => {}),
    ]);
    setRafraichit(false);
  };

  // Les etages se deduisent de la LISTE ENTIERE, pas d'une ligne isolee :
  // deux achats de la meme crypto sont deux etages, meme quand chaque
  // reference dit « 1 » (positions ouvertes avant la fusion du 19 sept.).
  const etages = React.useMemo(
    () => (positions ? etagesAffiches(positions) : {}), [positions]);

  const reste = React.useMemo(
    () => (positions && capitalEtat
      ? resteAInvestir(positions, capitalEtat.capital_eur, prixLive) : 0),
    [positions, capitalEtat, prixLive]);

  const ordonnees = React.useMemo(
    () => (positions ? trier(positions, tri, descendant, capital, prixLive) : null),
    [positions, tri, descendant, capital, prixLive],
  );

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
            {/* LE MEME CHIFFRE QU'EN DEMO. Consigne de l'operateur du
                19 septembre : « tu fais le mode demo et reel identique,
                a chaque fois ; si je fais une modif sur l'un ca la fait
                sur l'autre ». Ajoute en demo le 21, donc ajoute ici. */}
            {positions != null && (
              <T v="petit" couleur={c.encrePale} style={{ marginTop: espace.xs }}>
                {euros(reste)} restants à investir
              </T>
            )}
          </>
        ) : <Chargement />}
      </Carte>

      {/* La meme courbe qu'en demo -- consigne de l'operateur du
          19 septembre : toute modification sur l'un se fait sur
          l'autre. */}
      <Carte style={{ marginBottom: espace.l }}>
        <CourbeCapital compte="reel"
                       capitalDepart={capitalEtat?.capital_eur ?? 0} />
      </Carte>

      <T v="sousTitre" style={{ marginBottom: espace.s }}>
        Positions en cours {positions ? `(${positions.length})` : ""}
      </T>
      {!!erreur && <T v="petit" couleur={c.perte}>{erreur}</T>}
      {ordonnees === null ? (
        <Chargement />
      ) : ordonnees.length === 0 ? (
        <Vide titre="Aucune position ouverte"
              detail="Le robot attend une occasion qui passe ses filtres." />
      ) : (
        <>
          <BarreDeTri tri={tri} descendant={descendant}
                      surChangement={(t, d) => { setTri(t); setDescendant(d); }} />
          {ordonnees.map((p) => (
            <LignePosition key={p.id} p={p} capital={capital}
                           prixActuel={prixLive[p.pair]}
                           etage={etages[p.id]}
                           surAppui={navigation ? () => navigation.navigate("Position", {
                             position: p, capital, mode: "Réel",
                           }) : undefined} />
          ))}
        </>
      )}

      <T v="sousTitre" style={{ marginTop: espace.xl, marginBottom: espace.s }}>
        Historique {fermees ? `(${fermees.length})` : ""}
      </T>
      {fermees === null ? (
        <Chargement />
      ) : fermees.length === 0 ? (
        <Vide titre="Aucune position fermée pour l'instant"
              detail="Les trades terminés du compte réel s'afficheront ici." />
      ) : (
        <>
          <T v="petit" couleur={c.encreDouce} style={{ marginBottom: espace.s }}>
            {fermees.filter((t) => (t.result_pct ?? 0) > 0).length} gagnant(s),{" "}
            {fermees.filter((t) => (t.result_pct ?? 0) <= 0).length} perdant(s)
          </T>
          {fermees.map((t) => (
            <LigneFermee key={t.id} p={t}
                         capital={capitalEtat?.capital_eur ?? capital} />
          ))}
        </>
      )}
    </ScrollView>
  );
}
