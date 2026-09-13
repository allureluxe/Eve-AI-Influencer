/**
 * Onglet Cours — les graphiques TradingView.
 *
 * POURQUOI ON N'A PAS DESSINE NOS PROPRES GRAPHIQUES
 * --------------------------------------------------
 * Un graphique de trading correct — bougies, zoom, echelles, indicateurs,
 * temps reel — represente des mois de travail, et le notre serait moins
 * bon que celui que tout le monde connait deja. Reconnaitre l'interface
 * de TradingView rassure plus qu'un graphique maison approximatif.
 *
 * TROIS PRECAUTIONS
 * -----------------
 * 1. LE WIDGET EST GRATUIT ET SANS CLE. Il ne recoit aucune donnee de
 *    l'utilisateur : ni son identifiant, ni son capital, ni ses trades.
 *    On lui passe un nom de marche public, rien d'autre.
 * 2. LA WEBVIEW EST BRIDEE. Pas de navigation vers d'autres domaines :
 *    sans ce garde-fou, un lien dans le widget sortirait l'utilisateur
 *    de l'application vers une page qu'on ne controle pas, dans une
 *    fenetre qui a l'air d'etre encore la notre.
 * 3. LE THEME SUIT CELUI DE L'APPLICATION. Un graphique blanc qui
 *    s'ouvre dans une application sombre, c'est un flash dans les yeux
 *    et l'impression d'un assemblage de bric et de broc.
 */

import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";
import { api, PositionDirecte } from "../services/api";
import { nomCrypto } from "../services/format";
import { espace, palettes, rayon, TRAIT } from "../theme";
import { Carte, EnTete, T, useCouleurs, useTheme } from "../composants/base";

/** Les marches proposes par defaut, quand le robot n'a rien d'ouvert. */
const PAR_DEFAUT = ["BTCEUR", "ETHEUR", "SOLEUR", "XRPEUR", "ADAEUR"];

/**
 * La page du widget, construite ici plutot que chargee d'un serveur.
 *
 * Tout est en dur dans la chaine : aucun appel a nous, rien a
 * maintenir, et le contenu ne peut pas changer sous nos pieds.
 */
function pageWidget(marche: string, sombre: boolean): string {
  const p = palettes[sombre ? "sombre" : "clair"];
  return `<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<style>
  html,body{margin:0;padding:0;height:100%;background:${p.surface};overflow:hidden}
  #g{height:100%}
</style></head><body>
<div id="g"><div class="tradingview-widget-container" style="height:100%">
<div id="tv" style="height:100%"></div></div></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
  new TradingView.widget({
    container_id: "tv",
    symbol: "BITVAVO:${marche}",
    interval: "60",
    timezone: "Europe/Paris",
    theme: "${sombre ? "dark" : "light"}",
    style: "1",
    locale: "fr",
    toolbar_bg: "${p.surface}",
    hide_side_toolbar: true,
    hide_legend: false,
    allow_symbol_change: false,
    save_image: false,
    autosize: true
  });
</script></body></html>`;
}

function Graphique({ marche }: { marche: string }) {
  const c = useCouleurs();
  const sombre = useTheme() === "sombre";
  return (
    <View style={{
      height: 320, borderRadius: rayon.s, overflow: "hidden",
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.filetDoux,
      backgroundColor: c.surface,
    }}>
      <WebView
        source={{ html: pageWidget(marche, sombre) }}
        style={{ backgroundColor: c.surface }}
        javaScriptEnabled
        domStorageEnabled={false}
        // LA WEBVIEW NE SORT PAS. Seule la page qu'on a construite et
        // les scripts de TradingView passent ; tout autre domaine est
        // refuse. Sans cela, un lien du widget emmenerait l'utilisateur
        // ailleurs dans une fenetre qui a l'air d'etre la notre.
        originWhitelist={["about:blank"]}
        onShouldStartLoadWithRequest={(r) =>
          r.url === "about:blank" ||
          r.url.startsWith("https://s3.tradingview.com") ||
          r.url.startsWith("https://s.tradingview.com") ||
          r.url.startsWith("https://www.tradingview-widget.com")}
        // Rien de l'utilisateur ne doit atterrir chez un tiers.
        incognito
        thirdPartyCookiesEnabled={false}
      />
    </View>
  );
}

export function EcranCours() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();

  const [positions, setPositions] = React.useState<PositionDirecte[]>([]);
  const [choisi, setChoisi] = React.useState<string>("BTCEUR");

  // Les marches ou le robot est engage passent en tete : c'est ce que
  // l'utilisateur veut regarder en priorite.
  React.useEffect(() => {
    api.direct().then((r) => {
      const p = r.donnee?.positions ?? [];
      setPositions(p);
      if (p.length > 0) setChoisi(p[0].pair.replace("/", ""));
    });
  }, []);

  const ouverts = positions.map((p) => p.pair.replace("/", ""));
  const marches = [...ouverts, ...PAR_DEFAUT.filter((m) => !ouverts.includes(m))];

  return (
    <ScrollView
      style={{ backgroundColor: c.fond }}
      contentContainerStyle={{
        padding: espace.l, paddingTop: marges.top + espace.m,
        paddingBottom: marges.bottom + espace.xxxl,
      }}
    >
      <EnTete
        titre="Cours"
        sousTitre="Les graphiques en direct, sur les memes marches que le robot."
      />

      {/* Le selecteur : une bande de puces, celles du robot d'abord. */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
                  style={{ marginBottom: espace.l }}>
        {marches.map((m) => {
          const actif = m === choisi;
          const ouvert = ouverts.includes(m);
          return (
            <T
              key={m}
              v="sousTitre"
              couleur={actif ? c.surJaune : c.encre}
              onPress={() => setChoisi(m)}
              style={{
                backgroundColor: actif ? c.jaune : "transparent",
                borderWidth: TRAIT,
                borderColor: actif ? c.jaune : c.filetDoux,
                borderRadius: rayon.s,
                paddingVertical: espace.s,
                paddingHorizontal: espace.m,
                marginRight: espace.s,
                overflow: "hidden",
              }}
            >
              {nomCrypto(m.slice(0, -3) + "/EUR")}{ouvert ? " ·" : ""}
            </T>
          );
        })}
      </ScrollView>

      <Graphique marche={choisi} />

      {ouverts.includes(choisi) ? (
        <Carte style={{ marginTop: espace.l }} accent>
          <T v="sousTitre">Le robot est actuellement engage sur ce marche</T>
          <T v="petit" style={{ marginTop: espace.xs }}>
            Retrouve son prix d'entree et sa protection dans l'onglet Direct.
          </T>
        </Carte>
      ) : (
        <T v="legende" style={{ marginTop: espace.m }}>
          Le point a cote d'un nom indique que le robot y a une position
          ouverte.
        </T>
      )}

      <T v="legende" style={{ marginTop: espace.xxl, textAlign: "center",
                              lineHeight: 17 }}>
        Graphiques fournis par TradingView. Aucune de tes donnees ne leur
        est transmise.{"\n"}
        Allure ne detient aucun fonds et ne passe aucun ordre a ta place.
      </T>
    </ScrollView>
  );
}
