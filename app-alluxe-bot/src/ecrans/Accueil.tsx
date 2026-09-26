/**
 * Page d'accueil -- le point d'entree unique de l'application.
 *
 * DECISION DU 15 SEPTEMBRE, APPLIQUEE LE 16 : au lieu de plusieurs
 * applications separees (Alluxbot, Allure, Luna, l'agent), une seule
 * application avec 4 gros boutons empiles verticalement. Chaque bouton
 * ouvre son propre sous-navigateur (voir App.tsx). Luna et l'Agent ne
 * sont pas encore construits -- meme etat "bientot disponible" que
 * Discussion.tsx, pas de fausse promesse de contenu.
 */
import React from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace, rayon } from "../theme";
import { Logo, T, useCouleurs, useReglageTheme, Preference } from "../composants/base";

interface Section {
  cle: "Alluxbot" | "Allure" | "Luna" | "Laboratoire" | "Agent";
  titre: string;
  detail: string;
  icone: keyof typeof Ionicons.glyphMap;
  disponible: boolean;
}

const SECTIONS: Section[] = [
  {
    cle: "Alluxbot", titre: "Bot",
    detail: "Le pilotage prive du robot : positions, historique, objectifs, alertes.",
    icone: "flash-outline", disponible: true,
  },
  {
    cle: "Allure", titre: "Signaux",
    detail: "L'application publique des signaux, en mode administrateur.",
    icone: "list-outline", disponible: true,
  },
  {
    cle: "Luna", titre: "Luna",
    detail: "L'influenceuse IA : son personnage, ses posts generes.",
    icone: "sparkles-outline", disponible: true,
  },
  {
    cle: "Laboratoire", titre: "Laboratoire",
    detail: "Le moteur qui apprend, teste et valide de nouvelles stratégies en parallèle.",
    icone: "flask-outline", disponible: true,
  },
  {
    cle: "Agent", titre: "Agent",
    detail: "Alluxe : demande-lui l'etat du robot, des alertes, de Luna.",
    icone: "mic-outline", disponible: true,
  },
];

function BoutonSection({ section, onPress }: {
  section: Section; onPress: () => void;
}) {
  const c = useCouleurs();
  return (
    <Pressable
      onPress={section.disponible ? onPress : undefined}
      accessibilityRole="button"
      style={({ pressed }) => ({
        flexDirection: "row", alignItems: "center",
        backgroundColor: c.surface,
        borderRadius: rayon.l,
        padding: espace.l,
        marginBottom: espace.m,
        minHeight: 96,
        opacity: section.disponible ? (pressed ? 0.8 : 1) : 0.55,
        shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 12,
        shadowOffset: { width: 0, height: 4 }, elevation: 2,
      })}
    >
      <View style={{
        width: 56, height: 56, borderRadius: rayon.m,
        backgroundColor: c.jauneAplat, alignItems: "center", justifyContent: "center",
        marginRight: espace.l,
      }}>
        <Ionicons name={section.icone} size={28} color={c.surJaune} />
      </View>
      <View style={{ flex: 1 }}>
        <T v="sousTitre">{section.titre}</T>
        <T v="petit" couleur={c.encreDouce} style={{ marginTop: 2 }}>
          {section.disponible ? section.detail : "Bientot disponible"}
        </T>
      </View>
      {section.disponible && (
        <Ionicons name="chevron-forward" size={22} color={c.encrePale} />
      )}
    </Pressable>
  );
}

/** Le choix du theme : clair, sombre, ou automatique la nuit.
 *
 *  Le theme sombre existait depuis toujours mais etait SUBI -- impose
 *  par le reglage du telephone, d'ou son debranchement le 13 sept.
 *  ("le fond blanc, pas noir"). Ici c'est un choix, avec "Auto" par
 *  defaut : sombre de 20 h a 7 h, sans rien avoir a toucher. */
function ChoixTheme() {
  const c = useCouleurs();
  const { preference, choisir } = useReglageTheme();
  const options: { cle: Preference; libelle: string; icone: keyof typeof Ionicons.glyphMap }[] = [
    { cle: "clair", libelle: "Clair", icone: "sunny-outline" },
    { cle: "auto", libelle: "Auto", icone: "contrast-outline" },
    { cle: "sombre", libelle: "Sombre", icone: "moon-outline" },
  ];
  return (
    <View style={{ flexDirection: "row", gap: espace.xs,
                   justifyContent: "center", marginBottom: espace.l }}>
      {options.map((o) => {
        const actif = preference === o.cle;
        return (
          <Pressable key={o.cle} onPress={() => choisir(o.cle)} style={{
            flexDirection: "row", alignItems: "center", gap: 6,
            paddingVertical: espace.s, paddingHorizontal: espace.m,
            borderRadius: rayon.s,
            backgroundColor: actif ? c.jauneAplat : c.creux,
          }}>
            <Ionicons name={o.icone} size={15}
                      color={actif ? c.surJaune : c.encreDouce} />
            <T v="petit" couleur={actif ? c.surJaune : c.encreDouce}>{o.libelle}</T>
          </Pressable>
        );
      })}
    </View>
  );
}

export function EcranAccueil({ surChoix }: {
  surChoix: (cle: Section["cle"]) => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxl,
      }}
    >
      <View style={{ alignItems: "center", marginBottom: espace.xl }}>
        <Logo hauteur={84} />
        <T v="titreGrand" style={{ marginTop: espace.m }}>Alluxe</T>
        <T v="corps" couleur={c.encreDouce} style={{ textAlign: "center", marginTop: espace.xs }}>
          Tout le projet, au meme endroit.
        </T>
      </View>
      <ChoixTheme />
      {SECTIONS.map((s) => (
        <BoutonSection key={s.cle} section={s} onPress={() => surChoix(s.cle)} />
      ))}
    </ScrollView>
  );
}
