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
      adaptiveIcon: {
        foregroundImage: "./assets/icone-adaptative.png",
        backgroundColor: "#FFFFFF",
      },
    },
    plugins: ["expo-font"],
    extra: {
      supabaseUrl: process.env.SUPABASE_URL ?? "",
      supabaseAnonKey: process.env.SUPABASE_ANON_KEY ?? "",
    },
  },
});
