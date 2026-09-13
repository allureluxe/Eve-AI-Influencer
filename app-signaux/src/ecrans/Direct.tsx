/**
 * Onglet Direct — les positions du robot, en train de vivre.
 *
 * C'EST L'ECRAN QUI DONNE ENVIE DE REVENIR.
 * Les autres montrent des decisions passees ; celui-ci montre de
 * l'argent qui bouge en ce moment. C'est aussi le plus dangereux :
 * afficher un gain courant en vert vif et en gros donne exactement
 * l'impression d'arnaque qu'on veut eviter.
 *
 * Trois garde-fous tenus ici :
 *
 *   1. LA VARIATION N'EST JAMAIS UNE PROMESSE. On ecrit « en cours »,
 *      jamais « gagne ». Une position ouverte ne rapporte rien tant
 *      qu'elle n'est pas fermee, et l'ecran le rappelle en toutes
 *      lettres.
 *   2. L'HEURE DE LA COTATION EST AFFICHEE. Laisser croire au temps
 *      reel strict quand on rafraichit toutes les dix secondes serait
 *      un petit mensonge qui en autorise de plus gros.
 *   3. « A L'ABRI » EST L'INFORMATION MISE EN AVANT, pas le gain. Le
 *      robot remonte ses protections ; quand la protection passe
 *      au-dessus du prix d'achat, la position ne peut plus rien
 *      couter. C'est verifiable, c'est rassurant, et personne ne
 *      l'affiche.
 */

import React from "react";
import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, ilYA, PositionDirecte, ReponseDirect } from "../services/api";
import { euros, nomCrypto, perteMax, pourcent, prix, symbole }
  from "../services/format";
import { useCapital } from "../services/reglages";
import { espace, rayon, TRAIT } from "../theme";
import {
  BandeauCache, Bouton, Carte, Etiquette, Separateur, Squelette, T,
  useCouleurs, Vide,
} from "../composants/base";

/** Le rythme de rafraichissement. Dix secondes : le cache serveur aussi. */
const RYTHME_MS = 10_000;

function Position({ p, capital }: { p: PositionDirecte; capital: number }) {
  const c = useCouleurs();
  const variation = p.variation_pct;
  const couleur = variation === null ? c.encreDouce
    : variation > 0 ? c.gain : variation < 0 ? c.perte : c.encreDouce;

  // Ce que la position vaut en euros pour CE capital. La conversion
  // est ce qui rend l'ecran comprehensible : « +1,8 % » ne parle a
  // personne, « +4,20 € en cours » parle a tout le monde.
  const engage = p.position_size_pct !== null && p.entry_price > 0
    ? perteMax(p.position_size_pct, capital)
      / (Math.abs(p.entry_price - p.stop_loss) / p.entry_price)
    : 0;
  const enEuros = variation === null ? null : engage * variation / 100;

  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between",
                     alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <T v="titre">{nomCrypto(p.pair)}</T>
          <T v="legende" style={{ marginTop: 2 }}>
            {symbole(p.pair)} · achete a {prix(p.entry_price)}
          </T>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <T v="chiffre" couleur={couleur} style={{ fontSize: 24 }}>
            {variation === null ? "—" : pourcent(variation)}
          </T>
          {enEuros !== null ? (
            <T v="chiffre" couleur={couleur} style={{ fontSize: 14 }}>
              {enEuros >= 0 ? "+" : ""}{euros(enEuros)}
            </T>
          ) : null}
          {/* JAMAIS « gagne ». Une position ouverte ne rapporte rien. */}
          <T v="legende">en cours</T>
        </View>
      </View>

      {/* La protection : l'information qui compte vraiment. */}
      <View style={{
        marginTop: espace.l, padding: espace.m,
        backgroundColor: p.a_l_abri ? c.jaunePale : c.creux,
        borderLeftWidth: TRAIT,
        borderLeftColor: p.a_l_abri ? c.jaune : c.filetDoux,
      }}>
        {p.a_l_abri ? (
          <>
            <T v="sousTitre" couleur={c.olive}>Cette position est a l'abri</T>
            <T v="petit" style={{ marginTop: 2 }}>
              Le robot a remonte sa protection au-dessus du prix d'achat.
              Meme si le cours retombe, ce trade ne peut plus rien couter.
            </T>
          </>
        ) : (
          <>
            <T v="etiquette">Protection a {prix(p.stop_loss)}</T>
            <T v="petit" style={{ marginTop: 2 }}>
              {p.distance_stop_pct !== null
                ? `Le cours doit encore baisser de ${
                    p.distance_stop_pct.toFixed(1).replace(".", ",")} % ` +
                  `avant que le robot ne sorte.`
                : "Le robot sort automatiquement a ce prix."}
            </T>
          </>
        )}
      </View>

      <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.m }}>
        {p.rationale}
      </T>
    </Carte>
  );
}

export function EcranDirect({ versAbonnement }: { versAbonnement: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const capital = useCapital();

  const [data, setData] = React.useState<ReponseDirect | null>(null);
  const [cache, setCache] = React.useState<string | null>(null);
  const [pret, setPret] = React.useState(false);
  const [rafraichit, setRafraichit] = React.useState(false);

  const charger = React.useCallback(async () => {
    const r = await api.direct();
    setData(r.donnee);
    setCache(r.duCache && r.ageMinutes !== null
      ? `Hors ligne — dernieres donnees ${ilYA(r.ageMinutes)}` : null);
    setPret(true);
  }, []);

  React.useEffect(() => { charger(); }, [charger]);
  React.useEffect(() => {
    const t = setInterval(charger, RYTHME_MS);
    return () => clearInterval(t);
  }, [charger]);

  if (!pret) {
    return (
      <ScrollView contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.l }}>
        <Squelette largeur="45%" hauteur={28} />
        {[0, 1].map((i) => (
          <Squelette key={i} largeur="100%" hauteur={170}
                     style={{ marginTop: espace.l }} />
        ))}
      </ScrollView>
    );
  }

  const positions = data?.positions ?? [];
  const total = positions.reduce((s, p) => {
    if (p.variation_pct === null || p.position_size_pct === null) return s;
    const engage = perteMax(p.position_size_pct, capital)
      / (Math.abs(p.entry_price - p.stop_loss) / p.entry_price);
    return s + engage * p.variation_pct / 100;
  }, 0);

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
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between" }}>
        <T v="titreGrand">Direct</T>
        {/* Le point qui bat. Discret, mais il dit que ca vit. */}
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={{ width: 6, height: 6, borderRadius: rayon.rond,
                         backgroundColor: data?.cotations_disponibles
                           ? c.jaune : c.encrePale, marginRight: espace.s }} />
          <T v="legende">
            {data?.cotations_disponibles ? "cours en direct" : "cours indisponibles"}
          </T>
        </View>
      </View>
      <T v="petit" style={{ marginTop: 2, marginBottom: espace.l }}>
        Ce que le robot a d'ouvert en ce moment, au cours actuel.
      </T>

      {cache ? <BandeauCache texte={cache} /> : null}

      {positions.length > 0 ? (
        <View style={{
          borderTopWidth: TRAIT, borderBottomWidth: TRAIT,
          borderColor: c.filet, paddingVertical: espace.l,
          marginBottom: espace.l,
        }}>
          <Etiquette>Total en cours sur {euros(capital, 0)}</Etiquette>
          <T v="chiffre"
             couleur={total > 0 ? c.gain : total < 0 ? c.perte : c.encre}
             style={{ fontSize: 34, marginTop: espace.xs }}>
            {total >= 0 ? "+" : ""}{euros(total)}
          </T>
          {/* La phrase la plus importante de l'ecran. */}
          <T v="legende" style={{ marginTop: espace.s, lineHeight: 16 }}>
            Rien n'est acquis tant que les positions ne sont pas fermees.
            Ce montant peut encore monter ou descendre.
          </T>
        </View>
      ) : null}

      {positions.map((p) => (
        <Position key={p.id} p={p} capital={capital} />
      ))}

      {positions.length === 0 ? (
        <Vide
          titre="Le robot n'a rien d'ouvert"
          detail={
            "Il n'entre que quand les conditions sont reunies, environ " +
            "une fois par jour. Attendre fait partie de la methode : " +
            "c'est ce qui evite les mauvais trades."
          }
        />
      ) : null}

      {data && data.tier === "free" ? (
        <Carte style={{ marginTop: espace.m }} accent>
          <Etiquette>Les positions en direct</Etiquette>
          <T v="sousTitre" style={{ marginTop: espace.s }}>
            Tu vois ici les trois cryptos du compte gratuit, avec deux
            heures de retard
          </T>
          <T v="petit" style={{ marginTop: espace.s }}>
            Le direct complet — les 70 cryptos suivies, au moment ou le
            robot agit — fait partie de l'offre Plus.
          </T>
          <View style={{ marginTop: espace.l }}>
            <Bouton titre="Voir les offres" onPress={versAbonnement} />
          </View>
        </Carte>
      ) : null}

      <Separateur marge={espace.xl} />
      <T v="legende" style={{ textAlign: "center", lineHeight: 17 }}>
        Cours fournis par Bitvavo
        {data?.cotations_a
          ? `, mis a jour ${ilYA(Math.round(
              (Date.now() - Date.parse(data.cotations_a)) / 60_000))}`
          : ""}.
        {"\n"}Allure ne detient aucun fonds et ne passe aucun ordre a ta place.
      </T>
    </ScrollView>
  );
}
