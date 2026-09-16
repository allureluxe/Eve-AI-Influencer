/**
 * Le mode demonstration : essayer avant de payer.
 *
 * CE QUE LA DEMO MONTRE, ET CE QU'ELLE NE MONTRE PAS
 * --------------------------------------------------
 * Elle rejoue les signaux REELS deja clotures sur trois montants de
 * depart, et affiche ce que ca aurait donne. Rien n'est invente : les
 * chiffres viennent de la meme base que l'historique, et la meme
 * barriere s'applique — sous 30 trades clotures, aucune courbe n'est
 * affichee.
 *
 * C'est la difference entre une demonstration et une vitrine truquee.
 * Une demonstration montre du passe verifiable ; une vitrine truquee
 * montre un avenir choisi. Beaucoup d'applications du genre proposent
 * un « mode demo » qui simule des gains fictifs pour donner envie —
 * c'est exactement ce qu'on ne fait pas, et c'est aussi ce qui rend
 * l'application defendable devant le Play Store.
 *
 * ELLE AFFICHE AUSSI LE PIRE MOMENT. Un utilisateur qui decouvre en
 * demonstration qu'il aurait vu son capital baisser de 18 % avant de
 * remonter est un utilisateur qui ne se desabonnera pas au premier
 * mauvais mois.
 */

import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Line, Path } from "react-native-svg";
import { api, Performance } from "../services/api";
import { euros, pourcent } from "../services/format";
import { enregistrerCapital } from "../services/reglages";
import { espace, rayon, TRAIT } from "../../theme";
import {
  Bouton, Carte, EnTete, Etiquette, Separateur, Squelette, T, useCouleurs,
} from "../../composants/base";

/** Les trois montants proposes. */
const MONTANTS = [500, 2000, 10000];

function Courbe({ points, depart }: {
  points: { capital: number }[]; depart: number;
}) {
  const c = useCouleurs();
  const L = 320, H = 140;
  if (points.length < 2) return null;

  const valeurs = points.map((p) => p.capital);
  const bas = Math.min(...valeurs, depart);
  const haut = Math.max(...valeurs, depart);
  const amplitude = haut - bas || 1;
  const x = (i: number) => (i / (points.length - 1)) * L;
  const y = (v: number) => H - ((v - bas) / amplitude) * (H - 10) - 5;

  return (
    <Svg width="100%" height={H} viewBox={`0 0 ${L} ${H}`}
         preserveAspectRatio="none">
      {/* Le capital de depart. Sans cette ligne, une courbe qui descend
          peut ressembler a une courbe qui monte. */}
      <Line x1={0} y1={y(depart)} x2={L} y2={y(depart)}
            stroke={c.filetDoux} strokeWidth={1} strokeDasharray="3 4" />
      <Path
        d={valeurs.map((v, i) =>
          `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
        stroke={c.jaune} strokeWidth={2.5} fill="none"
        strokeLinejoin="round" strokeLinecap="round"
      />
    </Svg>
  );
}

export function EcranDemo({ versAbonnement }: { versAbonnement: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [perf, setPerf] = React.useState<Performance | null>(null);
  const [pret, setPret] = React.useState(false);
  const [montant, setMontant] = React.useState(MONTANTS[0]);

  React.useEffect(() => {
    api.performance().then((r) => { setPerf(r.donnee); setPret(true); });
  }, []);

  if (!pret) {
    return (
      <ScrollView contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.l }}>
        <Squelette largeur="55%" hauteur={28} />
        <Squelette largeur="100%" hauteur={180}
                   style={{ marginTop: espace.xl }} />
      </ScrollView>
    );
  }

  // LE SERVEUR CALCULE SUR 10 000 EUR. On remet a l'echelle du montant
  // choisi — c'est une simple proportion, puisque chaque position est
  // dimensionnee en pourcentage du capital. Recalculer trade par trade
  // ici donnerait le meme resultat en dupliquant la logique du serveur,
  // et les deux finiraient par diverger.
  const echelle = perf?.depart ? montant / perf.depart : 0;
  const courbe = (perf?.courbe ?? []).map((p) => ({
    capital: p.capital * echelle,
  }));
  const s = perf?.stats;

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <EnTete
        titre="Essayer"
        sousTitre="Ce que les signaux deja publies auraient donne, selon la somme de depart."
      />

      {/* Les trois montants. */}
      <View style={{ flexDirection: "row", marginBottom: espace.xl }}>
        {MONTANTS.map((m) => {
          const actif = m === montant;
          return (
            <T
              key={m}
              v="sousTitre"
              couleur={actif ? c.surJaune : c.encre}
              onPress={() => setMontant(m)}
              style={{
                flex: 1, textAlign: "center",
                backgroundColor: actif ? c.jaune : "transparent",
                borderWidth: TRAIT,
                borderColor: actif ? c.jaune : c.filetDoux,
                borderRadius: rayon.s,
                paddingVertical: espace.m,
                marginRight: m === MONTANTS[MONTANTS.length - 1] ? 0 : espace.s,
                overflow: "hidden",
              }}
            >
              {euros(m, 0)}
            </T>
          );
        })}
      </View>

      {perf?.fiable && s ? (
        <>
          <Carte>
            <Etiquette>
              {euros(montant, 0)} places au debut seraient devenus
            </Etiquette>
            <View style={{ flexDirection: "row", alignItems: "baseline",
                           marginTop: espace.s, marginBottom: espace.l }}>
              <T v="chiffre" style={{ fontSize: 32 }}>
                {euros(s.capital_final * echelle, 0)}
              </T>
              <T v="chiffre"
                 couleur={s.variation_pct >= 0 ? c.gain : c.perte}
                 style={{ fontSize: 17, marginLeft: espace.m }}>
                {pourcent(s.variation_pct)}
              </T>
            </View>

            <Courbe points={courbe} depart={montant} />

            <View style={{ flexDirection: "row",
                           justifyContent: "space-between",
                           marginTop: espace.s }}>
              <T v="legende">depart {euros(montant, 0)}</T>
              <T v="legende">{perf.trades} trades termines</T>
            </View>
          </Carte>

          {/* LE PIRE MOMENT, EN EUROS. C'est le chiffre qu'aucune
              demonstration n'affiche, et c'est celui qui evite les
              desabonnements au premier mauvais mois. */}
          <Carte style={{ marginTop: espace.m }} couleurAccent={c.perte}>
            <Etiquette>Le pire moment du parcours</Etiquette>
            <T v="chiffre" couleur={c.perte}
               style={{ fontSize: 26, marginTop: espace.xs }}>
              -{euros(montant * s.recul_max_pct / 100, 0)}
            </T>
            <T v="petit" style={{ marginTop: espace.s }}>
              A un moment, le capital est descendu de {s.recul_max_pct} %
              sous son plus haut. C'est normal et ca se reproduira :
              la methode gagne sur quelques gros trades et perd un peu,
              souvent, entre-temps.
            </T>
            <T v="petit" style={{ marginTop: espace.s }}>
              Si voir {euros(montant * s.recul_max_pct / 100, 0)} partir
              te ferait tout arreter, prends un montant plus petit.
            </T>
          </Carte>

          <View style={{ flexDirection: "row", flexWrap: "wrap",
                         marginTop: espace.l }}>
            {[
              ["Trades gagnants", `${s.taux_reussite} %`, undefined],
              ["Gain moyen", euros(s.gain_moyen * echelle), c.gain],
              ["Perte moyenne", euros(s.perte_moyenne * echelle), c.perte],
              ["Pour 1 € perdu", s.facteur_profit
                ? `${s.facteur_profit} € gagnes` : "—", undefined],
            ].map(([libelle, valeur, couleur]) => (
              <View key={libelle as string}
                    style={{ width: "50%", marginBottom: espace.l }}>
                <Etiquette>{libelle}</Etiquette>
                <T v="chiffre" couleur={couleur as string | undefined}
                   style={{ fontSize: 19, marginTop: 3 }}>
                  {valeur}
                </T>
              </View>
            ))}
          </View>

          <Carte>
            <Etiquette>Ce que ce calcul suppose</Etiquette>
            {(perf.hypotheses ?? []).map((h, i) => (
              <T key={i} v="legende" style={{ marginTop: espace.xs,
                                              lineHeight: 16 }}>
                • {h}
              </T>
            ))}
            <T v="legende" style={{ marginTop: espace.xs, lineHeight: 16 }}>
              • Un utilisateur reel gagnerait moins : les frais de
              plateforme ne sont pas deduits.
            </T>
          </Carte>

          <View style={{ marginTop: espace.xl }}>
            <Bouton
              titre={`Continuer avec ${euros(montant, 0)}`}
              onPress={() => { enregistrerCapital(montant); versAbonnement(); }}
            />
            <T v="legende" style={{ textAlign: "center",
                                    marginTop: espace.s }}>
              Enregistre ce montant pour que chaque signal t'affiche ce
              qu'il peut te couter en euros.
            </T>
          </View>
        </>
      ) : (
        <Carte>
          <T v="sousTitre" couleur={c.encreDouce}>
            Pas encore assez d'historique pour une demonstration
          </T>
          <T v="petit" style={{ marginTop: espace.s }}>
            {perf?.message ??
             "Il faut des trades termines pour montrer quelque chose."}
          </T>
          <T v="petit" style={{ marginTop: espace.m }}>
            Nous pourrions afficher une courbe inventee, comme le font
            beaucoup d'applications de ce genre. Nous prefererons
            t'afficher ce message quelques semaines de plus.
          </T>
        </Carte>
      )}

      <Separateur marge={espace.xl} />
      <T v="legende" style={{ textAlign: "center", lineHeight: 17 }}>
        Simulation calculee sur les signaux reellement publies. Les
        resultats passes ne prejugent pas des resultats futurs.
      </T>
    </ScrollView>
  );
}
