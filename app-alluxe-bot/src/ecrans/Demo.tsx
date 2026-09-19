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
import { Position, etagePyramide, historiqueDemo } from "../services/robot";
import { useSuiviPositions } from "../services/suiviPositions";
import { euros, gainEnEuros, miseConseillee, nomCrypto, pourcent, quand,
         resultatEnDirect } from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

// Capital de depart de la simulation (voir robot.demo.json,
// start_balance). Aucune table ne le publie -- c'est une constante, pas
// un compte reel.
//
// Porte de 500 a 3 300 EUR le 19 sept. au soir, pour une simulation de
// 48 h a capital plus eleve demandee par l'operateur. Le depot ne doit
// apparaitre NULLE PART comme un gain : `account_reference` et
// `peak_equity` ont ete releves d'autant cote robot, sans quoi le
// gestionnaire de risque aurait lu +560 % de performance.
//
// Ne sert plus qu'aux lignes anterieures au 19 sept. : chaque signal
// publie porte desormais son propre `capital_eur`, fige a l'ouverture.
const CAPITAL_DEMO_EUR = 3300;

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
    p.entry_price, p.stop_loss, prixActuel, p.side, p.position_size_pct ?? 0,
    p.capital_eur ?? capital,
  );
  const positif = eur >= 0;
  const couleur = positif ? c.gain : c.perte;
  // La MISE, en euros : ce que la position engage reellement. Le robot ne
  // publie que le RISQUE en pourcentage -- la somme engagee s'en deduit
  // par la distance au stop (voir miseConseillee).
  // Le capital FIGE a l'ouverture, pas le capital courant : sinon la
  // mise d'une position ouverte a 500 EUR, relue avec 3 300, serait
  // 6,6 fois trop grosse.
  const capitalOuverture = p.capital_eur ?? capital;
  const mise = miseConseillee(p.entry_price, p.stop_loss,
                              p.position_size_pct ?? 0, capitalOuverture);
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

const LIBELLE_STATUT: Record<string, string> = {
  closed_tp: "Objectif atteint",
  closed_sl: "Stop touche",
  cancelled: "Annule",
};

/** Une position DEMO deja fermee. Meme presentation que l'onglet
 *  Historique du reel, pour que les deux se lisent pareil. */
function LigneFermee({ p, capital }: { p: Position; capital: number }) {
  const c = useCouleurs();
  const gagnant = (p.result_pct ?? 0) > 0;
  const gain = gainEnEuros(p.entry_price, p.stop_loss, p.result_pct,
                            p.position_size_pct, p.capital_eur ?? capital);
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

export function EcranDemo() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [rafraichit, setRafraichit] = React.useState(false);
  const [fermees, setFermees] = React.useState<Position[] | null>(null);
  const { positions, capital, prixLive, erreur, rafraichir } =
    useSuiviPositions(true, CAPITAL_DEMO_EUR);

  // L'historique de la DEMO n'avait nulle part ou s'afficher : l'onglet
  // Historique ne montre que le reel (filtre is_demo=false), et les
  // trades simules disparaissaient donc completement une fois fermes.
  const chargerFermees = React.useCallback(async () => {
    try { setFermees(await historiqueDemo()); } catch { /* affiche vide */ }
  }, []);
  React.useEffect(() => { chargerFermees(); }, [chargerFermees]);

  const gainTotal = React.useMemo(() => {
    if (!positions) return 0;
    return positions.reduce((somme, p) => {
      const prixActuel = prixLive[p.pair];
      if (prixActuel == null) return somme;
      return somme + resultatEnDirect(
        p.entry_price, p.stop_loss, prixActuel, p.side, p.position_size_pct ?? 0,
        p.capital_eur ?? capital,
      ).eur;
    }, 0);
  }, [positions, prixLive, capital]);

  // LE CAPITAL DOIT INCLURE CE QUI EST DEJA ENCAISSE.
  //
  // Il affichait 500 EUR + les positions ouvertes, en ignorant les
  // trades deja fermes -- donc le capital ne bougeait jamais malgre les
  // gains realises. C'est pourtant CE chiffre que Monsieur regardera le
  // 28 pour decider de son depot.
  //
  // On ne peut pas lire le solde du simulateur : il repart de 500 EUR a
  // chaque redemarrage du service (limite connue et documentee de
  // PaperBroker.reprendre). Le recalculer depuis les trades fermes est
  // donc plus juste que de lui faire confiance.
  const gainRealise = React.useMemo(() => {
    if (!fermees) return 0;
    return fermees.reduce((somme, t) => {
      const g = gainEnEuros(t.entry_price, t.stop_loss, t.result_pct,
                            t.position_size_pct, t.capital_eur ?? capital);
      return somme + (g ?? 0);
    }, 0);
  }, [fermees, capital]);

  const surRafraichir = async () => {
    setRafraichit(true);
    await Promise.all([rafraichir(), chargerFermees()]);
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
        <T v="petit" couleur={c.encreDouce}>Capital virtuel (3 300 € de départ)</T>
        <T v="titreGrand" style={{ marginTop: espace.xs }}>
          {euros(capital + gainRealise + gainTotal)}
        </T>
        <View style={{ flexDirection: "row", gap: espace.m, marginTop: espace.xs }}>
          <T v="petit" couleur={gainRealise >= 0 ? c.gain : c.perte}>
            {euros(gainRealise)} encaissés
          </T>
          <T v="petit" couleur={gainTotal >= 0 ? c.gain : c.perte}>
            {euros(gainTotal)} en cours
          </T>
        </View>
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

      <T v="sousTitre" style={{ marginTop: espace.xl, marginBottom: espace.s }}>
        Historique {fermees ? `(${fermees.length})` : ""}
      </T>
      {fermees === null ? (
        <Chargement />
      ) : fermees.length === 0 ? (
        <Vide titre="Aucune position fermee pour l'instant"
              detail="Les trades termines de la simulation s'afficheront ici." />
      ) : (
        <>
          <T v="petit" couleur={c.encreDouce} style={{ marginBottom: espace.s }}>
            {fermees.filter((t) => (t.result_pct ?? 0) > 0).length} gagnant(s),{" "}
            {fermees.filter((t) => (t.result_pct ?? 0) <= 0).length} perdant(s)
          </T>
          {fermees.map((t) => <LigneFermee key={t.id} p={t} capital={capital} />)}
        </>
      )}
    </ScrollView>
  );
}
