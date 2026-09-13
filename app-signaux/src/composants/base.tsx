/**
 * Les briques visuelles ALLURE.
 *
 * LE FILET NOIR EPAIS EST LA SIGNATURE. La ou les applications du genre
 * posent des ombres douces et des coins tres arrondis pour paraitre
 * amicales, ALLURE trace des traits nets de 2 px. Ca se lit comme un
 * document imprime, pas comme une notification marketing — et c'est ce
 * qui fait qu'on la transmet.
 *
 * Un mot sur les ECRANS DE CHARGEMENT. Squelettes, jamais de roue qui
 * tourne : une roue dit « attends », un squelette dit « voila ce qui
 * arrive ». Sur un reseau mobile, c'est la difference entre une
 * application qui parait lente et une qui parait solide.
 */

import React, { createContext, useContext } from "react";
import {
  ActivityIndicator, Animated, Image, Pressable, StyleSheet, Text,
  useColorScheme, View, ViewStyle,
} from "react-native";
import { espace, palettes, polices, rayon, taille, Theme, TRAIT }
  from "../theme";

// ------------------------------------------------------------ theme

const ContexteTheme = createContext<Theme>("clair");

export function FournisseurTheme({ children }: { children: React.ReactNode }) {
  const systeme = useColorScheme();
  return (
    <ContexteTheme.Provider value={systeme === "dark" ? "sombre" : "clair"}>
      {children}
    </ContexteTheme.Provider>
  );
}

export function useCouleurs() {
  return palettes[useContext(ContexteTheme)];
}

export function useTheme() {
  return useContext(ContexteTheme);
}

// ------------------------------------------------------------ texte

type VarianteTexte = "titreGrand" | "titre" | "sousTitre" | "corps"
                   | "petit" | "legende" | "chiffre" | "etiquette";

export function T({ v = "corps", couleur, style, children, ...reste }: {
  v?: VarianteTexte;
  couleur?: string;
  style?: any;
  children: React.ReactNode;
  numberOfLines?: number;
  /** Un texte cliquable (onglet, lien). React Native le gere nativement. */
  onPress?: () => void;
  accessibilityRole?: "button" | "link" | "header";
}) {
  const c = useCouleurs();
  const styles: Record<VarianteTexte, any> = {
    titreGrand: { fontFamily: polices.titre, fontSize: taille.titreGrand,
                  color: c.encre, lineHeight: taille.titreGrand * 1.15 },
    titre: { fontFamily: polices.titre, fontSize: taille.titre,
             color: c.encre, lineHeight: taille.titre * 1.2 },
    sousTitre: { fontFamily: polices.interfaceGras, fontSize: taille.sousTitre,
                 color: c.encre, lineHeight: taille.sousTitre * 1.35 },
    corps: { fontFamily: polices.interface, fontSize: taille.corps,
             color: c.encre, lineHeight: taille.corps * 1.55 },
    petit: { fontFamily: polices.interface, fontSize: taille.petit,
             color: c.encreDouce, lineHeight: taille.petit * 1.5 },
    legende: { fontFamily: polices.interface, fontSize: taille.minuscule,
               color: c.encrePale, lineHeight: taille.minuscule * 1.4 },
    chiffre: { fontFamily: polices.chiffres, fontSize: taille.corps,
               color: c.encre, fontVariant: ["tabular-nums"] },
    // Petite, espacee, en capitales. Elle structure sans crier — le
    // contraire d'un badge colore.
    etiquette: { fontFamily: polices.interfaceGras, fontSize: taille.minuscule,
                 color: c.encrePale, letterSpacing: 1.2,
                 textTransform: "uppercase" },
  };
  return (
    <Text {...reste} style={[styles[v], couleur ? { color: couleur } : null, style]}>
      {children}
    </Text>
  );
}

/** Raccourci : le sur-titre de section. */
export function Etiquette({ children, style }: {
  children: React.ReactNode; style?: any;
}) {
  return <T v="etiquette" style={style}>{children}</T>;
}

// ------------------------------------------------------------ marque

/** Le logo ALLURE, a la taille demandee. */
export function Logo({ hauteur = 28 }: { hauteur?: number }) {
  return (
    <Image
      source={require("../../assets/logo-allure.png")}
      style={{ height: hauteur, width: hauteur * (128 / 111),
               resizeMode: "contain" }}
      accessibilityLabel="Allure"
    />
  );
}

/** L'en-tete de page : le titre, et le logo discret a droite. */
export function EnTete({ titre, sousTitre, droite }: {
  titre: string; sousTitre?: string; droite?: React.ReactNode;
}) {
  const c = useCouleurs();
  return (
    <View style={{ marginBottom: espace.l }}>
      <View style={{ flexDirection: "row", alignItems: "flex-start",
                     justifyContent: "space-between" }}>
        <T v="titreGrand" style={{ flex: 1 }}>{titre}</T>
        {droite ?? <Logo hauteur={26} />}
      </View>
      {sousTitre ? (
        <T v="petit" style={{ marginTop: 2 }}>{sousTitre}</T>
      ) : null}
      {/* Le filet fort sous le titre : la signature ALLURE. */}
      <View style={{ height: TRAIT, backgroundColor: c.filet,
                     marginTop: espace.m }} />
    </View>
  );
}

// ------------------------------------------------------------ cartes

/**
 * Une carte. Filet fin par defaut, filet JAUNE EPAIS a gauche si elle
 * doit attirer l'oeil. Pas d'ombre portee, pas de gros arrondi.
 */
export function Carte({ children, style, accent, couleurAccent }: {
  children: React.ReactNode;
  style?: ViewStyle;
  /** Marque la carte d'un filet jaune a gauche. */
  accent?: boolean;
  /** Remplace le jaune (resultat d'un trade, vigilance). */
  couleurAccent?: string;
}) {
  const c = useCouleurs();
  const marque = couleurAccent ?? (accent ? c.jaune : null);
  return (
    <View style={[{
      backgroundColor: c.surface,
      borderColor: c.filetDoux,
      borderWidth: StyleSheet.hairlineWidth,
      borderRadius: rayon.s,
      padding: espace.l,
      borderLeftWidth: marque ? TRAIT + 1 : StyleSheet.hairlineWidth,
      borderLeftColor: marque ?? c.filetDoux,
    }, style]}>
      {children}
    </View>
  );
}

export function Separateur({ marge = 0, fort }: {
  marge?: number; fort?: boolean;
}) {
  const c = useCouleurs();
  return <View style={{
    height: fort ? TRAIT : StyleSheet.hairlineWidth,
    backgroundColor: fort ? c.filet : c.filetDoux,
    marginVertical: marge,
  }} />;
}

// ---------------------------------------------------------- boutons

export function Bouton({ titre, onPress, variante = "plein", desactive }: {
  titre: string;
  onPress: () => void;
  variante?: "plein" | "contour" | "discret";
  desactive?: boolean;
}) {
  const c = useCouleurs();
  const plein = variante === "plein";
  return (
    <Pressable
      onPress={onPress}
      disabled={desactive}
      accessibilityRole="button"
      style={({ pressed }) => ({
        // LE BOUTON PLEIN EST JAUNE ALLURE, texte encre dessus. C'est
        // l'element le plus reconnaissable de la charte.
        backgroundColor: plein ? c.jaune : "transparent",
        borderColor: variante === "contour" ? c.filet : "transparent",
        borderWidth: variante === "contour" ? TRAIT : 0,
        borderRadius: rayon.s,
        paddingVertical: espace.m + 2,
        paddingHorizontal: espace.xl,
        alignItems: "center",
        opacity: desactive ? 0.35 : pressed ? 0.75 : 1,
      })}
    >
      <T v="sousTitre" couleur={plein ? c.surJaune : c.encre}>{titre}</T>
    </Pressable>
  );
}

// -------------------------------------------------------- squelettes

export function Squelette({ largeur = "100%", hauteur = 14, style }: {
  largeur?: number | string; hauteur?: number; style?: ViewStyle;
}) {
  const c = useCouleurs();
  const pulsation = React.useRef(new Animated.Value(0.4)).current;

  React.useEffect(() => {
    const boucle = Animated.loop(Animated.sequence([
      Animated.timing(pulsation, { toValue: 0.9, duration: 700,
                                   useNativeDriver: true }),
      Animated.timing(pulsation, { toValue: 0.4, duration: 700,
                                   useNativeDriver: true }),
    ]));
    boucle.start();
    return () => boucle.stop();
  }, [pulsation]);

  return (
    <Animated.View style={[{
      width: largeur as any, height: hauteur,
      backgroundColor: c.creux, borderRadius: rayon.s, opacity: pulsation,
    }, style]} />
  );
}

export function SqueletteCarte() {
  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Squelette largeur={110} hauteur={18} />
        <Squelette largeur={56} hauteur={18} />
      </View>
      <Squelette largeur="100%" hauteur={12} style={{ marginTop: espace.l }} />
      <Squelette largeur="82%" hauteur={12} style={{ marginTop: espace.s }} />
      <Squelette largeur="60%" hauteur={12} style={{ marginTop: espace.s }} />
    </Carte>
  );
}

// ------------------------------------------------------- etats vides

/**
 * L'ecran vide DIT POURQUOI, et ce n'est pas du confort.
 *
 * Le robot prend environ un signal par jour. Un utilisateur qui ouvre
 * l'application un jour calme voit une liste vide — et sans
 * explication, il conclut que l'application est cassee ou que
 * l'abonnement ne sert a rien. Une phrase transforme un bug apparent
 * en information.
 */
export function Vide({ titre, detail }: { titre: string; detail?: string }) {
  const c = useCouleurs();
  return (
    <View style={{ paddingVertical: espace.xxxl, paddingHorizontal: espace.l,
                   alignItems: "center" }}>
      <View style={{ width: 34, height: TRAIT, backgroundColor: c.jaune,
                     marginBottom: espace.l }} />
      <T v="sousTitre" couleur={c.encreDouce} style={{ textAlign: "center" }}>
        {titre}
      </T>
      {detail ? (
        <T v="petit" style={{ textAlign: "center", marginTop: espace.s,
                              maxWidth: 300 }}>
          {detail}
        </T>
      ) : null}
    </View>
  );
}

export function BandeauCache({ texte }: { texte: string }) {
  const c = useCouleurs();
  return (
    <View style={{
      backgroundColor: c.creux, paddingVertical: espace.s,
      paddingHorizontal: espace.l, borderRadius: rayon.s,
      marginBottom: espace.m, flexDirection: "row", alignItems: "center",
      borderLeftWidth: TRAIT, borderLeftColor: c.encrePale,
    }}>
      <T v="petit">{texte}</T>
    </View>
  );
}

export function Chargement() {
  const c = useCouleurs();
  return (
    <View style={{ padding: espace.xxl, alignItems: "center" }}>
      <ActivityIndicator color={c.jaune} />
    </View>
  );
}
