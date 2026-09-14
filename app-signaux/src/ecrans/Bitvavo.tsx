/**
 * L'ecran Bitvavo : ou passer les ordres, et le parrainage.
 *
 * CE QU'ON PROMET ET CE QU'ON PEUT TENIR
 * --------------------------------------
 * On propose 10 % de remise sur l'abonnement a qui ouvre un compte
 * Bitvavo par notre lien. Bitvavo ne nous previent pas nommement de
 * chaque ouverture : on ne PEUT donc pas accorder la remise
 * automatiquement.
 *
 * Deux mauvaises reponses etaient possibles. Accorder sur simple
 * declaration : tout le monde coche, la remise devient une baisse de
 * prix generale deguisee. Refuser faute de preuve automatique : la
 * promesse n'est jamais tenue, ce qui est pire que de ne pas la faire.
 *
 * La bonne reponse est de le dire. L'ecran annonce clairement que la
 * remise est verifiee sous quelques jours, et l'etat de la demande est
 * visible a tout moment. Une promesse dont on explique le delai est
 * tenue ; une promesse instantanee qu'on n'honore pas ne l'est pas.
 *
 * ON N'ECRIT NULLE PART QUE BITVAVO EST « LA MEILLEURE PLATEFORME ».
 * C'est celle sur laquelle le robot tourne — donc celle dont les prix
 * correspondent exactement aux signaux — et nous touchons une
 * commission. Les deux sont dits.
 */

import React from "react";
import { Alert, Linking, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Constants from "expo-constants";
import { supabase } from "../services/supabase";
import { espace, rayon, TRAIT } from "../theme";
import {
  Bouton, Carte, EnTete, Etiquette, Separateur, T, useCouleurs,
} from "../composants/base";

/** Le code de parrainage, injecte a la construction. */
const CODE = (Constants.expoConfig?.extra as Record<string, string>)
  ?.bitvavoParrainage ?? "";

interface Parrainage {
  demande_le: string;
  confirme_le: string | null;
}

function Etape({ n, titre, detail }: {
  n: number; titre: string; detail: string;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", marginBottom: espace.l }}>
      <View style={{
        width: 26, height: 26, borderRadius: rayon.s,
        borderWidth: TRAIT, borderColor: c.filet,
        alignItems: "center", justifyContent: "center",
        marginRight: espace.m,
      }}>
        <T v="chiffre" style={{ fontSize: 13 }}>{n}</T>
      </View>
      <View style={{ flex: 1 }}>
        <T v="sousTitre">{titre}</T>
        <T v="petit" style={{ marginTop: 2 }}>{detail}</T>
      </View>
    </View>
  );
}

export function EcranBitvavo({ onRetour }: { onRetour: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [parrainage, setParrainage] = React.useState<Parrainage | null>(null);
  const [charge, setCharge] = React.useState(false);

  const relire = React.useCallback(async () => {
    const { data: session } = await supabase.auth.getSession();
    const id = session.session?.user?.id;
    if (!id) { setCharge(true); return; }
    const { data } = await supabase
      .from("parrainages").select("demande_le, confirme_le")
      .eq("user_id", id).maybeSingle();
    setParrainage(data as Parrainage | null);
    setCharge(true);
  }, []);

  React.useEffect(() => { relire(); }, [relire]);

  async function ouvrirBitvavo() {
    const { data: session } = await supabase.auth.getSession();
    const id = session.session?.user?.id;
    if (!id) return;

    // Le jeton est deterministe et derive de l'identifiant : on le
    // retrouve tel quel dans le tableau de bord d'affiliation pour
    // rapprocher, sans stocker de correspondance ailleurs.
    const jeton = id.replace(/-/g, "").slice(0, 12);

    // La declaration part AVANT l'ouverture du navigateur : si
    // l'utilisateur ne revient jamais dans l'application, la demande
    // existe quand meme et pourra etre confirmee.
    await supabase.from("parrainages")
      .upsert({ user_id: id, jeton }, { onConflict: "user_id" });
    await relire();

    const url = CODE
      ? `https://bitvavo.com/fr/invite?a=${CODE}&ref=${jeton}`
      : "https://bitvavo.com/fr";
    await Linking.openURL(url);
  }

  const confirme = Boolean(parrainage?.confirme_le);
  const enAttente = Boolean(parrainage && !parrainage.confirme_le);

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <Pressable onPress={onRetour} style={{ marginBottom: espace.l }}>
        <T v="sousTitre" couleur={c.encreDouce}>‹ Retour</T>
      </Pressable>

      <EnTete
        titre="Passer tes ordres"
        sousTitre="Ou et comment acheter ce que le robot achete."
      />

      {/* ------------------------------------------ l'etat de la remise */}
      {charge && confirme ? (
        <Carte accent style={{ marginBottom: espace.l }}>
          <Etiquette>Remise active</Etiquette>
          <T v="titre" style={{ marginTop: espace.xs }}>
            10 % de reduction sur ton abonnement
          </T>
          <T v="petit" style={{ marginTop: espace.s }}>
            Ton ouverture de compte Bitvavo a ete verifiee. La reduction
            s'applique automatiquement au prochain prelevement.
          </T>
        </Carte>
      ) : null}

      {charge && enAttente ? (
        <Carte style={{ marginBottom: espace.l }} couleurAccent={c.encrePale}>
          <Etiquette>Verification en cours</Etiquette>
          <T v="sousTitre" style={{ marginTop: espace.xs }}>
            Ta demande de remise est enregistree
          </T>
          <T v="petit" style={{ marginTop: espace.s }}>
            Bitvavo ne nous previent pas en temps reel des ouvertures de
            compte : nous verifions a la main, sous quelques jours. Tu
            verras la remise apparaitre ici une fois confirmee.
          </T>
        </Carte>
      ) : null}

      {/* ------------------------------------------------- comment faire */}
      <Carte>
        <T v="titre">Comment suivre un signal</T>
        <T v="petit" style={{ marginTop: espace.xs, marginBottom: espace.l }}>
          Allure ne passe aucun ordre a ta place. Voici les quatre
          etapes, dans l'ordre.
        </T>

        <Etape n={1} titre="Ouvre ta plateforme"
               detail="Bitvavo, Binance, Kraken : celle que tu utilises deja." />
        <Etape n={2} titre="Cherche la crypto du signal"
               detail="Le nom exact est affiche sur la carte du signal." />
        <Etape n={3} titre="Achete au marche"
               detail="Pour le montant que TU as decide. L'application t'indique ce que la position peut te couter au pire." />
        <Etape n={4}
               titre="Place ta protection tout de suite"
               detail="Un ordre stop au prix indique. C'est l'etape que les debutants sautent, et c'est celle qui compte le plus : sans elle, une position peut descendre sans limite." />

        <View style={{
          backgroundColor: c.jaunePale, padding: espace.m,
          borderLeftWidth: TRAIT, borderLeftColor: c.jaune,
        }}>
          <T v="petit" couleur={c.olive}>
            Le robot deplace ses protections au fil du temps. Quand une
            position passe « a l'abri » dans l'onglet Direct, remonte ton
            propre stop au meme prix.
          </T>
        </View>
      </Carte>

      {/* ------------------------------------------------- le parrainage */}
      <Carte style={{ marginTop: espace.l }} accent={!confirme}>
        <Etiquette>Pas encore de compte ?</Etiquette>
        <T v="titre" style={{ marginTop: espace.xs }}>
          Bitvavo, et 10 % sur ton abonnement Allure
        </T>

        <T v="corps" couleur={c.encreDouce} style={{ marginTop: espace.m }}>
          Le robot tourne sur Bitvavo. Les prix affiches dans les signaux
          sont donc exactement ceux que tu verras — sur une autre
          plateforme, ils different legerement.
        </T>

        {/* LA TRANSPARENCE SUR LA COMMISSION EST OBLIGATOIRE, et elle
            est aussi ce qui rend la recommandation credible. */}
        <View style={{
          marginTop: espace.m, padding: espace.m, backgroundColor: c.creux,
          borderRadius: rayon.s,
        }}>
          <T v="petit">
            En toute transparence : si tu ouvres un compte par ce lien,
            Allure touche une commission de Bitvavo. C'est ce qui nous
            permet de te reverser 10 % sur ton abonnement. Tu peux tout
            a fait ouvrir un compte sans passer par nous.
          </T>
        </View>

        <View style={{ marginTop: espace.l }}>
          <Bouton
            titre={enAttente || confirme
              ? "Rouvrir le lien Bitvavo"
              : "Ouvrir un compte Bitvavo"}
            onPress={ouvrirBitvavo}
          />
        </View>

        {!enAttente && !confirme ? (
          <T v="legende" style={{ marginTop: espace.s, lineHeight: 16 }}>
            La remise n'est pas immediate : nous verifions l'ouverture
            sous quelques jours, puis elle s'applique au prelevement
            suivant.
          </T>
        ) : null}
      </Carte>

      {/* -------------------------------------------- deja un compte ? */}
      {!confirme && !enAttente ? (
        <T
          v="petit"
          couleur={c.encreDouce}
          style={{ textAlign: "center", marginTop: espace.l,
                   textDecorationLine: "underline" }}
          onPress={() => Alert.alert(
            "Compte deja ouvert",
            "La remise ne concerne que les comptes ouverts par notre " +
            "lien : Bitvavo ne nous reverse rien sur un compte existant. " +
            "Ecris-nous si tu penses etre dans un cas particulier.")}
        >
          J'ai deja un compte Bitvavo
        </T>
      ) : null}

      <Separateur marge={espace.xl} />
      <T v="legende" style={{ textAlign: "center", lineHeight: 17 }}>
        Allure ne detient aucun fonds, ne demande jamais tes cles
        d'echange et ne passe aucun ordre a ta place.{"\n"}
        Ce n'est pas un conseil en investissement personnalise.
      </T>
    </ScrollView>
  );
}
