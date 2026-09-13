/**
 * Les trois ecrans du premier lancement.
 *
 * CE QU'ILS DISENT, ET POURQUOI DANS CET ORDRE
 * --------------------------------------------
 * L'ordre habituel serait : ce que l'application apporte, puis les
 * precautions en petit a la fin. On fait l'inverse au deuxieme ecran.
 *
 * Quelqu'un qui installe une application de signaux crypto a deja vu
 * passer des arnaques. Sa premiere question n'est pas « qu'est-ce que
 * ca m'apporte », c'est « qu'est-ce que ca va me prendre ». Y repondre
 * tout de suite, avant qu'il ait a le demander, est ce qui distingue
 * l'application qu'on garde de celle qu'on desinstalle.
 *
 * Le troisieme ecran est le plus utile de tous : il explique comment
 * passer un ordre. Une application qui donne des signaux sans dire quoi
 * en faire laisse l'utilisateur bloque au premier — et il ne revient
 * pas.
 */

import React from "react";
import { Dimensions, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace, polices, rayon, taille, TRAIT } from "../theme";
import { Bouton, Logo, T, useCouleurs } from "../composants/base";

const { width: LARGEUR } = Dimensions.get("window");

interface Page {
  eyebrow: string;
  titre: string;
  paragraphes: string[];
}

const PAGES: Page[] = [
  {
    eyebrow: "Ce qu'Allure fait",
    titre: "Un robot qui trade son propre argent, et qui te montre tout",
    paragraphes: [
      "Allure suit un robot qui achete et vend des cryptos avec un vrai " +
      "compte. Chaque fois qu'il ouvre une position, tu la vois : la " +
      "crypto, le prix, la protection, et pourquoi.",
      "Tu vois aussi quand il perd. C'est le meme flux, sans tri.",
    ],
  },
  {
    eyebrow: "Ce qu'Allure ne fait pas",
    titre: "Allure ne touche jamais a ton argent",
    paragraphes: [
      "Aucune connexion a ton compte, aucun ordre passe a ta place, " +
      "aucune cle d'echange demandee. Personne de serieux ne t'en " +
      "demandera jamais.",
      "Allure ne promet aucun gain et ne te dit pas quoi faire. Elle " +
      "publie ce qu'un robot fait, tu decides du reste.",
    ],
  },
  {
    eyebrow: "Comment s'en servir",
    titre: "Le signal arrive, tu passes l'ordre toi-meme",
    paragraphes: [
      "Ouvre ton application Bitvavo ou Binance, cherche la crypto " +
      "indiquee, et passe un ordre d'achat au marche pour le montant " +
      "que tu as decide.",
      "Place ensuite un ordre stop au prix de protection affiche. " +
      "C'est lui qui limite ce que le trade peut te couter — c'est " +
      "l'etape que les debutants sautent, et c'est celle qui compte le " +
      "plus.",
      "Indique ton capital dans l'onglet Compte : chaque signal " +
      "t'affichera alors, en euros, ce qu'il peut te couter au pire.",
    ],
  },
];

export function EcranAccueil({ onTermine }: { onTermine: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [page, setPage] = React.useState(0);
  const defilement = React.useRef<ScrollView>(null);

  const dernier = page === PAGES.length - 1;

  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   paddingTop: marges.top, paddingBottom: marges.bottom }}>
      <ScrollView
        ref={defilement}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={(e) =>
          setPage(Math.round(e.nativeEvent.contentOffset.x / LARGEUR))}
      >
        {PAGES.map((p, i) => (
          <View key={i} style={{ width: LARGEUR, paddingHorizontal: espace.xl,
                                 justifyContent: "center" }}>
            {/* Un chiffre discret : il situe dans une sequence de trois,
                ce qui rassure sur la longueur de l'introduction. */}
            <View style={{ flexDirection: "row", alignItems: "center",
                           justifyContent: "space-between",
                           marginBottom: espace.l }}>
              <T v="chiffre" couleur={c.encrePale} style={{ fontSize: 13 }}>
                {i + 1} / {PAGES.length}
              </T>
              {i === 0 ? <Logo hauteur={38} /> : null}
            </View>

            <T v="etiquette" couleur={c.jaune}>{p.eyebrow}</T>

            <T style={{
              fontFamily: polices.titre, fontSize: 32, color: c.encre,
              lineHeight: 40, marginTop: espace.m, marginBottom: espace.xl,
            }}>
              {p.titre}
            </T>

            <View style={{ width: 40, height: TRAIT,
                           backgroundColor: c.jaune,
                           marginBottom: espace.xl }} />

            {p.paragraphes.map((texte, j) => (
              <T key={j} v="corps" couleur={c.encreDouce}
                 style={{ marginBottom: espace.l, fontSize: 16,
                          lineHeight: 26 }}>
                {texte}
              </T>
            ))}
          </View>
        ))}
      </ScrollView>

      <View style={{ paddingHorizontal: espace.xl, paddingBottom: espace.l }}>
        <View style={{ flexDirection: "row", justifyContent: "center",
                       marginBottom: espace.l }}>
          {PAGES.map((_, i) => (
            <View key={i} style={{
              width: i === page ? 18 : 6, height: 3,
              borderRadius: rayon.rond, marginHorizontal: 3,
              backgroundColor: i === page ? c.jaune : c.filet,
            }} />
          ))}
        </View>

        <Bouton
          titre={dernier ? "Commencer" : "Suivant"}
          onPress={() => {
            if (dernier) { onTermine(); return; }
            defilement.current?.scrollTo({
              x: (page + 1) * LARGEUR, animated: true });
            setPage(page + 1);
          }}
        />

        {!dernier ? (
          <T v="petit" couleur={c.encrePale}
             style={{ textAlign: "center", marginTop: espace.m }}
             onPress={onTermine}>
            Passer
          </T>
        ) : (
          <View style={{ height: taille.petit + espace.m }} />
        )}
      </View>
    </View>
  );
}
