/**
 * La grille d'offres ALLURE.
 *
 * ELLE VIENT DU SERVEUR, ELLE N'EST PAS ECRITE ICI.
 * Une grille recopiee dans l'application se desynchronise le jour ou
 * une offre change — et sa forme la plus probable est la pire : l'ecran
 * promet une capacite que le serveur refuse, l'utilisateur paie et ne
 * recoit pas.
 *
 * Les PRIX, eux, viennent de Google Play : la devise, les taxes et les
 * promotions locales changent selon le pays. Le prix indicatif de la
 * base ne sert que de repli quand le magasin est injoignable, et il est
 * alors annonce comme indicatif.
 *
 * LE TON DE L'ARGUMENTAIRE : factuel. Pas de « rejoins des milliers de
 * traders », pas de temoignage, pas de compte a rebours. Un
 * argumentaire honnete convainc moins vite — mais il ne produit pas de
 * remboursement a J+3, et c'est lui qu'on transmet a un ami.
 */

import React from "react";
import { StyleSheet, View } from "react-native";
import { Offre, Palier } from "../services/api";
import { euros } from "../services/format";
import { espace, rayon, TRAIT } from "../theme";
import { Bouton, Carte, Etiquette, T, useCouleurs } from "./base";

/** Ce que chaque capacite veut dire, en francais. */
function avantages(o: Offre): string[] {
  const liste: string[] = [];
  liste.push(o.toutes_paires
    ? "Les 70 cryptos suivies par le robot"
    : "Bitcoin, Ethereum et Solana");
  liste.push(o.retard_minutes === 0
    ? "Au moment ou le robot agit"
    : `${Math.round(o.retard_minutes / 60)} heures apres le robot`);
  if (o.positions_direct) liste.push("Les positions en direct, au cours actuel");
  if (o.note_du_matin) liste.push("Le point de marche chaque matin");
  liste.push(o.historique_complet
    ? "L'historique complet des trades"
    : "Les dix derniers trades termines");
  if (o.export_csv) liste.push("Export de l'historique en tableur");
  return liste;
}

export function CarteOffre({ offre, prixMagasin, actuelle, remisePct,
                             onChoisir, enCours }: {
  offre: Offre;
  /** Le prix reel de Google Play. Prioritaire sur l'indicatif. */
  prixMagasin?: string;
  actuelle: boolean;
  /** 10 % si le parrainage Bitvavo est confirme. */
  remisePct: number;
  onChoisir: () => void;
  enCours: boolean;
}) {
  const c = useCouleurs();
  const gratuite = offre.rang === 0;
  const prix = offre.prix_indicatif_eur ?? 0;
  const remise = remisePct > 0 && !gratuite ? prix * (1 - remisePct / 100) : null;

  return (
    <Carte
      style={{ marginBottom: espace.m }}
      accent={actuelle}
      couleurAccent={actuelle ? undefined : c.filetDoux}
    >
      <View style={{ flexDirection: "row", alignItems: "flex-start",
                     justifyContent: "space-between" }}>
        <View style={{ flex: 1, paddingRight: espace.m }}>
          <T v="titre">{offre.nom}</T>
          <T v="petit" style={{ marginTop: 2 }}>{offre.accroche}</T>
        </View>

        <View style={{ alignItems: "flex-end" }}>
          {gratuite ? (
            <T v="chiffre" style={{ fontSize: 20 }}>0 €</T>
          ) : (
            <>
              {remise !== null ? (
                <T v="chiffre" couleur={c.encrePale}
                   style={{ fontSize: 13,
                            textDecorationLine: "line-through" }}>
                  {euros(prix)}
                </T>
              ) : null}
              <T v="chiffre" style={{ fontSize: 20 }}>
                {prixMagasin ?? euros(remise ?? prix)}
              </T>
              <T v="legende">par mois</T>
            </>
          )}
        </View>
      </View>

      {actuelle ? (
        <View style={{
          alignSelf: "flex-start", marginTop: espace.m,
          paddingHorizontal: espace.s, paddingVertical: 2,
          backgroundColor: c.jaune, borderRadius: rayon.s,
        }}>
          <T v="legende" couleur={c.surJaune}>ton offre actuelle</T>
        </View>
      ) : null}

      <View style={{ marginTop: espace.l }}>
        {avantages(offre).map((a, i) => (
          <View key={i} style={{ flexDirection: "row", marginBottom: espace.s }}>
            <View style={{ width: 10, height: TRAIT, backgroundColor: c.jaune,
                           marginTop: 10, marginRight: espace.m }} />
            <T v="corps" couleur={c.encreDouce} style={{ flex: 1 }}>{a}</T>
          </View>
        ))}
      </View>

      {!actuelle && !gratuite ? (
        <View style={{ marginTop: espace.l }}>
          <Bouton
            titre={enCours ? "Un instant..." : `Prendre ${offre.nom}`}
            onPress={onChoisir}
            desactive={enCours}
            variante={offre.rang === 2 ? "plein" : "contour"}
          />
        </View>
      ) : null}

      {!prixMagasin && !gratuite ? (
        <T v="legende" style={{ marginTop: espace.s }}>
          Prix indicatif. Le montant exact, dans ta devise, s'affiche au
          moment du paiement.
        </T>
      ) : null}
    </Carte>
  );
}

/** Le bloc complet, du gratuit au plus haut. */
export function GrilleOffres({ offres, palier, prixMagasin, remisePct,
                               onChoisir, enCours }: {
  offres: Offre[];
  palier: Palier;
  prixMagasin: Record<string, string>;
  remisePct: number;
  onChoisir: (o: Offre) => void;
  enCours: string | null;
}) {
  const c = useCouleurs();
  return (
    <View>
      {remisePct > 0 ? (
        <View style={{
          backgroundColor: c.jaunePale, padding: espace.m,
          borderLeftWidth: TRAIT, borderLeftColor: c.jaune,
          marginBottom: espace.m,
        }}>
          <T v="petit" couleur={c.olive}>
            Ta remise de {remisePct} % pour l'ouverture d'un compte
            Bitvavo est appliquee sur les prix ci-dessous.
          </T>
        </View>
      ) : null}

      {[...offres].sort((a, b) => a.rang - b.rang).map((o) => (
        <CarteOffre
          key={o.tier}
          offre={o}
          prixMagasin={o.produit_id ? prixMagasin[o.produit_id] : undefined}
          actuelle={o.tier === palier}
          remisePct={remisePct}
          onChoisir={() => onChoisir(o)}
          enCours={enCours === o.tier}
        />
      ))}

      <T v="legende" style={{ lineHeight: 17, marginTop: espace.s }}>
        Sans engagement. Le paiement est gere par Google Play : nous ne
        voyons jamais ta carte. La resiliation se fait dans Google Play
        et tu gardes l'acces jusqu'a la fin de la periode payee.
      </T>
    </View>
  );
}
