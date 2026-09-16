// Meme mecanisme que app-signaux/app.config.js : lit process.env
// directement (dotenv en local, variables d'environnement du workflow
// GitHub Actions pour le build cloud) -- voir ce fichier-la pour le
// pourquoi complet.
require("dotenv").config();

module.exports = () => ({
  expo: {
    name: "Alluxe Bot",
    slug: "alluxe-bot",
    version: "1.0.0",
    orientation: "portrait",
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
      versionCode: 1,
      googleServicesFile: "./google-services.json",
      adaptiveIcon: {
        foregroundImage: "./assets/icone-adaptative.png",
        backgroundColor: "#FFFFFF",
      },
      permissions: ["POST_NOTIFICATIONS"],
    },
    plugins: [
      "expo-font",
      "expo-notifications",
      "expo-speech-recognition",
      "./plugins/reveil-vocal",
    ],
    extra: {
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
