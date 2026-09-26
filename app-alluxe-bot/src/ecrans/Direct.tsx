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
import {
  CompteDemo, EtatCapital, Position, comptesDemo, etatCapital, historique,
} from "../services/robot";
import { useSuiviPositions } from "../services/suiviPositions";
import { euros, pourcent } from "../services/format";
import { espace } from "../theme";
import { Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";
import { BarreDeTri, LigneFermee, LignePosition, Tri, trier } from "../composants/ListePositions";
import {
  etagesAffiches, gainTotalEnDirect, resteAInvestir,
} from "../composants/positionsTri";
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
  // LA FICHE DU COMPTE REEL. Elle porte les trois choses que l'ecran
  // Demo affiche et que celui-ci n'avait pas : le capital de depart,
  // les euros disponibles (pour calculer le capital EN DIRECT), et la
  // phrase de methode.
  const [fiche, setFiche] = React.useState<CompteDemo | null>(null);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [tri, setTri] = React.useState<Tri>("gain");
  const [descendant, setDescendant] = React.useState(true);
  const { positions, capital, prixLive, erreur, rafraichir } = useSuiviPositions(false, 0);

  // LE CAPITAL SE RELIT, IL NE SE CHARGE PAS UNE FOIS.
  //
  // Il etait lu au montage de l'ecran, et jamais ensuite : les positions
  // bougeaient en direct pendant que le gros chiffre restait fige.
  // Remarque de l'operateur le 26 septembre, dix minutes apres le premier
  // depot reel : « le capital il reste fige ».
  //
  // L'ecran Demo, lui, recalcule le sien a chaque cotation. Ici on ne
  // peut PAS recalculer cote application : au comptant, le capital vaut
  // les euros restants PLUS la valeur de ce qu'on detient, et
  // l'application ne connait pas le solde en euros. C'est le serveur qui
  // le sait, et il le republie toutes les cinq minutes.
  //
  // On le relit donc au meme rythme. Trente secondes : assez pour que le
  // chiffre vive, assez peu pour ne pas interroger la base en boucle.
  React.useEffect(() => {
    let vivant = true;
    const lire = () => {
      etatCapital().then((e) => { if (vivant) setCapitalEtat(e); }).catch(() => {});
    };
    const lireFiche = () => {
      comptesDemo()
        .then((f) => { if (vivant) setFiche(f.find((x) => x.compte === "reel") ?? null); })
        .catch(() => {});
    };
    lire();
    lireFiche();
    historique(100).then((h) => { if (vivant) setFermees(h); })
                   .catch(() => { if (vivant) setFermees([]); });
    const minuteur = setInterval(() => { lire(); lireFiche(); }, 30_000);
    return () => { vivant = false; clearInterval(minuteur); };
  }, []);

  const surRafraichir = async () => {
    setRafraichit(true);
    await Promise.all([
      rafraichir(),
      etatCapital().then(setCapitalEtat).catch(() => {}),
      comptesDemo().then((f) => setFiche(f.find((x) => x.compte === "reel") ?? null))
                   .catch(() => {}),
      historique(100).then(setFermees).catch(() => {}),
    ]);
    setRafraichit(false);
  };

  // LE CAPITAL DE DEPART DU COMPTE REEL, ET CE QU'IL N'EST PAS.
  //
  // Il valait `start_balance` = 1 000 EUR, un reglage de SIMULATEUR
  // recopie sur un compte au comptant. Le gain encaisse s'en deduisait :
  // 118,25 - 1 000 = -881,75 EUR. C'est pour ca que ce bloc n'existait
  // pas ici : il ne manquait pas par oubli, il cachait une absurdite.
  //
  // Le serveur publie desormais les DEPOTS NETS (voir
  // `ops/battement_comptes._depart_reel`) : 120 EUR verses le 25, 2 EUR
  // retires le 26, donc 118 EUR. Definition donnee par l'operateur
  // lui-meme : « si j'ajoute du capital il augmente, si j'en sors il
  // diminue ».
  const depart = fiche?.capital_depart ?? 0;

  // LE CAPITAL EN DIRECT, COMME EN DEMO.
  //
  // Demande de l'operateur le 26 septembre : « je veux le capital en
  // direct comme en demo ». Il avait raison trois fois de suite — le
  // serveur ne republiait que toutes les cinq minutes, et d'un releve a
  // l'autre le chiffre bougeait de un a dix centimes. A cote de
  // positions qui vivent, ca ne se distingue pas d'un chiffre mort.
  //
  // Au comptant, le capital vaut : EUROS RESTANTS + VALEUR DETENUE.
  // Le serveur publie desormais le premier terme (`cash_eur`) ; le
  // second, l'application le calcule deja pour chaque ligne. Il ne
  // manquait donc qu'une addition.
  //
  // Repli sur le dernier releve du serveur tant que `cash_eur` n'est
  // pas arrive : mieux vaut un chiffre en retard que pas de chiffre.
  const capitalVivant = React.useMemo(() => {
    if (fiche?.cash_eur == null || !positions) {
      return capitalEtat?.capital_eur ?? null;
    }
    const detenu = positions.reduce((somme, p) => {
      const prix = prixLive[p.pair] ?? p.entry_price;
      return somme + (p.volume ?? 0) * prix;
    }, 0);
    return fiche.cash_eur + detenu;
  }, [fiche?.cash_eur, positions, prixLive, capitalEtat]);

  // « EN COURS » : le gain latent des positions ouvertes, au cours du
  // moment. Le meme calcul qu'en demo, le meme composant partage.
  const gainLatent = React.useMemo(
    () => (positions ? gainTotalEnDirect(positions, depart, prixLive) : 0),
    [positions, prixLive, depart]);

  // « ENCAISSE » : ce qui est DEJA dans la caisse, latent exclu.
  //
  // On ne reprend PAS `encaisse_eur` du serveur pour le compte reel :
  // il vaut `capital total - depart`, et le capital total inclut deja
  // le latent. L'afficher a cote de « en cours » compterait deux fois
  // la meme chose. On retranche donc le latent explicitement.
  const gainEncaisse = capitalVivant == null || depart <= 0
    ? null : capitalVivant - gainLatent - depart;

  // Les etages se deduisent de la LISTE ENTIERE, pas d'une ligne isolee :
  // deux achats de la meme crypto sont deux etages, meme quand chaque
  // reference dit « 1 » (positions ouvertes avant la fusion du 19 sept.).
  const etages = React.useMemo(
    () => (positions ? etagesAffiches(positions) : {}), [positions]);

  // Le reste a investir se calcule sur le capital VIVANT, comme en
  // demo : sinon il se fige avec l'ancien chiffre du serveur pendant
  // que les positions bougent.
  const reste = React.useMemo(
    () => (positions && capitalVivant != null
      ? resteAInvestir(positions, capitalVivant, prixLive) : 0),
    [positions, capitalVivant, prixLive]);

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

      {/* LA MEME CARTE QU'EN DEMO, AU MOT PRES.
          « Je veux que reel soit a l'identique que demo, sauf les
          chiffres bien sur. » L'operateur l'a redemande le 26 septembre
          captures d'ecran a l'appui : il manquait le capital de depart
          dans l'intitule, la ligne « encaisse / en cours », et la
          phrase de methode. */}
      <Carte accent style={{ marginBottom: espace.l, alignItems: "center" }}>
        <T v="petit" couleur={c.encreDouce}>
          {depart > 0 ? `Capital reel · ${euros(depart)} de départ` : "Capital reel"}
        </T>
        {capitalVivant != null ? (
          <>
            <T v="titreGrand" style={{ marginTop: espace.xs }}>
              {euros(capitalVivant)}
            </T>
            {gainEncaisse != null && (
              <View style={{ flexDirection: "row", gap: espace.m, marginTop: espace.xs }}>
                <T v="petit" couleur={gainEncaisse >= 0 ? c.gain : c.perte}>
                  {euros(gainEncaisse)} encaissés
                </T>
                <T v="petit" couleur={gainLatent >= 0 ? c.gain : c.perte}>
                  {euros(gainLatent)} en cours
                </T>
              </View>
            )}
            {!!capitalEtat && (
              <T v="petit"
                 couleur={capitalEtat.variation_jour_pct >= 0 ? c.gain : c.perte}
                 style={{ marginTop: espace.xs }}>
                {pourcent(capitalEtat.variation_jour_pct)} aujourd'hui
              </T>
            )}
            {/* LE MEME CHIFFRE QU'EN DEMO. Consigne de l'operateur du
                19 septembre : « tu fais le mode demo et reel identique,
                a chaque fois ; si je fais une modif sur l'un ca la fait
                sur l'autre ». Ajoute en demo le 21, donc ajoute ici. */}
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
          </>
        ) : <Chargement />}
      </Carte>

      {/* La meme courbe qu'en demo -- consigne de l'operateur du
          19 septembre : toute modification sur l'un se fait sur
          l'autre. */}
      <Carte style={{ marginBottom: espace.l }}>
        <CourbeCapital compte="reel"
                       capitalDepart={capitalVivant ?? 0} />
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
