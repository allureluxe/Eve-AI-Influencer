/**
 * L'assemblage : polices, session, navigation.
 *
 * L'ORDRE DES ECRANS N'EST PAS ARBITRAIRE.
 *   accueil (une fois) -> connexion -> les quatre onglets
 *
 * L'accueil vient AVANT la connexion. Demander une adresse e-mail a
 * quelqu'un qui ne sait pas encore ce que fait l'application est le
 * meilleur moyen de le perdre — et c'est ce que font la plupart des
 * applications du genre.
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
  Newsreader_400Regular_Italic, Newsreader_600SemiBold,
} from "@expo-google-fonts/newsreader";
import {
  IBMPlexSans_400Regular, IBMPlexSans_600SemiBold,
} from "@expo-google-fonts/ibm-plex-sans";
import { IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "./src/services/supabase";
import { demarrerAbonnement } from "./src/services/abonnement";
import { accueilDejaVu, marquerAccueilVu } from "./src/services/reglages";
import { FournisseurTheme, T, useCouleurs, useTheme } from "./src/composants/base";
import { EcranAccueil } from "./src/ecrans/Accueil";
import { EcranConnexion } from "./src/ecrans/Connexion";
import { EcranSignaux } from "./src/ecrans/Signaux";
import { EcranAnalyse } from "./src/ecrans/Analyse";
import { EcranAgenda } from "./src/ecrans/Agenda";
import { EcranCompte } from "./src/ecrans/Compte";
import { espace, polices } from "./src/theme";

const Onglets = createBottomTabNavigator();

/**
 * L'icone d'un onglet : un point, pas un pictogramme.
 *
 * Les pictogrammes de barre d'onglets sont soit generiques (une maison,
 * un graphique), soit ambigus. Un libelle lisible et un point discret
 * disent plus, et laissent la typographie porter l'identite.
 */
function Point({ actif }: { actif: boolean }) {
  const c = useCouleurs();
  return (
    <View style={{
      width: 4, height: 4, borderRadius: 2, marginBottom: 3,
      backgroundColor: actif ? c.laiton : "transparent",
    }} />
  );
}

function Navigation({ session }: { session: Session }) {
  const c = useCouleurs();
  const theme = useTheme();
  const [versCompte, setVersCompte] = React.useState(0);

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
                text: c.encre, border: c.filet, primary: c.laiton },
    }}>
      <Onglets.Navigator
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarActiveTintColor: c.encre,
          tabBarInactiveTintColor: c.encrePale,
          tabBarStyle: {
            backgroundColor: c.surface, borderTopColor: c.filet,
            height: 62, paddingTop: 8, paddingBottom: 10,
          },
          tabBarLabelStyle: {
            fontFamily: polices.interfaceGras, fontSize: 11,
            letterSpacing: 0.3,
          },
          tabBarIcon: ({ focused }) => <Point actif={focused} />,
        })}
      >
        <Onglets.Screen name="Signaux" options={{ title: "Signaux" }}>
          {() => <EcranSignaux versAbonnement={() => setVersCompte((n) => n + 1)} />}
        </Onglets.Screen>
        <Onglets.Screen name="Analyse" component={EcranAnalyse} />
        <Onglets.Screen name="Agenda" component={EcranAgenda} />
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

  // Le retour du lien magique arrive par le schema `eve://`.
  React.useEffect(() => {
    const traiter = async (url: string) => {
      const { queryParams } = Linking.parse(url);
      const jeton = queryParams?.token_hash ?? queryParams?.access_token;
      if (typeof jeton !== "string") return;
      if (queryParams?.token_hash) {
        await supabase.auth.verifyOtp({ token_hash: jeton, type: "email" });
      }
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
    Newsreader_600SemiBold,
    Newsreader_400Regular_Italic,
    IBMPlexSans_400Regular,
    IBMPlexSans_600SemiBold,
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
 * Il porte le nom, dans la police finale des titres — pas de roue qui
 * tourne. Le passage a l'application est alors imperceptible.
 */
function EcranDeLancement() {
  const c = useCouleurs();
  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   alignItems: "center", justifyContent: "center" }}>
      <T style={{ fontFamily: polices.titre, fontSize: 44, color: c.encre }}>
        Eve
      </T>
      <View style={{ width: 26, height: 1, backgroundColor: c.filet,
                     marginTop: espace.l }} />
    </View>
  );
}
