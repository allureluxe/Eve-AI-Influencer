/**
 * Alluxe Bot -- l'outil prive de pilotage du robot de trading.
 *
 * Beaucoup plus simple qu'Allure : un seul utilisateur (l'operateur),
 * pas d'inscription, pas de paiement, pas de notifications push. Juste
 * une connexion (compte Allure existant) puis quatre onglets.
 */
import React from "react";
import { View } from "react-native";
import { NavigationContainer, DefaultTheme, DarkTheme }
  from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useFonts } from "expo-font";
import {
  Fraunces_600SemiBold, Fraunces_400Regular_Italic,
} from "@expo-google-fonts/fraunces";
import { Archivo_400Regular, Archivo_600SemiBold }
  from "@expo-google-fonts/archivo";
import { IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "./src/services/supabase";
import { FournisseurTheme, Logo, T, useCouleurs, useTheme }
  from "./src/composants/base";
import { EcranConnexion } from "./src/ecrans/Connexion";
import { EcranDirect } from "./src/ecrans/Direct";
import { EcranHistorique } from "./src/ecrans/Historique";
import { EcranObjectifs } from "./src/ecrans/Objectifs";
import { EcranDiscussion } from "./src/ecrans/Discussion";
import { espace, polices, TRAIT } from "./src/theme";

const Onglets = createBottomTabNavigator();

const ICONES_ONGLET: Record<string, keyof typeof Ionicons.glyphMap> = {
  Direct: "flash-outline",
  Historique: "time-outline",
  Objectifs: "trending-up-outline",
  Discussion: "chatbubble-ellipses-outline",
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

function Navigation() {
  const c = useCouleurs();
  const theme = useTheme();
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
        <Onglets.Screen name="Direct" component={EcranDirect} />
        <Onglets.Screen name="Historique" component={EcranHistorique} />
        <Onglets.Screen name="Objectifs" component={EcranObjectifs} />
        <Onglets.Screen name="Discussion" component={EcranDiscussion} />
      </Onglets.Navigator>
    </NavigationContainer>
  );
}

function Racine() {
  const [session, setSession] = React.useState<Session | null>(null);
  const [sessionPrete, setSessionPrete] = React.useState(false);

  React.useEffect(() => {
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s);
      setSessionPrete(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange(
      (_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (!sessionPrete) return <EcranDeLancement />;
  if (!session) return <EcranConnexion />;
  return <Navigation />;
}

function EcranDeLancement() {
  const c = useCouleurs();
  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   alignItems: "center", justifyContent: "center",
                   paddingHorizontal: espace.xl }}>
      <Logo hauteur={84} />
      <T v="titreGrand" style={{ marginTop: espace.l }}>Alluxe Bot</T>
      <T v="corps" couleur={c.encreDouce}
         style={{ textAlign: "center", marginTop: espace.s }}>
        Le pilotage prive du robot.
      </T>
    </View>
  );
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
