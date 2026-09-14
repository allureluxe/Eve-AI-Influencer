/**
 * Onglet Signaux.
 *
 * UN JOUR SANS SIGNAL EST LE CAS NORMAL, PAS UNE PANNE.
 * Le robot prend environ un signal par jour sur plus de 200 cryptos, et sa
 * strategie vit de ses rares gros trades. Un utilisateur qui ouvre
 * l'application un jour calme voit une liste vide ; sans explication il
 * conclut que l'application est cassee, ou que l'abonnement ne sert a
 * rien. L'ecran vide DIT pourquoi. C'est une ligne de texte, et c'est
 * probablement ce qui evite le plus de desabonnements.
 *
 * LISTE PUIS DETAIL (14 sept.). Chaque signal affichait toutes ses
 * informations d'un coup, empilees ; retour reel : « trop compacte,
 * pas fluide ». La liste montre une ligne par signal ; le detail
 * complet (CarteSignal) ne s'ouvre qu'au clic.
 */

import React from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, ilYA, ReponseSignaux, Signal } from "../services/api";
import { espace } from "../theme";
import {
  BandeauCache, Bouton, Carte, Logo, Separateur, SqueletteCarte, T,
  useCouleurs, Vide,
} from "../composants/base";
import { CarteSignal } from "../composants/CarteSignal";
import { LigneFloutee, LigneSignal } from "../composants/LigneSignal";
import { BarreReactions } from "../composants/BarreReactions";
import { useCapital } from "../services/reglages";

/** Le detail plein ecran d'un signal, avec retour et l'action « pris ». */
function DetailSignal({ signal, capital, onRetour }: {
  signal: Signal; capital: number; onRetour: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [pris, setPris] = React.useState(false);

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

      <CarteSignal signal={signal} capital={capital} marque={pris} />

      {signal.status === "active" && !pris ? (
        <Bouton titre="J'ai pris ce trade"
                onPress={() => { api.marquerPris(signal.id); setPris(true); }} />
      ) : null}

      <BarreReactions cible="signal" id={signal.id} />
    </ScrollView>
  );
}

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
  const [ouvert, setOuvert] = React.useState<Signal | null>(null);

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

  if (ouvert) {
    return <DetailSignal signal={ouvert} capital={capital}
                         onRetour={() => setOuvert(null)} />;
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
          tintColor={c.jaune}
          onRefresh={async () => {
            setRafraichit(true); await charger(); setRafraichit(false);
          }}
        />
      }
    >
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between" }}>
        <T v="titreGrand">Signaux</T>
        <Logo hauteur={114} />
      </View>
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
                borderBottomColor: onglet === cle ? c.jaune : "transparent",
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
        <LigneSignal key={s.id} signal={s} onPress={() => setOuvert(s)} />
      ))}

      {/* Les signaux payants non envoyes : un gabarit floute par
          signal cache, jamais leur contenu -- voir LigneSignal.tsx. */}
      {onglet === "encours" && data?.tier === "free"
        ? Array.from({ length: data?.masques ?? 0 }).map((_, i) => (
            <LigneFloutee key={`masque-${i}`} />
          ))
        : null}

      {liste.length === 0 && !erreur && !(data?.masques ?? 0) ? (
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

      {data?.tier === "free" && (data?.masques ?? 0) > 0 ? (
        <Carte style={{ marginTop: espace.m }} accent>
          <T v="etiquette">Allure Plus</T>
          <T v="sousTitre" style={{ marginTop: espace.s }}>
            {data.masques === 1
              ? "1 signal en cours ne t'est pas montre"
              : `${data.masques} signaux en cours ne te sont pas montres`}
          </T>
          <T v="petit" style={{ marginTop: espace.s }}>
            Le compte gratuit recoit Bitcoin, Ethereum et Solana, deux
            heures apres leur publication. Allure Plus donne les plus de
            200 cryptos suivies, au moment ou le robot agit.
          </T>
          <View style={{ marginTop: espace.l }}>
            <Bouton titre="Voir Allure Plus" onPress={versAbonnement} />
          </View>
        </Carte>
      ) : null}

      <Separateur marge={espace.xl} />
      <T v="legende" style={{ textAlign: "center", lineHeight: 17 }}>
        Allure publie des analyses de marche. Ce n'est pas un conseil en
        investissement personnalise. Nous ne detenons aucun fonds.
      </T>
    </ScrollView>
  );
}
