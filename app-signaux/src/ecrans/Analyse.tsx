/**
 * Onglet Analyse — la note du matin et l'historique chiffre.
 *
 * L'HISTORIQUE EST L'ECRAN LE PLUS DANGEREUX DE L'APPLICATION.
 * C'est celui qui justifie l'abonnement, donc celui ou la tentation
 * d'embellir est la plus forte, et celui que la conformite regarde en
 * premier. Trois regles tenues ici :
 *
 *   - le serveur refuse de rendre une courbe sous 30 trades, et
 *     l'ecran affiche franchement « pas encore assez d'historique »
 *     plutot que de tracer une jolie ligne sur six points ;
 *   - les hypotheses sont affichees SOUS la courbe, pas cachees
 *     derriere un lien ;
 *   - le recul maximum — combien on a perdu au pire moment — est
 *     montre avec la meme taille que le gain. Une application qui
 *     n'affiche que la hausse ment par omission.
 */

import React from "react";
import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { EcranDemo } from "./Demo";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Path, Line } from "react-native-svg";
import { api, ilYA, NoteMarche, Performance } from "../services/api";
import { euros, pourcent } from "../services/format";
import { espace, rayon } from "../theme";
import {
  BandeauCache, Carte, Logo, Separateur, Squelette, T, useCouleurs, Vide,
} from "../composants/base";

/** Une jauge horizontale, sobre : un filet et un repere. */
function Jauge({ titre, valeur, min, max, legende }: {
  titre: string; valeur: number | null; min: number; max: number;
  legende?: string;
}) {
  const c = useCouleurs();
  if (valeur === null) return null;
  const part = Math.max(0, Math.min(1, (valeur - min) / (max - min)));
  return (
    <View style={{ marginBottom: espace.l }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between",
                     marginBottom: espace.s }}>
        <T v="etiquette">{titre}</T>
        <T v="chiffre" couleur={c.encreDouce} style={{ fontSize: 13 }}>
          {legende ?? String(valeur)}
        </T>
      </View>
      <View style={{ height: 3, backgroundColor: c.creux,
                     borderRadius: rayon.rond }}>
        <View style={{
          position: "absolute", left: `${part * 100}%`,
          width: 3, height: 11, top: -4, marginLeft: -1.5,
          backgroundColor: c.jaune, borderRadius: rayon.rond,
        }} />
      </View>
    </View>
  );
}

/** La courbe de capital. Un trait, une ligne de depart, rien d'autre. */
function Courbe({ points }: { points: { capital: number }[] }) {
  const c = useCouleurs();
  const L = 300, H = 120;
  if (points.length < 2) return null;

  const valeurs = points.map((p) => p.capital);
  const bas = Math.min(...valeurs), haut = Math.max(...valeurs);
  const amplitude = haut - bas || 1;
  const x = (i: number) => (i / (points.length - 1)) * L;
  const y = (v: number) => H - ((v - bas) / amplitude) * (H - 8) - 4;

  const trace = valeurs
    .map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");
  const depart = valeurs[0];

  return (
    <Svg width="100%" height={H} viewBox={`0 0 ${L} ${H}`}
         preserveAspectRatio="none">
      {/* La ligne du capital de depart : sans elle, une courbe qui
          descend peut ressembler a une courbe qui monte. */}
      <Line x1={0} y1={y(depart)} x2={L} y2={y(depart)}
            stroke={c.filet} strokeWidth={1} strokeDasharray="3 4" />
      <Path d={trace} stroke={c.jaune} strokeWidth={1.8} fill="none"
            strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  );
}

function Statistique({ libelle, valeur, couleur }: {
  libelle: string; valeur: string; couleur?: string;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flex: 1, minWidth: "45%", marginBottom: espace.l }}>
      <T v="etiquette">{libelle}</T>
      <T v="chiffre" couleur={couleur ?? c.encre}
         style={{ fontSize: 20, marginTop: 3 }}>
        {valeur}
      </T>
    </View>
  );
}

const VUES = [["note", "Le point"], ["demo", "Essayer"]] as const;
type Vue = (typeof VUES)[number][0];

/**
 * L'en-tete de l'onglet, et son choix "Le point / Essayer" en-dessous --
 * PAS un deuxieme gros bouton segmente empile sur celui d'AnalyseEtMarche.
 * Retour reel du 14 sept. : « 4 gros onglets, essaye un autre truc ».
 * Meme filet discret que Signaux.tsx (En cours / Historique) : un trait
 * sous le libelle actif, pas une pastille bordee.
 */
function EnteteAnalyse({ vue, onChoisir }: {
  vue: Vue; onChoisir: (v: Vue) => void;
}) {
  const c = useCouleurs();
  return (
    <>
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between" }}>
        <T v="titreGrand">Analyse</T>
        <Logo hauteur={38} />
      </View>
      <T v="petit" style={{ marginTop: 2, marginBottom: espace.l }}>
        Le point du matin, et ce que le robot a fait jusqu'ici.
      </T>
      <View style={{ flexDirection: "row", marginBottom: espace.l,
                     borderBottomWidth: 1, borderBottomColor: c.filet }}>
        {VUES.map(([cle, libelle]) => (
          <T
            key={cle}
            v="sousTitre"
            couleur={vue === cle ? c.encre : c.encrePale}
            style={{
              paddingVertical: espace.m, marginRight: espace.xl,
              borderBottomWidth: 2, marginBottom: -1,
              borderBottomColor: vue === cle ? c.jaune : "transparent",
            }}
            onPress={() => onChoisir(cle)}
          >
            {libelle}
          </T>
        ))}
      </View>
    </>
  );
}

export function EcranAnalyse({ versAbonnement }: {
  versAbonnement: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [vue, setVue] = React.useState<Vue>("note");

  const [note, setNote] = React.useState<NoteMarche | null>(null);
  const [perf, setPerf] = React.useState<Performance | null>(null);
  const [cache, setCache] = React.useState<string | null>(null);
  const [pret, setPret] = React.useState(false);
  const [rafraichit, setRafraichit] = React.useState(false);

  const charger = React.useCallback(async () => {
    const [rn, rp] = await Promise.all([api.note(), api.performance()]);
    setNote(rn.donnee?.note ?? null);
    setPerf(rp.donnee);
    const vieux = rn.duCache ? rn.ageMinutes : rp.duCache ? rp.ageMinutes : null;
    setCache(vieux !== null
      ? `Hors ligne — dernieres donnees ${ilYA(vieux)}` : null);
    setPret(true);
  }, []);

  React.useEffect(() => { charger(); }, [charger]);

  // La demonstration a trois montants vit ici plutot que d'occuper un
  // onglet a elle : c'est la meme question — « qu'est-ce que ca donne
  // sur la duree » — posee avant plutot qu'apres l'abonnement.
  if (vue === "demo") {
    return (
      <View style={{ flex: 1, backgroundColor: c.fond,
                     paddingTop: marges.top + espace.m }}>
        <View style={{ paddingHorizontal: espace.l }}>
          <EnteteAnalyse vue={vue} onChoisir={setVue} />
        </View>
        <EcranDemo versAbonnement={versAbonnement} />
      </View>
    );
  }

  if (!pret) {
    return (
      <ScrollView contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.l }}>
        <Squelette largeur="70%" hauteur={26} />
        <Squelette largeur="100%" hauteur={12} style={{ marginTop: espace.l }} />
        <Squelette largeur="94%" hauteur={12} style={{ marginTop: espace.s }} />
        <Squelette largeur="100%" hauteur={140}
                   style={{ marginTop: espace.xxl }} />
      </ScrollView>
    );
  }

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
      refreshControl={
        <RefreshControl refreshing={rafraichit} tintColor={c.jaune}
          onRefresh={async () => {
            setRafraichit(true); await charger(); setRafraichit(false);
          }} />
      }
    >
      <EnteteAnalyse vue={vue} onChoisir={setVue} />

      {cache ? <BandeauCache texte={cache} /> : null}

      {/* ---------------------------------------- la note du matin */}
      {note ? (
        <Carte>
          <T v="etiquette">Le point du matin</T>
          <T v="titre" style={{ marginTop: espace.s }}>{note.headline}</T>
          {note.body_fr.split("\n\n").map((para, i) => (
            <T key={i} v="corps" couleur={c.encreDouce}
               style={{ marginTop: espace.m }}>
              {para}
            </T>
          ))}

          <View style={{ marginTop: espace.xl, paddingTop: espace.l,
                         borderTopWidth: StyleSheet.hairlineWidth,
                         borderTopColor: c.filet }}>
            <Jauge titre="Tendance" valeur={note.trend_score} min={-100} max={100}
                   legende={note.trend_score === null ? undefined
                     : note.trend_score > 20 ? "en hausse"
                     : note.trend_score < -20 ? "en baisse" : "plat"} />
            <Jauge titre="Agitation du marche" valeur={note.volatility_score}
                   min={0} max={100}
                   legende={note.volatility_score === null ? undefined
                     : note.volatility_score > 60 ? "forte"
                     : note.volatility_score > 30 ? "moyenne" : "calme"} />
            <Jauge titre="Peur et avidite" valeur={note.fear_greed}
                   min={0} max={100}
                   legende={note.fear_greed === null ? undefined
                     : `${note.fear_greed} sur 100`} />
            <Jauge titre="Part du bitcoin" valeur={note.btc_dominance}
                   min={30} max={70}
                   legende={note.btc_dominance === null ? undefined
                     : `${note.btc_dominance} %`} />
          </View>
        </Carte>
      ) : (
        <Vide titre="Pas de note aujourd'hui"
              detail={"Le point du matin n'est publie que lorsqu'il a " +
                      "quelque chose a dire. Rien a signaler est aussi " +
                      "une information."} />
      )}

      {/* --------------------------------------------- l'historique */}
      <T v="titre" style={{ marginTop: espace.xxl, marginBottom: espace.m }}>
        Historique des signaux
      </T>

      {perf?.fiable && perf.stats ? (
        <Carte>
          <T v="etiquette">
            Si on avait suivi les {perf.trades} signaux depuis le debut
          </T>
          <View style={{ flexDirection: "row", alignItems: "baseline",
                         marginTop: espace.s, marginBottom: espace.l }}>
            <T v="chiffre" style={{ fontSize: 28 }}>
              {euros(perf.stats.capital_final, 0)}
            </T>
            <T v="chiffre"
               couleur={perf.stats.variation_pct >= 0 ? c.gain : c.perte}
               style={{ fontSize: 16, marginLeft: espace.m }}>
              {pourcent(perf.stats.variation_pct)}
            </T>
          </View>

          <Courbe points={perf.courbe} />

          <View style={{ flexDirection: "row", justifyContent: "space-between",
                         marginTop: espace.s, marginBottom: espace.xl }}>
            <T v="legende">
              depart {euros(perf.depart ?? 10000, 0)}
            </T>
            <T v="legende">{perf.trades} trades</T>
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap",
                         justifyContent: "space-between" }}>
            <Statistique libelle="Trades gagnants"
                         valeur={`${perf.stats.taux_reussite} %`} />
            {/* LE RECUL MAXIMUM A LA MEME TAILLE QUE LE GAIN.
                Ne montrer que la hausse est un mensonge par omission. */}
            <Statistique libelle="Pire recul"
                         valeur={`-${perf.stats.recul_max_pct} %`}
                         couleur={c.perte} />
            <Statistique libelle="Gain moyen"
                         valeur={euros(perf.stats.gain_moyen)}
                         couleur={c.gain} />
            <Statistique libelle="Perte moyenne"
                         valeur={euros(perf.stats.perte_moyenne)}
                         couleur={c.perte} />
          </View>

          {/* Les hypotheses SOUS la courbe, pas derriere un lien. */}
          <View style={{ paddingTop: espace.m,
                         borderTopWidth: StyleSheet.hairlineWidth,
                         borderTopColor: c.filet }}>
            <T v="etiquette">Ce que ce calcul suppose</T>
            {(perf.hypotheses ?? []).map((h, i) => (
              <T key={i} v="legende" style={{ marginTop: espace.xs,
                                              lineHeight: 16 }}>
                • {h}
              </T>
            ))}
          </View>
        </Carte>
      ) : (
        <Carte>
          <T v="sousTitre" couleur={c.encreDouce}>
            Pas encore assez d'historique
          </T>
          <T v="petit" style={{ marginTop: espace.s }}>
            {perf?.message ??
             "L'historique apparaitra quand il y aura de quoi le juger."}
          </T>
          <T v="petit" style={{ marginTop: espace.m }}>
            Une courbe tracee sur une poignee de trades ne prouve rien :
            une bonne serie de chance ressemble exactement a un bon
            systeme. Nous prefererons t'afficher ce message quelques
            semaines de plus.
          </T>
        </Carte>
      )}

      <Separateur marge={espace.xl} />
      <T v="legende" style={{ textAlign: "center", lineHeight: 17 }}>
        Les resultats passes ne prejugent pas des resultats futurs.
        Cette simulation ne tient pas compte des frais de ta plateforme.
      </T>
    </ScrollView>
  );
}
