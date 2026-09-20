/**
 * Le selecteur des comptes de simulation.
 *
 * Demande de l'operateur le 20 septembre : « 3 onglets dans le mode
 * demo — demo 1, demo 2, demo 3 — et le nom de la methode utilisee avec
 * le capital en direct en euros. En cliquant dessus j'ai toutes les
 * positions et l'historique du compte. »
 *
 * POURQUOI TROIS COMPTES. Comparer deux methodes l'une APRES l'autre
 * melange l'effet du reglage et celui du marche — « une mesure qui
 * bouge deux variables ne dit rien sur aucune des deux ». Les faire
 * tourner en meme temps, sur les memes cotations, isole le reglage.
 *
 * LE NOM DE LA METHODE N'EST PAS ECRIT ICI. Il vient de la table
 * `alluxe_bot_comptes`, ou chaque robot publie SA methode au demarrage,
 * deduite de la configuration qu'il vient de charger. Le recopier dans
 * l'application, c'est ce qui avait fait afficher « canal 20 jours »
 * pendant une semaine alors que le robot tournait a 10.
 */
import React from "react";
import { Pressable, ScrollView, View } from "react-native";
import { CompteDemo } from "../services/robot";
import { euros } from "../services/format";
import { espace, rayon } from "../theme";
import { T, useCouleurs } from "./base";

/** Les trois comptes, dans l'ordre. Le nom affiche est court : c'est un
 *  onglet, pas une phrase. */
export const COMPTES = [
  { cle: "demo", nom: "Démo 1" },
  { cle: "demo2", nom: "Démo 2" },
  { cle: "demo3", nom: "Démo 3" },
] as const;

export type CleCompte = (typeof COMPTES)[number]["cle"];

/** Depuis combien de temps ce compte n'a-t-il plus parle ? */
function silenceDepuis(vuLe: string | undefined): number {
  if (!vuLe) return Infinity;
  return (Date.now() - new Date(vuLe).getTime()) / 60000;   // minutes
}

export function ChoixCompte({ actif, comptes, capitaux, surChoix }: {
  actif: CleCompte;
  comptes: Record<string, CompteDemo>;
  /** Capital EN DIRECT de chaque compte : depart + encaisse + en cours. */
  capitaux: Record<string, number | null>;
  surChoix: (cle: CleCompte) => void;
}) {
  const c = useCouleurs();

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={{ flexGrow: 0, marginBottom: espace.l }}
      contentContainerStyle={{ gap: espace.s, paddingRight: espace.l }}
    >
      {COMPTES.map(({ cle, nom }) => {
        const estActif = cle === actif;
        const fiche = comptes[cle];
        const capital = capitaux[cle];
        // Un compte qui n'a pas parle depuis un quart d'heure est
        // arrete. Afficher son capital comme s'il etait a jour ferait
        // lire un chiffre fige pour un chiffre vivant.
        const arrete = silenceDepuis(fiche?.vu_le) > 15;
        const jamaisDemarre = !fiche;

        return (
          <Pressable
            key={cle}
            onPress={() => surChoix(cle)}
            accessibilityRole="button"
            accessibilityState={{ selected: estActif }}
            accessibilityLabel={`${nom}${fiche ? ", " + fiche.resume_methode : ", pas encore démarré"}`}
            style={{
              minWidth: 190, maxWidth: 240,
              backgroundColor: estActif ? c.jauneAplat : c.surface,
              borderRadius: rayon.l,
              borderWidth: estActif ? 0 : 1,
              borderColor: c.filetDoux,
              paddingVertical: espace.m, paddingHorizontal: espace.l,
              opacity: jamaisDemarre ? 0.6 : 1,
            }}
          >
            <View style={{ flexDirection: "row", alignItems: "center",
                           justifyContent: "space-between", gap: espace.s }}>
              <T v="sousTitre" couleur={estActif ? c.surJaune : c.encre}>
                {nom}
              </T>
              {(arrete || jamaisDemarre) && (
                <View style={{ width: 7, height: 7, borderRadius: 4,
                               backgroundColor: estActif ? c.surJaune : c.encrePale }} />
              )}
            </View>

            <T v="chiffre"
               couleur={estActif ? c.surJaune : c.encre}
               style={{ marginTop: 2 }}>
              {capital != null ? euros(capital) : "—"}
            </T>

            <T v="legende"
               couleur={estActif ? c.surJaune : c.encrePale}
               style={{ marginTop: 4 }}>
              {jamaisDemarre
                ? "pas encore démarré"
                : arrete
                  ? "arrêté · " + fiche.resume_methode
                  : fiche.resume_methode}
            </T>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}
