/**
 * Les briques visuelles communes.
 *
 * Un mot sur les ECRANS DE CHARGEMENT. La specification demande des
 * squelettes plutot qu'une roue qui tourne, et c'est plus qu'une
 * preference : une roue dit « attends », un squelette dit « voila ce
 * qui arrive ». Sur un reseau mobile, la difference entre les deux est
 * celle entre une application qui parait lente et une qui parait
 * solide.
 */

import React, { createContext, useContext } from "react";
import {
  ActivityIndicator, Animated, Pressable, StyleSheet, Text,
  useColorScheme, View, ViewStyle,
} from "react-native";
import { espace, palettes, polices, rayon, taille, Theme } from "../theme";

// ------------------------------------------------------------ theme

const ContexteTheme = createContext<Theme>("sombre");

export function FournisseurTheme({ children }: { children: React.ReactNode }) {
  const systeme = useColorScheme();
  return (
    <ContexteTheme.Provider value={systeme === "light" ? "clair" : "sombre"}>
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
                  color: c.encre, lineHeight: taille.titreGrand * 1.2 },
    titre: { fontFamily: polices.titre, fontSize: taille.titre,
             color: c.encre, lineHeight: taille.titre * 1.25 },
    sousTitre: { fontFamily: polices.interfaceGras, fontSize: taille.sousTitre,
                 color: c.encre },
    corps: { fontFamily: polices.interface, fontSize: taille.corps,
             color: c.encre, lineHeight: taille.corps * 1.55 },
    petit: { fontFamily: polices.interface, fontSize: taille.petit,
             color: c.encreDouce, lineHeight: taille.petit * 1.5 },
    legende: { fontFamily: polices.interface, fontSize: taille.minuscule,
               color: c.encrePale },
    chiffre: { fontFamily: polices.chiffres, fontSize: taille.corps,
               color: c.encre, fontVariant: ["tabular-nums"] },
    // Une etiquette : petite, espacee, en capitales. Elle structure
    // sans crier — le contraire d'un badge colore.
    etiquette: { fontFamily: polices.interfaceGras, fontSize: taille.minuscule,
                 color: c.encrePale, letterSpacing: 1.1,
                 textTransform: "uppercase" },
  };
  return (
    <Text {...reste} style={[styles[v], couleur ? { color: couleur } : null, style]}>
      {children}
    </Text>
  );
}

// ------------------------------------------------------------ cartes

/**
 * Une carte. Pas d'ombre portee, pas de coin tres arrondi : un FILET.
 *
 * Les ombres et les gros arrondis sont la signature visuelle des
 * applications qui veulent paraitre amicales. Un filet fin ressemble a
 * une fiche de dossier, et c'est ce qu'on veut ici.
 */
export function Carte({ children, style, accent }: {
  children: React.ReactNode;
  style?: ViewStyle;
  /** Un filet vertical a gauche, pour marquer une categorie. */
  accent?: string;
}) {
  const c = useCouleurs();
  return (
    <View style={[{
      backgroundColor: c.surface,
      borderColor: c.filet,
      borderWidth: StyleSheet.hairlineWidth,
      borderRadius: rayon.m,
      padding: espace.l,
      borderLeftWidth: accent ? 3 : StyleSheet.hairlineWidth,
      borderLeftColor: accent ?? c.filet,
    }, style]}>
      {children}
    </View>
  );
}

export function Separateur({ marge = 0 }: { marge?: number }) {
  const c = useCouleurs();
  return <View style={{ height: StyleSheet.hairlineWidth,
                        backgroundColor: c.filet, marginVertical: marge }} />;
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
        backgroundColor: plein ? c.laiton : "transparent",
        borderColor: variante === "contour" ? c.laiton : "transparent",
        borderWidth: variante === "contour" ? 1 : 0,
        borderRadius: rayon.s,
        paddingVertical: espace.m + 2,
        paddingHorizontal: espace.xl,
        alignItems: "center",
        opacity: desactive ? 0.4 : pressed ? 0.75 : 1,
      })}
    >
      <T v="sousTitre" couleur={plein ? c.surLaiton : c.laiton}>{titre}</T>
    </Pressable>
  );
}

// -------------------------------------------------------- squelettes

/** Un bloc gris qui respire, en attendant la donnee. */
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

/** Le squelette d'une carte de signal : la forme de ce qui arrive. */
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
 * L'ecran vide. Il DIT POURQUOI, et ce n'est pas du confort.
 *
 * Le robot prend environ un signal par jour. Un utilisateur qui ouvre
 * l'application un jour calme voit une liste vide — et sans explication,
 * il conclut que l'application est cassee ou que l'abonnement ne sert a
 * rien. Une phrase suffit a transformer un bug apparent en information.
 */
export function Vide({ titre, detail }: { titre: string; detail?: string }) {
  const c = useCouleurs();
  return (
    <View style={{ paddingVertical: espace.xxxl, paddingHorizontal: espace.l,
                   alignItems: "center" }}>
      <View style={{ width: 34, height: StyleSheet.hairlineWidth,
                     backgroundColor: c.filet, marginBottom: espace.l }} />
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

/** Le bandeau « donnees du cache », affiche hors ligne. */
export function BandeauCache({ texte }: { texte: string }) {
  const c = useCouleurs();
  return (
    <View style={{
      backgroundColor: c.creux, paddingVertical: espace.s,
      paddingHorizontal: espace.l, borderRadius: rayon.s,
      marginBottom: espace.m, flexDirection: "row", alignItems: "center",
    }}>
      <View style={{ width: 5, height: 5, borderRadius: rayon.rond,
                     backgroundColor: c.encrePale, marginRight: espace.s }} />
      <T v="petit">{texte}</T>
    </View>
  );
}

export function Chargement() {
  const c = useCouleurs();
  return (
    <View style={{ padding: espace.xxl, alignItems: "center" }}>
      <ActivityIndicator color={c.laiton} />
    </View>
  );
}
