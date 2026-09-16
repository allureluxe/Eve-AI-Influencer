/**
 * Onglet Accueil.
 *
 * REMPLACE LES TROIS PAGES DEFILANTES DU PREMIER LANCEMENT (14 sept.).
 * Retour reel : « il y a toujours pas la page d'introduction comme j'ai
 * demande, je prefere que tu fasses un onglet accueil que 3 pages qui
 * defilent au debut ». Le contenu ne disparait pas -- il devient une
 * case permanente de la barre du bas, toujours consultable, au lieu
 * d'un tunnel qu'on ne revoit qu'en cherchant un lien dans les reglages.
 *
 * L'ORDRE RESTE CELUI QUI AVAIT ETE PENSE POUR L'INTRODUCTION : le
 * resultat en direct d'abord (ce que le visiteur veut verifier tout de
 * suite), puis l'histoire, puis ce qu'Allure fait et ne fait pas, puis
 * comment s'en servir. Voir l'ancien historique de ce fichier pour le
 * raisonnement complet sur cet ordre.
 */

import React from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { espace, rayon } from "../../theme";
import { Carte, Etiquette, Logo, Separateur, T, useCouleurs } from "../../composants/base";
import { supabase } from "../../services/supabase";
import { euros, pourcent } from "../services/format";
import { EcranCommunaute } from "./Communaute";
import { EcranMessages } from "./Messages";

interface EtatPublic { capital_eur: number; variation_jour_pct: number; }

/**
 * Le capital reel et la variation du jour, lus sans rien connaitre du
 * compte de l'utilisateur -- la table `etat_public` est volontairement
 * lisible par tout le monde (demande de l'operateur, 14 sept. : « une
 * page d'introduction avec le capital actuel du bot et le pourcentage
 * journalier »). Publiee par ops/publier_etat_public.py, toutes les 5
 * minutes.
 */
function useEtatPublic(): EtatPublic | null {
  const [etat, setEtat] = React.useState<EtatPublic | null>(null);
  React.useEffect(() => {
    (async () => {
      try {
        const { data } = await supabase.from("etat_public")
          .select("capital_eur, variation_jour_pct")
          .eq("id", "robot").maybeSingle();
        if (data) setEtat(data as EtatPublic);
      } catch {
        // Pas grave : la page reste utile sans ce chiffre.
      }
    })();
  }, []);
  return etat;
}

/** La carte de chiffres, tout en haut de l'onglet. */
function CarteEnDirect() {
  const c = useCouleurs();
  const etat = useEtatPublic();
  if (!etat) return null;
  const positif = etat.variation_jour_pct >= 0;
  return (
    <View style={{
      flexDirection: "row", backgroundColor: c.creux,
      borderRadius: rayon.l, padding: espace.l, marginBottom: espace.xl,
    }}>
      <View style={{ flex: 1 }}>
        <T v="legende">Capital reel du robot, maintenant</T>
        <T v="chiffre" style={{ fontSize: 26, marginTop: 2 }}>
          {euros(etat.capital_eur, 0)}
        </T>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <T v="legende">Aujourd'hui</T>
        <T v="chiffre" couleur={positif ? c.gain : c.perte}
           style={{ fontSize: 26, marginTop: 2 }}>
          {pourcent(etat.variation_jour_pct)}
        </T>
      </View>
    </View>
  );
}

/** Une section de texte : sur-titre jaune, titre, paragraphes. */
function Section({ eyebrow, titre, paragraphes }: {
  eyebrow: string; titre: string; paragraphes: string[];
}) {
  const c = useCouleurs();
  return (
    <Carte style={{ marginBottom: espace.m }}>
      <Etiquette>{eyebrow}</Etiquette>
      <T v="titre" style={{ marginTop: espace.s, marginBottom: espace.m }}>
        {titre}
      </T>
      {paragraphes.map((texte, i) => (
        <T key={i} v="corps" couleur={c.encreDouce}
           style={{ marginTop: i ? espace.m : 0 }}>
          {texte}
        </T>
      ))}
    </Carte>
  );
}

/**
 * Un raccourci vers un ecran a part (Communaute, Messages) -- icone +
 * libelle, sans case dans la barre du bas. Meme principe que Binance :
 * le fil social et la messagerie se rejoignent par une icone depuis
 * l'accueil, pas par un onglet supplementaire (retour reel, 14 sept. :
 * « essaye de faire un peu comme Binance fait »).
 */
function Raccourci({ icone, libelle, onPress }: {
  icone: keyof typeof Ionicons.glyphMap; libelle: string; onPress: () => void;
}) {
  const c = useCouleurs();
  return (
    <Pressable onPress={onPress} style={{
      flex: 1, alignItems: "center", backgroundColor: c.creux,
      borderRadius: rayon.m, paddingVertical: espace.m, marginRight: espace.s,
    }}>
      <Ionicons name={icone} size={24} color={c.encre} />
      <T v="petit" style={{ marginTop: espace.xs }}>{libelle}</T>
    </Pressable>
  );
}

export function EcranAccueil() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [vue, setVue] = React.useState<"accueil" | "communaute" | "messages">("accueil");

  if (vue === "communaute") {
    return <EcranCommunaute onRetour={() => setVue("accueil")} />;
  }
  if (vue === "messages") {
    return <EcranMessages onRetour={() => setVue("accueil")} />;
  }

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between" }}>
        <T v="titreGrand">Accueil</T>
        <Logo hauteur={114} />
      </View>
      <T v="petit" style={{ marginTop: 2, marginBottom: espace.l }}>
        Ce qu'Allure fait, et pourquoi.
      </T>

      <View style={{ flexDirection: "row", marginBottom: espace.l }}>
        <Raccourci icone="people-outline" libelle="Communaute"
                   onPress={() => setVue("communaute")} />
        <Raccourci icone="chatbubbles-outline" libelle="Messages"
                   onPress={() => setVue("messages")} />
      </View>

      <CarteEnDirect />

      <Section
        eyebrow="L'histoire"
        titre="Un robot qui trade son propre argent, en public"
        paragraphes={[
          "Depuis fin aout, un robot achete et vend des cryptos avec un " +
          "vrai compte Bitvavo -- pas une simulation. Chaque fois qu'il " +
          "ouvre une position, tu la vois : la crypto, le prix, la " +
          "protection, et pourquoi.",
          "Il ne cherche pas a deviner le marche minute par minute : sa " +
          "strategie tient ses positions plusieurs jours, et elle vit " +
          "de quelques gros trades plutot que de beaucoup de petits.",
          "Tu vois aussi quand il perd. C'est le meme flux, sans tri.",
        ]}
      />

      <Section
        eyebrow="Ce qu'Allure fait"
        titre="Elle publie ce que le robot fait, en direct"
        paragraphes={[
          "Chaque ouverture et chaque cloture de position passe par " +
          "l'application : l'onglet Direct montre ce qui est ouvert " +
          "maintenant, l'onglet Signaux garde l'historique.",
        ]}
      />

      <Section
        eyebrow="Ce qu'Allure ne fait pas"
        titre="Allure ne touche jamais a ton argent"
        paragraphes={[
          "Aucune connexion a ton compte, aucun ordre passe a ta place, " +
          "aucune cle d'echange demandee. Personne de serieux ne t'en " +
          "demandera jamais.",
          "Allure ne promet aucun gain et ne te dit pas quoi faire. " +
          "Elle publie ce qu'un robot fait, tu decides du reste.",
        ]}
      />

      <Section
        eyebrow="Comment s'en servir"
        titre="Le signal arrive, tu passes l'ordre toi-meme"
        paragraphes={[
          "Ouvre ton application Bitvavo ou Binance, cherche la crypto " +
          "indiquee, et passe un ordre d'achat au marche pour le " +
          "montant que tu as decide.",
          "Place ensuite un ordre stop au prix de protection affiche. " +
          "C'est lui qui limite ce que le trade peut te couter -- c'est " +
          "l'etape que les debutants sautent, et c'est celle qui compte " +
          "le plus.",
          "Indique ton capital dans l'onglet Compte : chaque signal " +
          "t'affichera alors, en euros, ce qu'il peut te couter au pire.",
        ]}
      />

      <Separateur marge={espace.xl} />
      <T v="legende" style={{ textAlign: "center", lineHeight: 17 }}>
        Allure publie des analyses de marche. Ce n'est pas un conseil en
        investissement personnalise. Nous ne detenons aucun fonds.
      </T>
    </ScrollView>
  );
}
