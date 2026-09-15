/**
 * Alluxe Bot -- l'outil prive de pilotage du robot de trading.
 *
 * PROPRIETE DE LENY LUDOVIC. Application privee, personnelle, exclusive
 * a l'operateur -- aucune reprise ou reutilisation sans son accord.
 *
 * DECISION EXPLICITE DU 15 SEPTEMBRE : cette application n'a NI
 * inscription NI ecran de connexion email/mot de passe -- contrairement
 * a Allure, elle n'est faite que pour une seule personne. L'appli
 * s'authentifie donc seule aupres de Supabase, en arriere-plan, avec un
 * compte de service dedie (jamais montre, jamais demande). La seule
 * chose demandee a l'ouverture est une verification d'identite locale
 * (l'annee de naissance de l'operateur, voir ecrans/Verification.tsx) --
 * PAS un mot de passe a retenir, juste de quoi lever un doute si
 * jamais quelqu'un d'autre ouvrait ce telephone.
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
import Constants from "expo-constants";

import { supabase } from "./src/services/supabase";
import { FournisseurTheme, Logo, T, useCouleurs, useTheme }
  from "./src/composants/base";
import { EcranVerification } from "./src/ecrans/Verification";
import { EcranDirect } from "./src/ecrans/Direct";
import { EcranHistorique } from "./src/ecrans/Historique";
import { EcranObjectifs } from "./src/ecrans/Objectifs";
import { EcranDiscussion } from "./src/ecrans/Discussion";
import { espace, polices, TRAIT } from "./src/theme";

const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string>;

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
  const [connecte, setConnecte] = React.useState(false);
  const [erreurConnexion, setErreurConnexion] = React.useState("");
  const [verifie, setVerifie] = React.useState(false);

  // Connexion invisible : le compte de service, jamais un formulaire.
  React.useEffect(() => {
    (async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (session) { setConnecte(true); return; }
      if (!extra.serviceEmail || !extra.servicePassword) {
        setErreurConnexion("Compte de service non configure.");
        return;
      }
      const { error } = await supabase.auth.signInWithPassword({
        email: extra.serviceEmail, password: extra.servicePassword,
      });
      if (error) setErreurConnexion(error.message);
      else setConnecte(true);
    })();
  }, []);

  if (erreurConnexion) return <EcranDeLancement erreur={erreurConnexion} />;
  if (!connecte) return <EcranDeLancement />;
  if (!verifie) return <EcranVerification surReussite={() => setVerifie(true)} />;
  return <Navigation />;
}

function EcranDeLancement({ erreur }: { erreur?: string }) {
  const c = useCouleurs();
  return (
    <View style={{ flex: 1, backgroundColor: c.fond,
                   alignItems: "center", justifyContent: "center",
                   paddingHorizontal: espace.xl }}>
      <Logo hauteur={84} />
      <T v="titreGrand" style={{ marginTop: espace.l }}>Alluxe Bot</T>
      <T v="corps" couleur={erreur ? c.perte : c.encreDouce}
         style={{ textAlign: "center", marginTop: espace.s }}>
        {erreur ?? "Le pilotage prive du robot."}
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
