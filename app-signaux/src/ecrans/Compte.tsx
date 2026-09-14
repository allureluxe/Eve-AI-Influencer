/**
 * Onglet Compte — abonnement, reglages, et ce qu'Allure ne fait pas.
 *
 * L'ARGUMENTAIRE EST FACTUEL. Pas de « rejoins des milliers de
 * traders », pas de temoignage, pas de compte a rebours. Trois lignes
 * qui disent exactement ce qu'on recoit en plus. Un argumentaire
 * honnete convainc moins vite qu'un argumentaire vendeur — mais il ne
 * produit pas de remboursement a J+3, et c'est lui qu'on transmet.
 */

import React from "react";
import {
  Alert, Linking, ScrollView, StyleSheet, Switch, TextInput, View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Offre, Palier } from "../services/api";
import {
  lireOffres, lirePalier, lireRemise, ouvrirGestionPlay,
  prochainPrelevement, restaurer, souscrire,
} from "../services/abonnement";
import { CAPITAL_DEFAUT, enregistrerCapital, useCapital }
  from "../services/reglages";
import { supabase } from "../services/supabase";
import { euros } from "../services/format";
import { espace, rayon, TRAIT } from "../theme";
import {
  Bouton, Carte, EnTete, Etiquette, Logo, Separateur, T, useCouleurs,
} from "../composants/base";
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

function LigneReglage({ titre, detail, valeur, onChange }: {
  titre: string; detail?: string; valeur: boolean;
  onChange: (v: boolean) => void;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", alignItems: "center",
                   paddingVertical: espace.m }}>
      <View style={{ flex: 1, paddingRight: espace.l }}>
        <T v="corps">{titre}</T>
        {detail ? <T v="petit" style={{ marginTop: 2 }}>{detail}</T> : null}
      </View>
      <Switch value={valeur} onValueChange={onChange}
              trackColor={{ true: c.jaune, false: c.creux }}
              thumbColor={c.surface} />
    </View>
  );
}

export function EcranCompte({ email, onRevoirPresentation }: {
  email: string;
  /** Remet l'introduction en trois pages -- vue une seule fois par
   * defaut, sinon injoignable. Demande le 13 sept. : « il faut une
   * page d'accueil pour expliquer l'application, c'est trop direct ».
   * Elle existait deja ; ce qui manquait, c'etait un moyen de la
   * revoir apres l'avoir passee la premiere fois. */
  onRevoirPresentation: () => void;
}) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const capitalEnregistre = useCapital();

  const [palier, setPalier] = React.useState<Palier>("free");
  const [offres, setOffres] = React.useState<Offre[]>([]);
  const [prixMagasin, setPrixMagasin] = React.useState<Record<string, string>>({});
  const [remise, setRemise] = React.useState(0);
  const [echeance, setEcheance] = React.useState<Date | null>(null);
  const [enCours, setEnCours] = React.useState<string | null>(null);
  const [capital, setCapital] = React.useState(String(CAPITAL_DEFAUT));
  const [signaux, setSignaux] = React.useState(true);
  const [macro, setMacro] = React.useState(true);

  React.useEffect(() => { setCapital(String(capitalEnregistre)); },
                  [capitalEnregistre]);

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
    supabase.auth.getSession().then(async ({ data }) => {
      const id = data.session?.user?.id;
      if (!id) return;
      const { data: p } = await supabase
        .from("profiles").select("notif_signals, notif_macro")
        .eq("id", id).single();
      if (p) { setSignaux(p.notif_signals); setMacro(p.notif_macro); }
    });
  }, [rafraichir]);

  async function majNotif(champ: "notif_signals" | "notif_macro", v: boolean) {
    const { data } = await supabase.auth.getSession();
    const id = data.session?.user?.id;
    if (id) await supabase.from("profiles").update({ [champ]: v }).eq("id", id);
  }

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
      <EnTete titre="Compte" sousTitre={email} droite={<Logo hauteur={38} />} />

      {/* ------------------------------------------- l'abonnement */}
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

      {/* ------------------------------------------- ton capital */}
      <Rubrique titre="Ton capital">
        <Carte>
          <T v="petit">
            Sert uniquement a te dire, sur chaque signal, ce que la
            position peut te couter en euros. Ce chiffre reste sur ton
            telephone : il n'est envoye nulle part.
          </T>
          <View style={{ flexDirection: "row", alignItems: "center",
                         marginTop: espace.m }}>
            <TextInput
              value={capital}
              onChangeText={setCapital}
              onEndEditing={() => enregistrerCapital(Number(capital))}
              keyboardType="numeric"
              style={{
                flex: 1, backgroundColor: c.creux, color: c.encre,
                borderRadius: rayon.s, paddingHorizontal: espace.m,
                paddingVertical: espace.m, fontSize: 17,
                fontVariant: ["tabular-nums"],
              }}
              placeholderTextColor={c.encrePale}
            />
            <T v="sousTitre" style={{ marginLeft: espace.m }}>€</T>
          </View>
          <T v="legende" style={{ marginTop: espace.s }}>
            Exemple : sur {euros(Number(capital) || CAPITAL_DEFAUT, 0)}, un
            signal a 0,6 % risque {euros((Number(capital) || CAPITAL_DEFAUT)
              * 0.006)}.
          </T>
        </Carte>
      </Rubrique>

      {/* ------------------------------------------ notifications */}
      <Rubrique titre="Notifications">
        <Carte>
          <LigneReglage
            titre="Nouveaux signaux" valeur={signaux}
            onChange={(v) => { setSignaux(v); majNotif("notif_signals", v); }}
          />
          <Separateur />
          <LigneReglage
            titre="Annonces economiques"
            detail="Quinze minutes avant les plus importantes"
            valeur={macro}
            onChange={(v) => { setMacro(v); majNotif("notif_macro", v); }}
          />
          <Separateur />
          <T v="legende" style={{ marginTop: espace.m, lineHeight: 16 }}>
            Rien n'est envoye entre 23 h et 7 h, heure de chez toi.
          </T>
        </Carte>
      </Rubrique>

      {/* ------------------------------------- ce qu'Allure ne fait pas */}
      <Rubrique titre="Ce qu'Allure ne fait pas">
        <Carte>
          {[
            "Allure ne touche jamais a ton argent. Aucune connexion a ton " +
            "compte, aucun ordre passe a ta place.",
            "Allure ne te demande jamais tes cles d'echange, ni ton mot de " +
            "passe Bitvavo ou Binance. Personne de serieux ne le fait.",
            "Allure ne promet aucun gain. Les signaux publies sont ceux " +
            "d'un robot qui engage son propre argent, et il perd " +
            "regulierement.",
          ].map((texte, i) => (
            <T key={i} v="petit" style={{ marginBottom: espace.m,
                                          lineHeight: 20 }}>
              {texte}
            </T>
          ))}
        </Carte>
      </Rubrique>

      {/* --------------------------------------------------- legal */}
      <Rubrique titre="Informations">
        <Carte>
          {[
            ["Conditions d'utilisation", "https://allure-trading.fr/cgu"],
            ["Politique de confidentialite", "https://allure-trading.fr/confidentialite"],
            ["Nous ecrire", "mailto:contact@allure-trading.fr"],
          ].map(([libelle, url]) => (
            <T key={url} v="corps" couleur={c.encre}
               style={{ paddingVertical: espace.s,
                        textDecorationLine: "underline" }}
               onPress={() => Linking.openURL(url)}>
              {libelle}
            </T>
          ))}
          <T v="corps" couleur={c.encre}
             style={{ paddingVertical: espace.s,
                      textDecorationLine: "underline" }}
             onPress={onRevoirPresentation}>
            Revoir la presentation de l'application
          </T>
          <Separateur marge={espace.s} />
          <T v="corps" couleur={c.perte} style={{ paddingVertical: espace.s }}
             onPress={() => supabase.auth.signOut()}>
            Se deconnecter
          </T>
        </Carte>
      </Rubrique>

      <T v="legende" style={{ textAlign: "center", marginTop: espace.xxl,
                              lineHeight: 17 }}>
        Allure publie des analyses de marche. Ce n'est pas un conseil en
        investissement personnalise. Nous ne detenons aucun fonds.
      </T>
    </ScrollView>
  );
}
