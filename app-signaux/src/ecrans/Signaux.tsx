/**
 * Onglet Signaux — l'ecran d'accueil.
 *
 * UN JOUR SANS SIGNAL EST LE CAS NORMAL, PAS UNE PANNE.
 * Le robot prend environ un signal par jour sur 70 cryptos, et sa
 * strategie vit de ses rares gros trades. Un utilisateur qui ouvre
 * l'application un jour calme voit une liste vide ; sans explication il
 * conclut que l'application est cassee, ou que l'abonnement ne sert a
 * rien. L'ecran vide DIT pourquoi. C'est une ligne de texte, et c'est
 * probablement ce qui evite le plus de desabonnements.
 */

import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, ilYA, ReponseSignaux } from "../services/api";
import { espace, rayon } from "../theme";
import {
  BandeauCache, Bouton, Carte, Separateur, SqueletteCarte, T, useCouleurs, Vide,
} from "../composants/base";
import { CarteSignal } from "../composants/CarteSignal";
import { useCapital } from "../services/reglages";

export function EcranSignaux({ versAbonnement }: { versAbonnement: () => void }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const capital = useCapital();

  const [data, setData] = React.useState<ReponseSignaux | null>(null);
  const [cache, setCache] = React.useState<string | null>(null);
  const [erreur, setErreur] = React.useState<string | null>(null);
  const [chargeUneFois, setChargeUneFois] = React.useState(false);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [onglet, setOnglet] = React.useState<"encours" | "historique">("encours");

  const charger = React.useCallback(async () => {
    const r = await api.signaux();
    setData(r.donnee);
    setCache(r.duCache && r.ageMinutes !== null
      ? `Hors ligne — dernieres donnees ${ilYA(r.ageMinutes)}` : null);
    setErreur(r.erreur);
    setChargeUneFois(true);
  }, []);

  React.useEffect(() => { charger(); }, [charger]);

  // Un rafraichissement automatique toutes les deux minutes tant que
  // l'ecran est ouvert. Plus court epuiserait la batterie pour rien :
  // le robot ne produit pas un signal par minute.
  React.useEffect(() => {
    const t = setInterval(charger, 120_000);
    return () => clearInterval(t);
  }, [charger]);

  if (!chargeUneFois) {
    return (
      <ScrollView contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.l }}>
        <SqueletteCarte /><SqueletteCarte /><SqueletteCarte />
      </ScrollView>
    );
  }

  const liste = onglet === "encours"
    ? (data?.actifs ?? []) : (data?.clotures ?? []);

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
      refreshControl={
        <RefreshControl
          refreshing={rafraichit}
          tintColor={c.laiton}
          onRefresh={async () => {
            setRafraichit(true); await charger(); setRafraichit(false);
          }}
        />
      }
    >
      <T v="titreGrand">Signaux</T>
      <T v="petit" style={{ marginTop: 2, marginBottom: espace.l }}>
        Ce que le robot fait avec son propre argent.
      </T>

      {cache ? <BandeauCache texte={cache} /> : null}

      {/* Deux onglets, en filet. Pas de pastilles colorees. */}
      <View style={{ flexDirection: "row", marginBottom: espace.l,
                     borderBottomWidth: 1, borderBottomColor: c.filet }}>
        {([["encours", "En cours"], ["historique", "Historique"]] as const)
          .map(([cle, libelle]) => (
            <T
              key={cle}
              v="sousTitre"
              couleur={onglet === cle ? c.encre : c.encrePale}
              style={{
                paddingVertical: espace.m, marginRight: espace.xl,
                borderBottomWidth: 2, marginBottom: -1,
                borderBottomColor: onglet === cle ? c.laiton : "transparent",
              }}
              onPress={() => setOnglet(cle)}
            >
              {libelle}
            </T>
          ))}
      </View>

      {erreur && !data ? (
        <Vide titre={erreur}
              detail="Tire vers le bas pour reessayer." />
      ) : null}

      {liste.map((s) => (
        <CarteSignal
          key={s.id}
          signal={s}
          capital={capital}
          onPress={s.status === "active"
            ? () => api.marquerPris(s.id) : undefined}
        />
      ))}

      {liste.length === 0 && !erreur ? (
        onglet === "encours" ? (
          <Vide
            titre="Aucune position ouverte aujourd'hui"
            detail={
              "Le robot prend environ un signal par jour, et seulement " +
              "quand les conditions sont reunies. Une journee sans signal " +
              "est le fonctionnement normal, pas une panne — c'est meme " +
              "ce qui evite les mauvais trades."
            }
          />
        ) : (
          <Vide titre="Pas encore d'historique"
                detail="Les trades termines apparaitront ici." />
        )
      ) : null}

      {/* L'invitation a l'abonnement : un NOMBRE, jamais un contenu.
          Annoncer « BTC vient de passer a l'achat, abonne-toi » serait
          donner le signal tout en pretendant le vendre. */}
      {data?.tier === "free" && (data?.masques ?? 0) > 0 ? (
        <Carte style={{ marginTop: espace.m }} accent={c.laiton}>
          <T v="etiquette">Eve Plus</T>
          <T v="sousTitre" style={{ marginTop: espace.s }}>
            {data.masques === 1
              ? "1 signal en cours ne t'est pas montre"
              : `${data.masques} signaux en cours ne te sont pas montres`}
          </T>
          <T v="petit" style={{ marginTop: espace.s }}>
            Le compte gratuit recoit Bitcoin, Ethereum et Solana, deux
            heures apres leur publication. Eve Plus donne les 70 cryptos
            suivies, au moment ou le robot agit.
          </T>
          <View style={{ marginTop: espace.l }}>
            <Bouton titre="Voir Eve Plus" onPress={versAbonnement} />
          </View>
        </Carte>
      ) : null}

      <Separateur marge={espace.xl} />
      <T v="legende" style={{ textAlign: "center", lineHeight: 17 }}>
        Eve publie des analyses de marche. Ce n'est pas un conseil en
        investissement personnalise. Nous ne detenons aucun fonds.
      </T>
    </ScrollView>
  );
}
