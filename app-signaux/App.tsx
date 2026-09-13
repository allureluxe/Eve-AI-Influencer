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
 *   Marche   — les cours et l'agenda : « ou en est le prix » et
 *              « qu'est-ce qui va le bouger », la meme question a deux
 *              echelles de temps.
 *   Analyse  — le point du matin, l'historique chiffre, et la
 *              demonstration a trois montants.
 *   Bitvavo  — ou passer ses ordres, et le parrainage.
 *   Compte   — les offres et les reglages, rarement.
 *
 * SIX ONGLETS EST LE MAXIMUM. Au-dela, les libelles deviennent
 * illisibles et plus personne ne trouve rien. C'est pourquoi Cours et
 * Agenda partagent « Marche », et pourquoi la demonstration vit dans
 * « Analyse » plutot que d'occuper une place a elle.
 */

import React from "react";
import { View } from "react-native";
import { NavigationContainer, DefaultTheme, DarkTheme }
  from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import * as Notifications from "expo-notifications";
import { useFonts } from "expo-font";
import {
  Fraunces_400Regular_Italic, Fraunces_600SemiBold,
} from "@expo-google-fonts/fraunces";
import { Archivo_400Regular, Archivo_600SemiBold }
  from "@expo-google-fonts/archivo";
import { IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono";
import type { Session } from "@supabase/supabase-js";

import * as Linking from "expo-linking";
import { supabase } from "./src/services/supabase";
import type { EmailOtpType } from "@supabase/supabase-js";
import { demarrerAbonnement } from "./src/services/abonnement";
import { accueilDejaVu, marquerAccueilVu } from "./src/services/reglages";
import { FournisseurTheme, Logo, T, useCouleurs, useTheme }
  from "./src/composants/base";
import { EcranAccueil } from "./src/ecrans/Accueil";
import { EcranConnexion } from "./src/ecrans/Connexion";
import { EcranDirect } from "./src/ecrans/Direct";
import { EcranSignaux } from "./src/ecrans/Signaux";
import { EcranMarche } from "./src/ecrans/Marche";
import { EcranAnalyse } from "./src/ecrans/Analyse";
import { EcranCompte } from "./src/ecrans/Compte";
import { EcranBitvavo } from "./src/ecrans/Bitvavo";
import { espace, polices, TRAIT } from "./src/theme";

const Onglets = createBottomTabNavigator();

/**
 * L'icone d'un onglet.
 *
 * Un simple trait jaune de 16x2 px etait invisible pour qui ne connait
 * pas deja le langage graphique ALLURE (retour reel, 13 sept.) : « les
 * onglets sont invisibles ». Un pictogramme reconnaissable, dans une
 * pastille jaune quand l'onglet est actif, se comprend sans explication
 * — c'est le prix a payer pour rester utilisable par un debutant, meme
 * si c'est moins « signature » qu'un trait epure.
 */
const ICONES_ONGLET: Record<string, keyof typeof Ionicons.glyphMap> = {
  Direct: "flash-outline",
  Signaux: "list-outline",
  Marche: "stats-chart-outline",
  Analyse: "analytics-outline",
  Bitvavo: "swap-horizontal-outline",
  Compte: "person-outline",
};

function IconeOnglet({ route, actif }: { route: string; actif: boolean }) {
  const c = useCouleurs();
  return (
    <View style={{
      width: 40, height: 28, borderRadius: 14,
      alignItems: "center", justifyContent: "center",
      backgroundColor: actif ? c.jaune : "transparent",
    }}>
      <Ionicons
        name={ICONES_ONGLET[route] ?? "ellipse-outline"}
        size={20}
        color={actif ? c.surJaune : c.encrePale}
      />
    </View>
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
        screenOptions={({ route }) => ({
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
          tabBarIcon: ({ focused }) => (
            <IconeOnglet route={route.name} actif={focused} />
          ),
        })}
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

        <Onglets.Screen name="Marche" options={{ title: "Marche" }}
                        component={EcranMarche} />

        <Onglets.Screen name="Analyse" options={{ title: "Analyse" }}>
          {({ navigation }) => (
            <EcranAnalyse
              versAbonnement={() => navigation.navigate("Compte" as never)} />
          )}
        </Onglets.Screen>

        <Onglets.Screen name="Bitvavo" options={{ title: "Bitvavo" }}
                        component={EcranBitvavo} />

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

  // Le lien de confirmation d'inscription arrive par le schema
  // `allure://`. L'e-mail est desormais obligatoire (decision de
  // l'operateur, 13 sept.) : sans ce traitement, un compte tout juste
  // cree resterait bloque a "en attente de confirmation" pour toujours.
  React.useEffect(() => {
    const traiter = async (url: string) => {
      const { queryParams } = Linking.parse(url);
      const jeton = queryParams?.token_hash;
      if (typeof jeton !== "string") return;
      const type: EmailOtpType = typeof queryParams?.type === "string"
        ? queryParams.type as EmailOtpType : "signup";
      const { error } = await supabase.auth.verifyOtp({
        token_hash: jeton, type });
      if (error) console.warn("verifyOtp a echoue :", error.message);
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
