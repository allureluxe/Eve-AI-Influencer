/**
 * Onglet Demo -- TROIS simulations a 3 300 EUR, en parallele.
 *
 * Demande de l'operateur le 20 septembre : « 3 onglets dans le mode
 * demo — demo 1, demo 2, demo 3 — et le nom de la methode utilisee avec
 * le capital en direct en euros. En cliquant dessus j'ai toutes les
 * positions et l'historique du compte. »
 *
 * POURQUOI TROIS. Comparer deux methodes l'une APRES l'autre melange
 * l'effet du reglage et celui du marche. Les faire tourner EN MEME
 * TEMPS, sur les memes cotations, isole le reglage -- c'est la seule
 * facon d'obtenir une reponse quand le rejeu ne peut pas trancher, ce
 * qui est justement le cas de la reserve de budget (sur 40 paires, zero
 * reserve et la moitie reservee donnent le meme resultat au centime).
 *
 * Chaque compte est strictement isole : ses fichiers portent son nom
 * (`data/state-demo2.json`...) et chaque ligne publiee porte la colonne
 * `compte`. Sans cela, deux simulations se melangeraient exactement
 * comme la demo s'est melangee au robot reel le 18 septembre -- en pire,
 * puisque les deux sont « virtuelles » et que rien ne choquerait a
 * l'oeil.
 */
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { CompteDemo, Position, comptesDemo, historiqueDemo } from "../services/robot";
import { useSuiviPositions } from "../services/suiviPositions";
import { euros, gainRealiseDe, nomCrypto, pourcent, quand } from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";
import { BarreDeTri, LignePosition, Tri, trier } from "../composants/ListePositions";
import { etagesAffiches, gainTotalEnDirect, resteAInvestir } from "../composants/positionsTri";
import { CourbeCapital } from "../composants/CourbeCapital";
import { CleCompte, ChoixCompte, COMPTES } from "../composants/ChoixCompte";

// Repli quand la fiche du compte n'est pas encore lue. Les trois
// simulations partent de 3 300 EUR (decision de l'operateur, 20 sept. :
// « les 3 comptes doivent avoir une mise de depart de 3 300 € »). La
// valeur reelle vient de `alluxe_bot_comptes`, publiee par le robot
// lui-meme -- l'application ne la devine pas.
const CAPITAL_DEMO_EUR = 3300;

// Les chiffres historiques sont reconstruits depuis les trades fermes corriges
// (profit_eur net), pas depuis une ancienne valeur de cache serveur.
const HISTORIQUE_CORRIGE_LE_23_09_2026 = true;

const LIBELLE_STATUT: Record<string, string> = {
  closed_tp: "Objectif atteint",
  closed_sl: "Stop touche",
  cancelled: "Annule",
};

/** Une position DEMO deja fermee. */
function LigneFermee({ p, capital }: { p: Position; capital: number }) {
  const c = useCouleurs();
  const gagnant = (p.result_pct ?? 0) > 0;
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
        <T v="chiffre" couleur={couleur}>{gain != null ? euros(gain) : "—"}</T>
        <T v="petit" couleur={couleur}>
          {p.result_pct != null ? pourcent(p.result_pct) : ""}
        </T>
      </View>
    </View>
  );
}

export function EcranDemo({ navigation }: { navigation?: any }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [compte, setCompte] = React.useState<CleCompte>("demo");
  const [rafraichit, setRafraichit] = React.useState(false);
  const [fermees, setFermees] = React.useState<Position[] | null>(null);
  const [fiches, setFiches] = React.useState<Record<string, CompteDemo>>({});
  // Le capital de CHAQUE compte, pour que les trois onglets affichent un
  // chiffre sans qu'on ait a les ouvrir un par un.
  const [capitaux, setCapitaux] = React.useState<Record<string, number | null>>({});
  const [tri, setTri] = React.useState<Tri>("gain");
  const [descendant, setDescendant] = React.useState(true);

  const { positions, prixLive, erreur, rafraichir } =
    useSuiviPositions(true, CAPITAL_DEMO_EUR, compte);

  const fiche = fiches[compte];
  const capitalDepart = fiche?.capital_depart ?? CAPITAL_DEMO_EUR;

  const chargerFiches = React.useCallback(async () => {
    try {
      const lignes = await comptesDemo();
      const parCle: Record<string, CompteDemo> = {};
      for (const l of lignes) parCle[l.compte] = l;
      setFiches(parCle);
    } catch { /* l'ecran fonctionne sans les fiches */ }
  }, []);

  const chargerFermees = React.useCallback(async () => {
    try { setFermees(await historiqueDemo(100, compte)); }
    catch { setFermees([]); }
  }, [compte]);

  React.useEffect(() => { chargerFiches(); }, [chargerFiches]);
  React.useEffect(() => { chargerFermees(); }, [chargerFermees]);

  // LE CAPITAL DES AUTRES ONGLETS.
  //
  // Il ne suffit pas de le calculer pour le compte affiche : les trois
  // onglets montrent un chiffre, et un onglet qui affiche « — » pendant
  // qu'on regarde le voisin ne sert a rien. On lit donc l'historique de
  // chaque compte une fois -- leurs positions ouvertes, elles, n'ont pas
  // de cotation en memoire, donc ce chiffre-la est le capital ENCAISSE.
  React.useEffect(() => {
    let vivant = true;
    (async () => {
      const resultats: Record<string, number | null> = {};
      for (const { cle } of COMPTES) {
        const f = fiches[cle];
        if (!f) { resultats[cle] = null; continue; }
        // LE CAPITAL VIVANT VIENT DU SERVEUR quand il l'a publie.
        //
        // On le recalculait a partir des seuls trades FERMES, donc
        // en ignorant les positions ouvertes : le chiffre affiche
        // sur l'onglet qu'on NE regarde PAS paraissait fige.
        // Releve par l'operateur le 22 septembre.
        //
        // `capital_eur` est ecrit toutes les 5 minutes par
        // ops/battement_comptes.py : solde + gain latent, la
        // definition meme du simulateur.
        // SOURCE UNIQUE : trades fermes corriges. Les anciennes valeurs
        // capital_eur/encaisse_eur peuvent dater d'avant la correction.
        try {
          const clos = await historiqueDemo(1000, cle);
          const realise = clos.reduce(
            (somme, t) => somme + (gainRealiseDe(t, f.capital_depart) ?? 0), 0);
          resultats[cle] = f.capital_depart + realise;
        } catch { resultats[cle] = f.capital_depart; }
      }
      if (vivant) setCapitaux(resultats);
    })();
    return () => { vivant = false; };
  }, [fiches]);

  // Le total passe par la MEME fonction que les lignes. Ecrit a la main
  // ici, il a menti pendant que les lignes disaient vrai -- voir
  // `gainTotalEnDirect`.
  const gainTotal = React.useMemo(
    () => (positions ? gainTotalEnDirect(positions, capitalDepart, prixLive) : 0),
    [positions, prixLive, capitalDepart]);

  // LE CAPITAL DOIT INCLURE CE QUI EST DEJA ENCAISSE. Il affichait le
  // depart + les positions ouvertes, en ignorant les trades deja fermes
  // -- donc il ne bougeait jamais malgre les gains realises.
  // LE CHIFFRE PUBLIE D'ABORD, LA RECONSTITUTION SEULEMENT A DEFAUT.
  //
  // La reconstitution vaut `volume x prix d'achat x result_pct`, donc le
  // gain du PRIX — sans les frais que le robot a pourtant payes. Releve
  // par l'operateur le 22 septembre : la demo 2 annoncait 128,28 EUR
  // encaisses quand le solde du simulateur en portait 117,08. Sept
  // trades suffisaient, dont 7,93 EUR de frais et 3,27 d'arrondis.
  //
  // `profit_eur` est desormais publie par le robot, frais deduits, une
  // seule fois par position (zero sur les etages 2+ d'une pyramide). Les
  // lignes fermees AVANT cette date ne l'ont pas : elles retombent sur
  // l'ancien calcul, qui reste la meilleure approximation disponible
  // pour elles. L'historique ne se reecrit pas.
  //
  // ET MEME `profit_eur` NE SUFFIT PAS. Il vaut `ClosedTrade.profit`,
  // qui ne deduit que les frais de VENTE : ceux d'ACHAT sont preleves a
  // l'ouverture et n'apparaissent dans AUCUN trade ferme tant que la
  // position reste ouverte. Sur la demo 2, 25 positions ouvertes depuis
  // le debut representaient 7,93 EUR deja payes et invisibles.
  //
  // Le seul chiffre qui les porte tous est le solde du simulateur, que
  // le serveur publie desormais dans `encaisse_eur`. On le prend des
  // qu'il est la ; la somme des lignes reste le repli.
  const gainRealise = React.useMemo(() => {
    // NE PLUS UTILISER encaisse_eur : cette valeur peut etre ancienne.
    // Le montant corrige vient directement des trades fermes et de
    // profit_eur quand il est disponible.
    if (!fermees) return 0;
    return fermees.reduce(
      (somme, t) => somme + (gainRealiseDe(t, capitalDepart) ?? 0), 0);
  }, [fermees, capitalDepart]);

  // L'onglet ouvert connait ses positions en cours ; les autres non.
  // On remplace donc son chiffre par le capital COMPLET.
  // LE GAIN LATENT COMPTE DANS CE QUI RESTE A INVESTIR.
  //
  // Cette ligne passait `capitalDepart + gainRealise` : elle ignorait
  // les plus-values des positions OUVERTES. Or le simulateur calcule sa
  // marge disponible sur la valeur TOTALE du compte (`equity = solde +
  // gain flottant`), donc l'application annoncait moins de marge que le
  // robot n'en a reellement.
  //
  // Mesure du 22 septembre sur la demo 1 : 165 EUR affiches pour 526
  // disponibles. Releve par l'operateur -- « on n'a pas les memes
  // chiffres sur reste a investir ».
  //
  // `capitalDepart + gainRealise + gainTotal` est exactement le capital
  // affiche en gros au-dessus : les deux chiffres de la carte parlent
  // desormais du meme compte.
  const reste = React.useMemo(
    () => (positions
      ? resteAInvestir(positions, capitalDepart + gainRealise + gainTotal, prixLive)
      : 0),
    [positions, prixLive, capitalDepart, gainRealise, gainTotal]);

  const capitauxAffiches = React.useMemo(() => ({
    ...capitaux,
    [compte]: capitalDepart + gainRealise + gainTotal,
  }), [capitaux, compte, capitalDepart, gainRealise, gainTotal]);

  const surRafraichir = async () => {
    setRafraichit(true);
    await Promise.all([rafraichir(), chargerFermees(), chargerFiches()]);
    setRafraichit(false);
  };

  // Les etages se deduisent de la LISTE ENTIERE, pas d'une ligne isolee :
  // deux achats de la meme crypto sont deux etages, meme quand chaque
  // reference dit « 1 » (positions ouvertes avant la fusion du 19 sept.).
  const etages = React.useMemo(
    () => (positions ? etagesAffiches(positions) : {}), [positions]);

  const ordonnees = React.useMemo(
    () => (positions ? trier(positions, tri, descendant, capitalDepart, prixLive) : null),
    [positions, tri, descendant, capitalDepart, prixLive],
  );

  const nomCompte = COMPTES.find((x) => x.cle === compte)?.nom ?? compte;

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

      <ChoixCompte actif={compte} comptes={fiches} capitaux={capitauxAffiches}
                   surChoix={setCompte} />

      <Carte accent style={{ marginBottom: espace.l, alignItems: "center" }}>
        <T v="petit" couleur={c.encreDouce}>
          {nomCompte} · {euros(capitalDepart)} de départ
        </T>
        <T v="titreGrand" style={{ marginTop: espace.xs }}>
          {euros(capitalDepart + gainRealise + gainTotal)}
        </T>
        <View style={{ flexDirection: "row", gap: espace.m, marginTop: espace.xs }}>
          <T v="petit" couleur={gainRealise >= 0 ? c.gain : c.perte}>
            {euros(gainRealise)} encaissés
          </T>
          <T v="petit" couleur={gainTotal >= 0 ? c.gain : c.perte}>
            {euros(gainTotal)} en cours
          </T>
        </View>
        {/* CE QUI RESTE A INVESTIR. Demande de l'operateur le 21 sept. :
            sans ce chiffre, on ne sait pas si le robot peut encore
            acheter ou s'il est a l'arret faute de place. Il s'affiche en
            gris et non en vert/rouge : ce n'est ni un gain ni une perte,
            c'est de la place disponible. */}
        {positions != null && (
          <T v="petit" couleur={c.encrePale} style={{ marginTop: espace.xs }}>
            {euros(reste)} restants à investir
          </T>
        )}
        {!!fiche?.methode && (
          <T v="legende" couleur={c.encrePale}
             style={{ marginTop: espace.s, textAlign: "center" }}>
            {fiche.methode}
          </T>
        )}
      </Carte>

      {/* LA COURBE DU CAPITAL, facon Bitvavo -- demande de l'operateur
          le 22 septembre. Elle ne montre que ce qui a ete RELEVE :
          le serveur enregistre un point toutes les cinq minutes
          depuis ce jour-la, et on ne reconstitue pas apres coup une
          valeur qu'on n'a jamais notee. */}
      <Carte style={{ marginBottom: espace.l }}>
        <CourbeCapital compte={compte} capitalDepart={capitalDepart} />
      </Carte>

      {!fiche && (
        <Vide titre={`${nomCompte} n'a pas encore démarré`}
              detail="Sa configuration est prête ; il attend d'être lancé." />
      )}

      <T v="sousTitre" style={{ marginBottom: espace.s }}>
        Positions en cours {positions ? `(${positions.length})` : ""}
      </T>
      {!!erreur && <T v="petit" couleur={c.perte}>{erreur}</T>}
      {ordonnees === null ? (
        <Chargement />
      ) : ordonnees.length === 0 ? (
        <Vide titre="Aucune position ouverte"
              detail="Meme moteur que le robot reel, sur capital virtuel." />
      ) : (
        <>
          <BarreDeTri tri={tri} descendant={descendant}
                      surChangement={(t, d) => { setTri(t); setDescendant(d); }} />
          {ordonnees.map((p) => (
            <LignePosition key={p.id} p={p} capital={capitalDepart}
                           prixActuel={prixLive[p.pair]}
                           etage={etages[p.id]}
                           surAppui={navigation ? () => navigation.navigate("Position", {
                             position: p, capital: capitalDepart, mode: nomCompte,
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
        <Vide titre="Aucune position fermee pour l'instant"
              detail="Les trades termines de cette simulation s'afficheront ici." />
      ) : (
        <>
          <T v="petit" couleur={c.encreDouce} style={{ marginBottom: espace.s }}>
            {fermees.filter((t) => (t.result_pct ?? 0) > 0).length} gagnant(s),{" "}
            {fermees.filter((t) => (t.result_pct ?? 0) <= 0).length} perdant(s)
          </T>
          {fermees.map((t) => (
            <LigneFermee key={t.id} p={t} capital={capitalDepart} />
          ))}
        </>
      )}
    </ScrollView>
  );
}
