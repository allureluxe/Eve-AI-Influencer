/**
 * Onglet Compte -- segment Abonnement.
 *
 * L'ARGUMENTAIRE EST FACTUEL. Pas de « rejoins des milliers de
 * traders », pas de temoignage, pas de compte a rebours. Trois lignes
 * qui disent exactement ce qu'on recoit en plus. Un argumentaire
 * honnete convainc moins vite qu'un argumentaire vendeur — mais il ne
 * produit pas de remboursement a J+3, et c'est lui qu'on transmet.
 *
 * NE PORTE PLUS QUE L'ABONNEMENT (14 sept.). Le capital declaratif, les
 * notifications, "ce qu'Allure ne fait pas" et les liens legaux ont
 * rejoint Profil.tsx / APropos.tsx / Contact.tsx -- voir
 * CompteEtBitvavo.tsx pour le decoupage complet en segments.
 */

import React from "react";
import { Alert, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Offre, Palier } from "../services/api";
import {
  lireOffres, lirePalier, lireRemise, ouvrirGestionPlay,
  prochainPrelevement, restaurer, souscrire,
} from "../services/abonnement";
import { espace } from "../theme";
import { Bouton, Carte, Etiquette, T, useCouleurs } from "../composants/base";
import { GrilleOffres } from "../composants/Offres";

function Rubrique({ titre, children }: {
  titre: string; children: React.ReactNode;
}) {
  return (
    <View style={{ marginTop: espace.xxl }}>
      <Etiquette style={{ marginBottom: espace.s }}>{titre}</Etiquette>
      {children}
    </View>
  );
}

export function EcranCompte() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [palier, setPalier] = React.useState<Palier>("free");
  const [offres, setOffres] = React.useState<Offre[]>([]);
  const [prixMagasin, setPrixMagasin] = React.useState<Record<string, string>>({});
  const [remise, setRemise] = React.useState(0);
  const [echeance, setEcheance] = React.useState<Date | null>(null);
  const [enCours, setEnCours] = React.useState<string | null>(null);

  const rafraichir = React.useCallback(async () => {
    setPalier(await lirePalier());
    setRemise(await lireRemise());
    setEcheance(await prochainPrelevement());
  }, []);

  React.useEffect(() => {
    rafraichir();
    lireOffres().then(({ grille, prix }) => {
      setOffres(grille);
      setPrixMagasin(prix);
    });
  }, [rafraichir]);

  async function choisir(offre: Offre) {
    if (!offre.produit_id) return;
    setEnCours(offre.tier);
    const resultat = await souscrire(offre.produit_id);
    setEnCours(null);

    if (resultat === "annule") return;
    if (resultat === "indisponible") {
      Alert.alert("Offre indisponible",
                  "Le magasin n'a pas repondu. Rien n'a ete preleve.");
      return;
    }
    if (resultat === "echec") {
      Alert.alert("Achat non abouti",
                  "Rien n'a ete preleve. Tu peux reessayer.");
      return;
    }
    // LE DEBLOCAGE VIENT DU SERVEUR, PAS DE L'ACHAT.
    // RevenueCat previent notre serveur par webhook ; on relit le
    // profil apres un instant. Debloquer localement ferait apparaitre
    // un abonne que le serveur ne reconnait pas — et qui verrait un
    // ecran vide en croyant avoir paye.
    setTimeout(rafraichir, 2500);
    Alert.alert("C'est fait",
                `Ton abonnement ${offre.nom} est actif. Les signaux ` +
                `arrivent dans quelques secondes.`);
  }

  const offreActuelle = offres.find((o) => o.tier === palier);
  const payant = (offreActuelle?.rang ?? 0) > 0;

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      {payant ? (
        <>
          <Carte accent>
            <Etiquette>Ton abonnement</Etiquette>
            <T v="titre" style={{ marginTop: espace.xs }}>
              Allure {offreActuelle?.nom}
            </T>
            {echeance ? (
              <T v="petit" style={{ marginTop: espace.s }}>
                Prochain prelevement le{" "}
                {echeance.toLocaleDateString("fr-FR", {
                  day: "numeric", month: "long", year: "numeric" })}.
              </T>
            ) : null}
            {remise > 0 ? (
              <T v="petit" couleur={c.olive} style={{ marginTop: espace.xs }}>
                Remise de {remise} % appliquee (parrainage Bitvavo).
              </T>
            ) : null}
            <View style={{ marginTop: espace.l }}>
              <Bouton titre="Gerer ou resilier" variante="contour"
                      onPress={ouvrirGestionPlay} />
            </View>
            <T v="legende" style={{ marginTop: espace.s, lineHeight: 16 }}>
              La resiliation se fait dans Google Play. Tu gardes l'acces
              jusqu'a la fin de la periode deja payee.
            </T>
          </Carte>

          <Rubrique titre="Changer d'offre">
            <GrilleOffres
              offres={offres} palier={palier} prixMagasin={prixMagasin}
              remisePct={remise} onChoisir={choisir} enCours={enCours}
            />
          </Rubrique>
        </>
      ) : (
        <Rubrique titre="Les offres Allure">
          <GrilleOffres
            offres={offres} palier={palier} prixMagasin={prixMagasin}
            remisePct={remise} onChoisir={choisir} enCours={enCours}
          />
          <View style={{ marginTop: espace.m }}>
            <Bouton
              titre="J'ai deja un abonnement"
              variante="discret"
              onPress={async () => {
                const ok = await restaurer();
                await rafraichir();
                Alert.alert(
                  ok ? "Abonnement retrouve" : "Aucun abonnement trouve",
                  ok ? "Ton acces est retabli."
                     : "Verifie que tu utilises le meme compte Google.");
              }}
            />
          </View>
        </Rubrique>
      )}
    </ScrollView>
  );
}
