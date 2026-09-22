/**
 * La courbe du capital d'un compte, facon Bitvavo.
 *
 * Demande de l'operateur le 22 septembre : « un graphisme comme sur
 * Bitvavo, 1 jour 7 jours 30 jours 1 an, pour chaque compte reel et
 * demo ».
 *
 * DESSINEE EN SVG, SANS BIBLIOTHEQUE DE GRAPHIQUES. `react-native-svg`
 * est deja installe et suffit largement : une courbe, un degrade, un
 * point final. Une bibliotheque de charts ajouterait des centaines de
 * kilo-octets a l'application pour des fonctions qu'on n'utiliserait
 * pas, et imposerait son propre style la ou on veut celui de la marque.
 *
 * D'OU VIENNENT LES POINTS. Le serveur releve le capital toutes les
 * cinq minutes (`ops/battement_comptes.py`), mais il n'a commence que le
 * 21 septembre au soir : la courbe n'avait donc que deux points, et les
 * quatre fenetres montraient la meme chose. « Le graphique ne bouge pas,
 * les euros restent les memes qu'au debut. »
 *
 * `ops/reconstituer_capital.py` a comble le passe, heure par heure,
 * depuis l'ouverture de chaque compte : solde realise a cette heure-la
 * plus la valeur de marche des positions alors ouvertes. Meme definition
 * que celle du simulateur, donc la reconstitution se raccorde exactement
 * aux releves en direct.
 *
 * ET QUAND LA FENETRE DEPASSE L'AGE DU COMPTE, on le dit. Un compte de
 * quatre jours n'a pas trente jours d'historique ; afficher « 30 jours »
 * sur une courbe qui en couvre quatre donnerait l'impression d'un
 * capital immobile depuis un mois.
 */
import React from "react";
import { Pressable, View } from "react-native";
import Svg, { Defs, LinearGradient, Path, Stop, Circle, Line } from "react-native-svg";
import { PointCapital, courbeCapital } from "../services/robot";
import { euros, pourcent } from "../services/format";
import { espace, rayon, TRAIT } from "../theme";
import { T, useCouleurs } from "./base";

export type Fenetre = "1j" | "7j" | "30j" | "1an";

const FENETRES: { cle: Fenetre; libelle: string; jours: number }[] = [
  { cle: "1j", libelle: "1 jour", jours: 1 },
  { cle: "7j", libelle: "7 jours", jours: 7 },
  { cle: "30j", libelle: "30 jours", jours: 30 },
  { cle: "1an", libelle: "1 an", jours: 365 },
];

const HAUTEUR = 150;

/** Le trace, en coordonnees SVG. Rend aussi l'aire sous la courbe. */
function chemins(points: PointCapital[], L: number, H: number) {
  const v = points.map((p) => Number(p.capital_eur));
  const bas = Math.min(...v);
  const haut = Math.max(...v);
  // UNE MARGE VERTICALE, SINON LA COURBE COLLE AUX BORDS. Et quand tout
  // est plat (`haut === bas`), on evite la division par zero en
  // dessinant une ligne au milieu plutot qu'un trace invisible.
  const etendue = haut - bas || 1;
  const marge = etendue * 0.12;
  const min = bas - marge;
  const max = haut + marge;
  const x = (i: number) => (i / Math.max(1, v.length - 1)) * L;
  const y = (val: number) => H - ((val - min) / (max - min)) * H;

  let trace = `M ${x(0)} ${y(v[0])}`;
  for (let i = 1; i < v.length; i++) trace += ` L ${x(i)} ${y(v[i])}`;
  const aire = `${trace} L ${L} ${H} L 0 ${H} Z`;
  return { trace, aire, dernierX: x(v.length - 1), dernierY: y(v[v.length - 1]) };
}

export function CourbeCapital({ compte, capitalDepart }: {
  compte: string; capitalDepart: number;
}) {
  const c = useCouleurs();
  const [fenetre, setFenetre] = React.useState<Fenetre>("1j");
  const [points, setPoints] = React.useState<PointCapital[] | null>(null);
  const [largeur, setLargeur] = React.useState(0);

  React.useEffect(() => {
    let vivant = true;
    setPoints(null);
    const jours = FENETRES.find((f) => f.cle === fenetre)!.jours;
    const depuis = new Date(Date.now() - jours * 86400_000).toISOString();
    courbeCapital(compte, depuis)
      .then((p) => { if (vivant) setPoints(p); })
      .catch(() => { if (vivant) setPoints([]); });
    return () => { vivant = false; };
  }, [compte, fenetre]);

  const assez = points !== null && points.length >= 2;

  // LA FENETRE DEMANDEE N'EST PAS TOUJOURS LA FENETRE MONTREE.
  //
  // Un compte ouvert il y a quatre jours n'a pas trente jours
  // d'historique : « 30 jours » et « 1 an » affichent alors exactement
  // la meme courbe que « 7 jours ». Laisser l'etiquette mentir donnerait
  // l'impression d'un capital immobile depuis un an -- c'est ce que
  // l'operateur a vu et signale : « le graphique ne bouge pas, les
  // euros restent les memes qu'au debut ».
  //
  // On annonce donc la periode REELLEMENT couverte des qu'elle est plus
  // courte que celle demandee.
  const couverture = React.useMemo(() => {
    if (!assez) return "";
    const debut = new Date(points![0].vu_le);
    const jours = (Date.now() - debut.getTime()) / 86400_000;
    const demande = FENETRES.find((f) => f.cle === fenetre)!.jours;
    if (jours >= demande * 0.9) return "";
    return `depuis le ${debut.toLocaleDateString("fr-FR",
      { day: "numeric", month: "long" })}`;
  }, [points, fenetre, assez]);
  const premier = assez ? Number(points![0].capital_eur) : capitalDepart;
  const dernier = assez ? Number(points![points!.length - 1].capital_eur) : capitalDepart;
  const variation = premier > 0 ? (dernier / premier - 1) * 100 : 0;
  const hausse = variation >= 0;
  const teinte = hausse ? c.gain : c.perte;

  return (
    <View style={{ marginBottom: espace.l }}>
      <View style={{ flexDirection: "row", alignItems: "baseline",
                     justifyContent: "space-between", marginBottom: espace.s }}>
        <T v="sousTitre">{euros(dernier)}</T>
        {assez && (
          <T v="petit" couleur={teinte}>
            {euros(dernier - premier)} · {pourcent(variation)}
          </T>
        )}
      </View>

      {/* LE PLUS BAS ATTEINT, qu'aucun chiffre unique ne montre. La
          demo 1 est descendue a 3 162 EUR le 19 septembre -- 4 % sous
          la mise -- alors qu'elle affiche +11 % aujourd'hui. C'est
          precisement ce qu'une courbe sert a voir. */}
      {assez && (
        <T v="legende" couleur={c.encrePale} style={{ marginBottom: espace.xs }}>
          plus bas {euros(Math.min(...points!.map((p) => Number(p.capital_eur))))}
          {"  ·  "}plus haut {euros(Math.max(...points!.map((p) => Number(p.capital_eur))))}
        </T>
      )}

      <View
        onLayout={(e) => setLargeur(e.nativeEvent.layout.width)}
        style={{ height: HAUTEUR, justifyContent: "center" }}
      >
        {assez && largeur > 0 ? (() => {
          const { trace, aire, dernierX, dernierY } =
            chemins(points!, largeur, HAUTEUR);
          return (
            <Svg width={largeur} height={HAUTEUR}>
              <Defs>
                <LinearGradient id="remplissage" x1="0" y1="0" x2="0" y2="1">
                  <Stop offset="0" stopColor={teinte} stopOpacity="0.22" />
                  <Stop offset="1" stopColor={teinte} stopOpacity="0" />
                </LinearGradient>
              </Defs>
              {/* Le niveau de depart : on voit d'un coup d'oeil si on est
                  au-dessus ou au-dessous de la mise initiale. */}
              <Line x1="0" y1={HAUTEUR - 1} x2={largeur} y2={HAUTEUR - 1}
                    stroke={c.filetDoux} strokeWidth={1} />
              <Path d={aire} fill="url(#remplissage)" />
              <Path d={trace} stroke={teinte} strokeWidth={2}
                    fill="none" strokeLinejoin="round" strokeLinecap="round" />
              <Circle cx={dernierX} cy={dernierY} r={3.5} fill={teinte} />
            </Svg>
          );
        })() : (
          <T v="petit" couleur={c.encrePale} style={{ textAlign: "center" }}>
            {points === null
              ? "…"
              : "Pas encore assez de relevés sur cette période."}
          </T>
        )}
      </View>

      {!!couverture && (
        <T v="legende" couleur={c.encrePale}
           style={{ textAlign: "center", marginTop: espace.xs }}>
          {couverture} — le compte n'est pas plus ancien
        </T>
      )}

      <View style={{ flexDirection: "row", gap: espace.xs, marginTop: espace.s }}>
        {FENETRES.map(({ cle, libelle }) => {
          const choisi = cle === fenetre;
          return (
            <Pressable
              key={cle}
              onPress={() => setFenetre(cle)}
              accessibilityRole="button"
              accessibilityState={{ selected: choisi }}
              style={{
                flex: 1, paddingVertical: 6, borderRadius: rayon.s,
                alignItems: "center",
                backgroundColor: choisi ? c.jauneAplat : "transparent",
                borderWidth: choisi ? 0 : TRAIT, borderColor: c.filetDoux,
              }}
            >
              <T v="legende" couleur={choisi ? c.surJaune : c.encreDouce}>
                {libelle}
              </T>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
