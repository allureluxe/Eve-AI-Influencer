// Meme mecanisme que app-signaux/app.config.js : lit process.env
// directement (dotenv en local, variables d'environnement du workflow
// GitHub Actions pour le build cloud) -- voir ce fichier-la pour le
// pourquoi complet.
require("dotenv").config();

// Mises a jour OTA (decision de l'operateur, 29 sept. puis 2 oct. 2026) :
// les changements JS/TS arrivent sans nouvel APK. Le projet EAS est
// cree le 2 oct. sur le compte Expo vps-eve (identifiant public, pas un
// secret) ; EAS_PROJECT_ID_ALLUXE_BOT peut le remplacer. `runtimeVersion` suit `version` :
// changer de version = changement natif = nouvel APK obligatoire.
const projetEas = process.env.EAS_PROJECT_ID_ALLUXE_BOT ?? "ce222d25-c311-434a-b295-69d5494a9c8a";

module.exports = () => ({
  expo: {
    name: "Alluxe Bot",
    slug: "alluxe-bot",
    owner: "vps-eve",
    version: "1.0.0",
    runtimeVersion: { policy: "appVersion" },
    updates: projetEas
      ? { enabled: true, url: `https://u.expo.dev/${projetEas}`, checkAutomatically: "ON_LOAD", fallbackToCacheTimeout: 0,
          requestHeaders: { "expo-channel-name": "production" } }
      : { enabled: false },
    orientation: "portrait",
    // Version web (3 oct. 2026) : servie sous un sous-chemin par GitHub
    // Pages (/Eve-AI-Influencer). Absent pour l'APK.
    ...(process.env.EXPO_BASE_URL ? { experiments: { baseUrl: process.env.EXPO_BASE_URL } } : {}),
    web: { name: "Alluxe Bot", shortName: "Alluxe Bot", favicon: "./assets/icone.png",
           themeColor: "#FFFFFF", backgroundColor: "#FFFFFF" },
    scheme: "alluxebot",
    userInterfaceStyle: "automatic",
    icon: "./assets/icone.png",
    splash: {
      image: "./assets/lancement.png",
      resizeMode: "contain",
      backgroundColor: "#FFFFFF",
    },
    android: {
      package: "fr.allure.alluxebot",
      versionCode: 2,
      googleServicesFile: "./google-services.json",
      adaptiveIcon: {
        foregroundImage: "./assets/icone-adaptative.png",
        backgroundColor: "#FFFFFF",
      },
      permissions: ["POST_NOTIFICATIONS", "USE_BIOMETRIC", "USE_FINGERPRINT"],
    },
    plugins: [
      "expo-font",
      "expo-notifications",
      "expo-speech-recognition",
      "expo-secure-store",
      "./plugins/reveil-vocal",
    ],
    extra: {
      ...(projetEas ? { eas: { projectId: projetEas } } : {}),
      supabaseUrl: process.env.SUPABASE_URL ?? "",
      supabaseAnonKey: process.env.SUPABASE_ANON_KEY ?? "",
      // Compte de service dedie (pas le compte personnel de l'operateur) :
      // l'appli s'authentifie seule, sans jamais montrer d'ecran de
      // connexion -- decision explicite du 15 sept., cette application
      // est privee et n'a ni inscription ni connexion visible. Un compte
      // dedie plutot que le sien limite les degats si l'APK fuite un jour
      // (voir supabase/migrations/20260915220000_alluxe_bot_prive.sql
      // pour le is_admin qui protege les vraies donnees).
      serviceEmail: process.env.ALLUXE_BOT_SERVICE_EMAIL ?? "",
      servicePassword: process.env.ALLUXE_BOT_SERVICE_PASSWORD ?? "",
    },
  },
});
