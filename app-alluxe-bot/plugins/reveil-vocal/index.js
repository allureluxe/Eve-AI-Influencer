/**
 * Plugin Expo pour le reveil vocal "Alluxe" -- ecoute en arriere-plan
 * (meme app fermee) via Porcupine (Picovoice), ouvre l'application quand
 * le mot est entendu.
 *
 * PREMIERE VERSION (16 sept.). Voir la memoire "reveil-vocal-alluxe" et
 * les commentaires de ServiceReveilVocal.kt pour le detail complet.
 * Volontairement conçu pour ne JAMAIS faire echouer la construction ou
 * planter l'application si la cle Picovoice ou le fichier de mot-cle
 * manquent -- le service se desactive tout seul, en silence, cote natif.
 *
 * Ce qu'il modifie dans le projet Android genere par `expo prebuild` :
 *   - permissions RECORD_AUDIO / FOREGROUND_SERVICE / FOREGROUND_SERVICE_MICROPHONE
 *   - declaration du service ServiceReveilVocal (foregroundServiceType="microphone")
 *   - dependance Gradle vers le SDK Android de Porcupine
 *   - la cle d'acces Picovoice (PICOVOICE_ACCESS_KEY, .env), ecrite dans
 *     res/values/strings.xml -- PAS un secret d'API classique (elle
 *     n'autorise qu'a faire tourner CE mot-cle precis, jamais a lire de
 *     donnees), donc pas traitee comme les autres cles du depot.
 *   - copie du fichier de mot-cle (assets/reveil/alluxe_android.ppn,
 *     genere sur console.picovoice.ai) dans les assets Android, s'il existe
 *   - les 3 fichiers Kotlin de ce dossier, copies dans le paquet natif
 *   - l'enregistrement de ReveilVocalPackage dans MainApplication.kt
 */
const fs = require("fs");
const path = require("path");
const {
  withAndroidManifest,
  withAppBuildGradle,
  withMainApplication,
  withStringsXml,
  withDangerousMod,
  AndroidConfig,
} = require("@expo/config-plugins");

const PACKAGE_ANDROID = "fr.allure.alluxebot";
// Verifie sur search.maven.org (g:ai.picovoice a:porcupine-android) --
// 3.0.3 n'existe pas, une premiere tentative avec ce numero a fait
// echouer la resolution Gradle en CI (16 sept.). Rester sur une version
// confirmee presente avant d'en changer.
const VERSION_PORCUPINE_ANDROID = "3.0.1";
const FICHIER_MOT_CLE = path.join("assets", "reveil", "alluxe_android.ppn");

function withPermissionsReveilVocal(config) {
  return withAndroidManifest(config, (config) => {
    AndroidConfig.Permissions.ensurePermissions(config.modResults, [
      "android.permission.RECORD_AUDIO",
      "android.permission.FOREGROUND_SERVICE",
      "android.permission.FOREGROUND_SERVICE_MICROPHONE",
    ]);

    const application = AndroidConfig.Manifest.getMainApplicationOrThrow(config.modResults);
    application.service = application.service ?? [];
    const dejaPresent = application.service.some(
      (s) => s.$["android:name"] === ".ServiceReveilVocal",
    );
    if (!dejaPresent) {
      application.service.push({
        $: {
          "android:name": ".ServiceReveilVocal",
          "android:exported": "false",
          "android:foregroundServiceType": "microphone",
        },
      });
    }
    return config;
  });
}

function withCleAccesReveilVocal(config) {
  return withStringsXml(config, (config) => {
    config.modResults = AndroidConfig.Strings.setStringItem(
      [
        {
          $: { name: "picovoice_access_key", translatable: "false" },
          _: process.env.PICOVOICE_ACCESS_KEY ?? "",
        },
      ],
      config.modResults,
    );
    return config;
  });
}

function withDependanceGradleReveilVocal(config) {
  return withAppBuildGradle(config, (config) => {
    if (!config.modResults.contents.includes("ai.picovoice:porcupine-android")) {
      config.modResults.contents = config.modResults.contents.replace(
        "dependencies {",
        `dependencies {\n    implementation("ai.picovoice:porcupine-android:${VERSION_PORCUPINE_ANDROID}")`,
      );
    }
    return config;
  });
}

function withFichiersNatifsReveilVocal(config) {
  return withDangerousMod(config, [
    "android",
    async (config) => {
      const racineNatif = path.join(
        config.modRequest.platformProjectRoot,
        "app",
        "src",
        "main",
      );
      const dossierJava = path.join(
        racineNatif,
        "java",
        ...PACKAGE_ANDROID.split("."),
      );
      fs.mkdirSync(dossierJava, { recursive: true });
      for (const nom of [
        "ServiceReveilVocal.kt",
        "ReveilVocalModule.kt",
        "ReveilVocalPackage.kt",
      ]) {
        fs.copyFileSync(
          path.join(__dirname, nom),
          path.join(dossierJava, nom),
        );
      }

      // Le mot-cle est FOURNI PAR L'OPERATEUR (genere sur le site de
      // Picovoice) -- absent au premier passage, et c'est prevu : le
      // build reussit quand meme, le service se desactivera tout seul.
      const cheminSource = path.join(config.modRequest.projectRoot, FICHIER_MOT_CLE);
      if (fs.existsSync(cheminSource)) {
        const dossierAssets = path.join(racineNatif, "assets", "reveil");
        fs.mkdirSync(dossierAssets, { recursive: true });
        fs.copyFileSync(
          cheminSource,
          path.join(dossierAssets, "alluxe_android.ppn"),
        );
      }
      return config;
    },
  ]);
}

function withEnregistrementPackageReveilVocal(config) {
  return withMainApplication(config, (config) => {
    if (!config.modResults.contents.includes("ReveilVocalPackage()")) {
      config.modResults.contents = config.modResults.contents.replace(
        "return PackageList(this).packages",
        "return PackageList(this).packages.apply { add(ReveilVocalPackage()) }",
      );
    }
    return config;
  });
}

module.exports = function withReveilVocal(config) {
  config = withPermissionsReveilVocal(config);
  config = withCleAccesReveilVocal(config);
  config = withDependanceGradleReveilVocal(config);
  config = withFichiersNatifsReveilVocal(config);
  config = withEnregistrementPackageReveilVocal(config);
  return config;
};
