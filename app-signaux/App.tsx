/**
 * L'assemblage ALLURE : polices, session, navigation.
 *
 * L'ORDRE DES ECRANS N'EST PAS ARBITRAIRE.
 *   accueil (une fois) -> connexion -> les six onglets
 *
 * L'accueil vient AVANT la connexion. Demander une adresse e-mail a
 * quelqu'un qui ne sait pas encore ce que fait l'application est le
 * meilleur moyen de le perdre — et c'est ce que font la plupart des
 * applications du genre.
 *
 * L'ORDRE DES ONGLETS SUIT L'USAGE, PAS L'ORGANIGRAMME.
 *   Direct   — ce qui bouge maintenant. C'est pour ca qu'on ouvre.
 *   Signaux  — ce qu'il faut faire, et l'historique.
 *   Cours    — les graphiques, quand on veut verifier de ses yeux.
 *   Analyse  — le point du matin et l'agenda, une fois par jour.
 *   Essayer  — la demonstration, pour qui hesite encore.
 *   Compte   — les offres et les reglages, rarement.
 */

import React from "react";
import { View } from "react-native";
import { NavigationContainer, DefaultTheme, DarkTheme }
  from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import * as Linking from "expo-linking";
import * as Notifications from "expo-notifications";
import { useFonts } from "expo-font";
import {
  Fraunces_400Regular_Italic, Fraunces_600SemiBold,
} from "@expo-google-fonts/fraunces";
import { Archivo_400Regular, Archivo_600SemiBold }
  from "@expo-google-fonts/archivo";
import { IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "./src/services/supabase";
import { demarrerAbonnement } from "./src/services/abonnement";
import { accueilDejaVu, marquerAccueilVu } from "./src/services/reglages";
import { FournisseurTheme, Logo, T, useCouleurs, useTheme }
  from "./src/composants/base";
import { EcranAccueil } from "./src/ecrans/Accueil";
import { EcranConnexion } from "./src/ecrans/Connexion";
import { EcranDirect } from "./src/ecrans/Direct";
import { EcranSignaux } from "./src/ecrans/Signaux";
import { EcranCours } from "./src/ecrans/Cours";
import { EcranAnalyse } from "./src/ecrans/Analyse";
import { EcranDemo } from "./src/ecrans/Demo";
import { EcranCompte } from "./src/ecrans/Compte";
import { EcranBitvavo } from "./src/ecrans/Bitvavo";
import { espace, polices, TRAIT } from "./src/theme";

const Onglets = createBottomTabNavigator();

/**
 * L'icone d'un onglet : un TRAIT JAUNE, pas un pictogramme.
 *
 * Les pictogrammes de barre d'onglets sont soit generiques (une maison,
 * un graphique), soit ambigus. Un libelle lisible surmonte du trait
 * ALLURE dit plus, et laisse la typographie porter l'identite.
 */
function Trait({ actif }: { actif: boolean }) {
  const c = useCouleurs();
  return (
    <View style={{
      width: 16, height: TRAIT, marginBottom: 4,
      backgroundColor: actif ? c.jaune : "transparent",
    }} />
  );
}

function Navigation({ session }: { session: Session }) {
  const c = useCouleurs();
  const theme = useTheme();
  const [, setVersCompte] = React.useState(0);

  React.useEffect(() => {
    demarrerAbonnement(session.user.id).catch(() => { /* sans magasin */ });
  }, [session.user.id]);

  // Le jeton de notification : enregistre une fois, sur le profil.
  React.useEffect(() => {
    (async () => {
      try {
        const { status } = await Notifications.requestPermissionsAsync();
        if (status !== "granted") return;
        const jeton = (await Notifications.getDevicePushTokenAsync()).data;
        const fuseau = Intl.DateTimeFormat().resolvedOptions().timeZone;
        await supabase.from("profiles")
          .update({ push_token: jeton, timezone: fuseau })
          .eq("id", session.user.id);
      } catch {
        // Un refus de notification n'empeche pas d'utiliser l'application.
      }
    })();
  }, [session.user.id]);

  const base = theme === "clair" ? DefaultTheme : DarkTheme;

  return (
    <NavigationContainer theme={{
      ...base,
      colors: { ...base.colors, background: c.fond, card: c.surface,
                text: c.encre, border: c.filetDoux, primary: c.jaune },
    }}>
      <Onglets.Navigator
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: c.encre,
          tabBarInactiveTintColor: c.encrePale,
          tabBarStyle: {
            backgroundColor: c.surface,
            borderTopColor: c.filet,
            borderTopWidth: TRAIT,
            height: 64, paddingTop: 8, paddingBottom: 10,
          },
          tabBarLabelStyle: {
            fontFamily: polices.interfaceGras, fontSize: 10,
            letterSpacing: 0.4,
          },
          tabBarIcon: ({ focused }) => <Trait actif={focused} />,
        }}
      >
        <Onglets.Screen name="Direct" options={{ title: "Direct" }}>
          {({ navigation }) => (
            <EcranDirect
              versAbonnement={() => navigation.navigate("Compte" as never)} />
          )}
        </Onglets.Screen>

        <Onglets.Screen name="Signaux" options={{ title: "Signaux" }}>
          {({ navigation }) => (
            <EcranSignaux
              versAbonnement={() => navigation.navigate("Compte" as never)} />
          )}
        </Onglets.Screen>

        <Onglets.Screen name="Cours" component={EcranCours} />
        <Onglets.Screen name="Analyse" component={EcranAnalyse} />

        <Onglets.Screen name="Essayer" options={{ title: "Essayer" }}>
          {({ navigation }) => (
            <EcranDemo
              versAbonnement={() => navigation.navigate("Compte" as never)} />
          )}
        </Onglets.Screen>

        <Onglets.Screen name="Compte" options={{ title: "Compte" }}>
          {() => <EcranCompte email={session.user.email ?? ""} />}
        </Onglets.Screen>
      </Onglets.Navigator>
    </NavigationContainer>
  );
}

function Racine() {
  const c = useCouleurs();
  const [session, setSession] = React.useState<Session | null>(null);
  const [accueilVu, setAccueilVu] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    accueilDejaVu().then(setAccueilVu);
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange(
      (_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  // Le retour du lien magique arrive par le schema `allure://`.
  React.useEffect(() => {
    const traiter = async (url: string) => {
      const { queryParams } = Linking.parse(url);
      const jeton = queryParams?.token_hash;
      if (typeof jeton !== "string") return;
      await supabase.auth.verifyOtp({ token_hash: jeton, type: "email" });
    };
    Linking.getInitialURL().then((u) => { if (u) traiter(u); });
    const abo = Linking.addEventListener("url", ({ url }) => traiter(url));
    return () => abo.remove();
  }, []);

  if (accueilVu === null) {
    return <View style={{ flex: 1, backgroundColor: c.fond }} />;
  }
  if (!accueilVu) {
    return (
      <EcranAccueil onTermine={() => {
        marquerAccueilVu(); setAccueilVu(true);
      }} />
    );
  }
  if (!session) return <EcranConnexion />;
  return <Navigation session={session} />;
}

export default function App() {
  const [policesPretes] = useFonts({
    Fraunces_600SemiBold,
    Fraunces_400Regular_Italic,
    Archivo_400Regular,
    Archivo_600SemiBold,
    IBMPlexMono_500Medium,
  });

  return (
    <SafeAreaProvider>
      <FournisseurTheme>
        <StatusBar style="auto" />
        {policesPretes ? <Racine /> : <EcranDeLancement />}
      </FournisseurTheme>
    </SafeAreaProvider>
  );
}

/**
 * L'ecran affiche pendant le chargement des polices.
 *
 * Il porte le logo, pas une roue qui tourne. Le passage a l'application
 * est alors imperceptible.
 */
function EcranDeLancement() {
  const c = useCouleurs();
  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   alignItems: "center", justifyContent: "center" }}>
      <Logo hauteur={84} />
      <View style={{ width: 34, height: TRAIT, backgroundColor: c.jaune,
                     marginTop: espace.xl }} />
    </View>
  );
}
