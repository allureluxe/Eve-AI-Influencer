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
import { NavigationContainer, DefaultTheme, DarkTheme, createNavigationContainerRef }
  from "@react-navigation/native";
import * as Linking from "expo-linking";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
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
import * as Notifications from "expo-notifications";

import { supabase } from "./src/services/supabase";
import { FournisseurTheme, Logo, T, useCouleurs, useTheme }
  from "./src/composants/base";
import { EcranVerification } from "./src/ecrans/Verification";
import { EcranAccueil } from "./src/ecrans/Accueil";
import { EcranDirect } from "./src/ecrans/Direct";
import { EcranDemo } from "./src/ecrans/Demo";
import { EcranPosition } from "./src/ecrans/Position";
import { EcranHistorique } from "./src/ecrans/Historique";
import { EcranObjectifs } from "./src/ecrans/Objectifs";
import { EcranAlertes } from "./src/ecrans/Alertes";
import { EcranDiscussion } from "./src/ecrans/Discussion";
import { EcranLuna } from "./src/ecrans/Luna";
import { EcranAgent } from "./src/ecrans/Agent";
import { espace, polices, TRAIT } from "./src/theme";

import { EcranAccueil as EcranAccueilAllure } from "./src/allure/ecrans/Accueil";
import { EcranDirect as EcranDirectAllure } from "./src/allure/ecrans/Direct";
import { EcranSignaux as EcranSignauxAllure } from "./src/allure/ecrans/Signaux";
import { EcranAnalyseEtMarche as EcranAnalyseAllure } from "./src/allure/ecrans/AnalyseEtMarche";
import { EcranCompteEtBitvavo as EcranCompteAllure } from "./src/allure/ecrans/CompteEtBitvavo";

const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string>;

const navigationRef = createNavigationContainerRef<any>();

/**
 * Le reveil vocal (ServiceReveilVocal.kt, natif) ouvre l'application via
 * `alluxebot://reveil` quand il entend "Alluxe". Meme mecanisme de lien
 * profond qu'app-signaux (Allure) pour la confirmation d'e-mail --
 * `Linking`, pas de dependance nouvelle.
 */
function traiterLienReveil(url: string) {
  if (!url.includes("reveil")) return;
  if (!navigationRef.isReady()) return;
  navigationRef.navigate({
    name: "Agent", params: { autoEcoute: true, horodatage: Date.now() },
  } as never);
}

// Affiche la notification meme quand l'appli est deja ouverte -- sinon
// "achat/vente/robot suspendu" n'apparaitrait que si le telephone etait
// verrouille, ce qui n'est pas ce que l'operateur a demande.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true, shouldPlaySound: true, shouldSetBadge: false,
  }),
});

const Pile = createNativeStackNavigator();
const OngletsAlluxbot = createBottomTabNavigator();
const OngletsAllure = createBottomTabNavigator();

const ICONES_ALLUXBOT: Record<string, keyof typeof Ionicons.glyphMap> = {
  Direct: "flash-outline",
  Demo: "flask-outline",
  Historique: "time-outline",
  Objectifs: "trending-up-outline",
  Alertes: "notifications-outline",
  Discussion: "chatbubble-ellipses-outline",
};

const ICONES_ALLURE: Record<string, keyof typeof Ionicons.glyphMap> = {
  Accueil: "home-outline",
  Direct: "flash-outline",
  Signaux: "list-outline",
  Analyse: "analytics-outline",
  Compte: "person-outline",
};

function IconeOnglet({ icones, route, actif }: {
  icones: Record<string, keyof typeof Ionicons.glyphMap>;
  route: string; actif: boolean;
}) {
  const c = useCouleurs();
  return (
    <View style={{
      width: 40, height: 28, borderRadius: 14,
      alignItems: "center", justifyContent: "center",
      backgroundColor: actif ? c.jauneAplat : "transparent",
    }}>
      <Ionicons
        name={icones[route] ?? "ellipse-outline"}
        size={20}
        color={actif ? c.surJaune : c.encrePale}
      />
    </View>
  );
}

/** Options communes aux deux barres d'onglets (Alluxbot et Allure). */
function optionsOnglets(
  c: ReturnType<typeof useCouleurs>,
  icones: Record<string, keyof typeof Ionicons.glyphMap>,
) {
  return ({ route }: { route: { name: string } }) => ({
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
    tabBarIcon: ({ focused }: { focused: boolean }) => (
      <IconeOnglet icones={icones} route={route.name} actif={focused} />
    ),
  });
}

/** Alluxbot -- l'outil de pilotage deja construit le 15 septembre. */
function NavigationAlluxbot() {
  const c = useCouleurs();
  return (
    <OngletsAlluxbot.Navigator screenOptions={optionsOnglets(c, ICONES_ALLUXBOT)}>
      {/* `navigation` est transmis explicitement : c'est lui qui ouvre
          l'ecran de detail, declare sur la pile RACINE. Un onglet
          imbrique y remonte tout seul. */}
      <OngletsAlluxbot.Screen name="Direct">
        {({ navigation }) => <EcranDirect navigation={navigation} />}
      </OngletsAlluxbot.Screen>
      <OngletsAlluxbot.Screen name="Demo">
        {({ navigation }) => <EcranDemo navigation={navigation} />}
      </OngletsAlluxbot.Screen>
      <OngletsAlluxbot.Screen name="Historique" component={EcranHistorique} />
      <OngletsAlluxbot.Screen name="Objectifs" component={EcranObjectifs} />
      <OngletsAlluxbot.Screen name="Alertes" component={EcranAlertes} />
      <OngletsAlluxbot.Screen name="Discussion" component={EcranDiscussion} />
    </OngletsAlluxbot.Navigator>
  );
}

/**
 * Allure -- l'application publique, integree telle quelle en mode
 * administrateur. Pas d'ecran de connexion propre : la session du
 * compte de service, deja ouverte par Alluxe Bot, sert directement
 * (decision du 16 sept., voir REPRISE du 15 sept. point 5 -- c'est deja
 * un mode administrateur, une 2e authentification n'aurait aucun sens).
 */
function NavigationAllure({ email }: { email: string }) {
  const c = useCouleurs();
  return (
    <OngletsAllure.Navigator screenOptions={optionsOnglets(c, ICONES_ALLURE)}>
      <OngletsAllure.Screen name="Accueil" component={EcranAccueilAllure} />
      <OngletsAllure.Screen name="Direct">
        {({ navigation }) => (
          <EcranDirectAllure
            versAbonnement={() => navigation.navigate("Compte" as never)} />
        )}
      </OngletsAllure.Screen>
      <OngletsAllure.Screen name="Signaux">
        {({ navigation }) => (
          <EcranSignauxAllure
            versAbonnement={() => navigation.navigate("Compte" as never)} />
        )}
      </OngletsAllure.Screen>
      <OngletsAllure.Screen name="Analyse">
        {({ navigation }) => (
          <EcranAnalyseAllure
            versAbonnement={() => navigation.navigate("Compte" as never)} />
        )}
      </OngletsAllure.Screen>
      <OngletsAllure.Screen name="Compte">
        {() => <EcranCompteAllure email={email} />}
      </OngletsAllure.Screen>
    </OngletsAllure.Navigator>
  );
}

/**
 * La pile racine : Accueil (4 boutons) -> Alluxbot ou Allure.
 *
 * Le bouton retour flotte au-dessus du contenu (`headerTransparent`)
 * plutot que d'ajouter une 2e barre de titre -- chaque ecran gere deja
 * la sienne (logo + titre) en respectant les marges de securite, et un
 * vrai header natif ici doublonnerait ce qui existe.
 */
function Navigation() {
  const c = useCouleurs();
  const theme = useTheme();
  const base = theme === "clair" ? DefaultTheme : DarkTheme;
  // Une seule session possible ici : le compte de service. Les ecrans
  // Allure qui affichent un e-mail (Compte) montrent donc le sien.
  const email = extra.serviceEmail ?? "";

  // Reveil vocal : le service natif ouvre l'app via "alluxebot://reveil".
  // Attend que la pile de navigation soit prete (`onReady`) avant de
  // consommer l'URL de lancement -- sinon un demarrage a froid (app
  // tuee, reveillee par le mot-cle) perdrait le lien parce que le
  // navigateur n'existe pas encore au moment ou getInitialURL() repond.
  React.useEffect(() => {
    const abonnement = Linking.addEventListener("url", ({ url }) => traiterLienReveil(url));
    return () => abonnement.remove();
  }, []);

  return (
    <NavigationContainer
      ref={navigationRef}
      onReady={() => {
        Linking.getInitialURL().then((url) => { if (url) traiterLienReveil(url); });
      }}
      theme={{
      ...base,
      colors: { ...base.colors, background: c.fond, card: c.surface,
                text: c.encre, border: c.filetDoux, primary: c.jaune },
    }}>
      <Pile.Navigator
        screenOptions={{
          headerShown: false,
        }}
      >
        <Pile.Screen name="Accueil">
          {({ navigation }) => (
            <EcranAccueil surChoix={(cle) => navigation.navigate(cle)} />
          )}
        </Pile.Screen>
        <Pile.Screen name="Alluxbot" component={NavigationAlluxbot}
          options={{
            headerShown: true, headerTransparent: true, headerTitle: "",
            headerTintColor: c.encre, headerShadowVisible: false,
            headerBackTitleVisible: false,
          }} />
        <Pile.Screen name="Allure"
          options={{
            headerShown: true, headerTransparent: true, headerTitle: "",
            headerTintColor: c.encre, headerShadowVisible: false,
            headerBackTitleVisible: false,
          }}>
          {() => <NavigationAllure email={email} />}
        </Pile.Screen>
        <Pile.Screen name="Luna" component={EcranLuna}
          options={{
            headerShown: true, headerTransparent: true, headerTitle: "",
            headerTintColor: c.encre, headerShadowVisible: false,
            headerBackTitleVisible: false,
          }} />
        <Pile.Screen name="Position" component={EcranPosition}
          options={{
            headerShown: true, headerTransparent: true, headerTitle: "",
            headerTintColor: c.encre, headerShadowVisible: false,
            headerBackTitleVisible: false,
          }} />
        <Pile.Screen name="Agent" component={EcranAgent}
          options={{
            headerShown: true, headerTransparent: true, headerTitle: "",
            headerTintColor: c.encre, headerShadowVisible: false,
            headerBackTitleVisible: false,
          }} />
      </Pile.Navigator>
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

  // Jeton de notification : enregistre une fois connecte, sur la ligne
  // privee unique (un seul appareil, un seul operateur). Meme methode
  // qu'Allure (getDevicePushTokenAsync, pas le jeton Expo -- l'envoi se
  // fait directement via Firebase Cloud Messaging, voir
  // gold_bot/notifiers.py::FirebasePushChannel).
  React.useEffect(() => {
    if (!connecte) return;
    (async () => {
      try {
        const { status } = await Notifications.requestPermissionsAsync();
        if (status !== "granted") return;
        const jeton = (await Notifications.getDevicePushTokenAsync()).data;
        await supabase.from("alluxe_bot_prive")
          .update({ push_token: jeton }).eq("id", "robot");
      } catch {
        // Un refus de notification n'empeche pas d'utiliser l'application.
      }
    })();
  }, [connecte]);

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
