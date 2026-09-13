// Remplace app.json (Expo lui donne priorite des qu'il existe).
//
// POURQUOI CE FICHIER EXISTE. app.json ecrivait "@SUPABASE_URL" dans
// `extra` : cette syntaxe n'est resolue QUE par les Environment
// Variables du tableau de bord EAS, pendant un `eas build` dans le
// cloud. En dev local (`expo start`), personne ne la remplace — Expo
// Go recevait donc la chaine "@SUPABASE_URL" telle quelle et
// `createClient()` echouait des le demarrage.
//
// Ce fichier lit directement `process.env`, rempli ici par
// `app-signaux/.env` (dotenv) en local, et plus tard par les memes
// noms de variables definis dans le tableau de bord EAS pour les
// builds cloud — meme mecanisme, une seule source de verite.
require("dotenv").config();

module.exports = () => ({
  expo: {
    name: "Allure",
    slug: "allure-trading",
    version: "1.0.0",
    orientation: "portrait",
    scheme: "allure",
    userInterfaceStyle: "automatic",
    icon: "./assets/icone.png",
    splash: {
      image: "./assets/lancement.png",
      resizeMode: "contain",
      backgroundColor: "#FFFFFF",
    },
    android: {
      package: "fr.allure.trading",
      versionCode: 1,
      googleServicesFile: "./google-services.json",
      adaptiveIcon: {
        foregroundImage: "./assets/icone-adaptative.png",
        backgroundColor: "#EFE73C",
      },
      permissions: ["POST_NOTIFICATIONS"],
    },
    plugins: ["expo-font", "expo-notifications"],
    extra: {
      supabaseUrl: process.env.SUPABASE_URL ?? "",
      supabaseAnonKey: process.env.SUPABASE_ANON_KEY ?? "",
      revenueCatAndroidKey: process.env.REVENUECAT_ANDROID_KEY ?? "",
      bitvavoParrainage: process.env.BITVAVO_PARRAINAGE ?? "",
      eas: {
        projectId: process.env.EAS_PROJECT_ID ?? "",
      },
    },
  },
});
