/**
 * Onglet Compte — abonnement, reglages, et ce qu'Eve ne fait pas.
 *
 * L'ARGUMENTAIRE D'ABONNEMENT EST ICI, ET IL EST FACTUEL.
 * Pas de « rejoins des milliers de traders », pas de temoignage, pas de
 * chiffre de gain. Trois lignes qui disent exactement ce qu'on recoit
 * en plus. Un argumentaire honnete convainc moins vite qu'un
 * argumentaire vendeur — mais il ne produit pas de rembourse­ment a
 * J+3, et c'est lui qu'on transmet a un ami.
 */

import React from "react";
import {
  Alert, Linking, ScrollView, StyleSheet, Switch, TextInput, View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  lireOffre, lirePalier, OffrePlus, ouvrirGestionPlay, prochainPrelevement,
  restaurer, souscrire,
} from "../services/abonnement";
import { CAPITAL_DEFAUT, enregistrerCapital, useCapital }
  from "../services/reglages";
import { supabase } from "../services/supabase";
import { euros } from "../services/format";
import { espace, rayon } from "../theme";
import { Bouton, Carte, Separateur, T, useCouleurs } from "../composants/base";

function Rubrique({ titre, children }: {
  titre: string; children: React.ReactNode;
}) {
  return (
    <View style={{ marginTop: espace.xxl }}>
      <T v="etiquette" style={{ marginBottom: espace.s }}>{titre}</T>
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
              trackColor={{ true: c.laiton, false: c.creux }}
              thumbColor={c.surface} />
    </View>
  );
}

export function EcranCompte({ email }: { email: string }) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const capitalEnregistre = useCapital();

  const [palier, setPalier] = React.useState<"free" | "plus">("free");
  const [offre, setOffre] = React.useState<OffrePlus | null>(null);
  const [echeance, setEcheance] = React.useState<Date | null>(null);
  const [achatEnCours, setAchat] = React.useState(false);
  const [capital, setCapital] = React.useState(String(CAPITAL_DEFAUT));
  const [signaux, setSignaux] = React.useState(true);
  const [macro, setMacro] = React.useState(true);

  React.useEffect(() => { setCapital(String(capitalEnregistre)); },
                  [capitalEnregistre]);

  const rafraichirPalier = React.useCallback(async () => {
    setPalier(await lirePalier());
    setEcheance(await prochainPrelevement());
  }, []);

  React.useEffect(() => {
    rafraichirPalier();
    lireOffre().then(setOffre);
    supabase.auth.getSession().then(async ({ data }) => {
      const id = data.session?.user?.id;
      if (!id) return;
      const { data: p } = await supabase
        .from("profiles").select("notif_signals, notif_macro")
        .eq("id", id).single();
      if (p) { setSignaux(p.notif_signals); setMacro(p.notif_macro); }
    });
  }, [rafraichirPalier]);

  async function majNotif(champ: "notif_signals" | "notif_macro", v: boolean) {
    const { data } = await supabase.auth.getSession();
    const id = data.session?.user?.id;
    if (id) await supabase.from("profiles").update({ [champ]: v }).eq("id", id);
  }

  async function acheter() {
    if (!offre) return;
    setAchat(true);
    const resultat = await souscrire(offre);
    setAchat(false);
    if (resultat === "annule") return;
    if (resultat === "echec") {
      Alert.alert("Achat non abouti",
                  "Rien n'a ete preleve. Tu peux reessayer.");
      return;
    }
    // LE DEBLOCAGE VIENT DU SERVEUR, PAS DE L'ACHAT.
    // RevenueCat previent notre serveur par webhook ; on attend un
    // instant puis on relit le profil. Debloquer localement ferait
    // apparaitre un abonne que le serveur ne reconnait pas — et qui
    // verrait un ecran vide.
    setTimeout(rafraichirPalier, 2500);
    Alert.alert("C'est fait",
                "Ton abonnement est actif. Les signaux en temps reel " +
                "arrivent dans quelques secondes.");
  }

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <T v="titreGrand">Compte</T>
      <T v="petit" style={{ marginTop: 2 }}>{email}</T>

      {/* ------------------------------------------- l'abonnement */}
      <Rubrique titre={palier === "plus" ? "Ton abonnement" : "Eve Plus"}>
        {palier === "plus" ? (
          <Carte accent={c.laiton}>
            <T v="titre">Eve Plus, actif</T>
            {echeance ? (
              <T v="petit" style={{ marginTop: espace.s }}>
                Prochain prelevement le{" "}
                {echeance.toLocaleDateString("fr-FR", {
                  day: "numeric", month: "long", year: "numeric" })}.
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
        ) : (
          <Carte accent={c.laiton}>
            <T v="titre">Les signaux au moment ou ils sortent</T>

            {/* Trois lignes factuelles. Ce qu'on recoit, rien d'autre. */}
            <View style={{ marginTop: espace.l }}>
              {[
                ["Les 70 cryptos suivies", "au lieu de trois"],
                ["Au moment ou le robot agit", "au lieu de deux heures apres"],
                ["Notification a l'ouverture et a la fermeture", ""],
              ].map(([titre, detail], i) => (
                <View key={i} style={{ flexDirection: "row",
                                       marginBottom: espace.m }}>
                  <View style={{ width: 14, height: StyleSheet.hairlineWidth,
                                 backgroundColor: c.laiton, marginTop: 11,
                                 marginRight: espace.m }} />
                  <View style={{ flex: 1 }}>
                    <T v="corps">{titre}</T>
                    {detail ? <T v="petit">{detail}</T> : null}
                  </View>
                </View>
              ))}
            </View>

            <Separateur marge={espace.m} />

            {offre ? (
              <>
                <View style={{ flexDirection: "row", alignItems: "baseline",
                               marginBottom: espace.l }}>
                  <T v="chiffre" style={{ fontSize: 26 }}>{offre.prix}</T>
                  <T v="petit" style={{ marginLeft: espace.s }}>
                    {offre.periode}
                  </T>
                </View>
                <Bouton
                  titre={achatEnCours ? "Un instant..."
                    : offre.essaiJours
                      ? `Essayer ${offre.essaiJours} jours gratuitement`
                      : "S'abonner"}
                  onPress={acheter}
                  desactive={achatEnCours}
                />
                <T v="legende" style={{ marginTop: espace.m, lineHeight: 16 }}>
                  {offre.essaiJours
                    ? `Sans engagement. Rien n'est preleve pendant ` +
                      `${offre.essaiJours} jours, et tu peux arreter a tout ` +
                      `moment depuis Google Play. `
                    : "Sans engagement, resiliable a tout moment. "}
                  Le paiement est gere par Google Play : nous ne voyons
                  jamais ta carte.
                </T>
              </>
            ) : (
              <T v="petit">
                L'offre n'est pas disponible pour le moment.
              </T>
            )}

            <View style={{ marginTop: espace.l }}>
              <Bouton
                titre="J'ai deja un abonnement"
                variante="discret"
                onPress={async () => {
                  const ok = await restaurer();
                  await rafraichirPalier();
                  Alert.alert(
                    ok ? "Abonnement retrouve" : "Aucun abonnement trouve",
                    ok ? "Ton acces est retabli."
                       : "Verifie que tu utilises le meme compte Google.");
                }}
              />
            </View>
          </Carte>
        )}
      </Rubrique>

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

      {/* ------------------------------------- ce qu'Eve ne fait pas */}
      <Rubrique titre="Ce qu'Eve ne fait pas">
        <Carte>
          {[
            "Eve ne touche jamais a ton argent. Aucune connexion a ton " +
            "compte, aucun ordre passe a ta place.",
            "Eve ne te demande jamais tes cles d'echange, ni ton mot de " +
            "passe Bitvavo ou Binance. Personne de serieux ne le fait.",
            "Eve ne promet aucun gain. Les signaux publies sont ceux d'un " +
            "robot qui engage son propre argent, et il perd regulierement.",
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
            ["Conditions d'utilisation", "https://eve-signaux.fr/cgu"],
            ["Politique de confidentialite", "https://eve-signaux.fr/confidentialite"],
            ["Nous ecrire", "mailto:contact@eve-signaux.fr"],
          ].map(([libelle, url]) => (
            <T key={url} v="corps" couleur={c.laiton}
               style={{ paddingVertical: espace.s }}
               onPress={() => Linking.openURL(url)}>
              {libelle}
            </T>
          ))}
          <Separateur marge={espace.s} />
          <T v="corps" couleur={c.baisse} style={{ paddingVertical: espace.s }}
             onPress={() => supabase.auth.signOut()}>
            Se deconnecter
          </T>
        </Carte>
      </Rubrique>

      <T v="legende" style={{ textAlign: "center", marginTop: espace.xxl,
                              lineHeight: 17 }}>
        Eve publie des analyses de marche. Ce n'est pas un conseil en
        investissement personnalise. Nous ne detenons aucun fonds.
      </T>
    </ScrollView>
  );
}
