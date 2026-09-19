/**
 * Le graphique d'une crypto, facon TradingView, avec les niveaux de la
 * position traces dessus.
 *
 * Demande de l'operateur (19 sept.) : « je veux un graphique de la
 * crypto en 1m, 5m, 15m, 30m, 1h, 4h, 1 jour, tu mets le mode
 * TradingView ».
 *
 * Dessine avec `lightweight-charts` -- la bibliotheque publiee par
 * TradingView eux-memes -- alimentee par les bougies de BITVAVO, c'est-
 * a-dire la source exacte sur laquelle le robot decide. Voir
 * `services/bougies.ts` pour pourquoi pas le widget tout fait.
 *
 * Les trois lignes horizontales sont le coeur de l'ecran : elles
 * repondent d'un coup d'oeil a « ou suis-je entre, et qu'est-ce qui me
 * protege maintenant ». Quand le stop suiveur est passe AU-DESSUS du
 * prix d'achat, la position ne peut plus perdre -- c'est visible
 * immediatement, sans lire un chiffre.
 */
import React from "react";
import { View } from "react-native";
import { WebView } from "react-native-webview";
import { Bougie } from "../services/bougies";
import { useCouleurs, useTheme } from "./base";

export interface NiveauTrace {
  prix: number;
  libelle: string;
  couleur: string;
  /** Tirets : pour distinguer une protection d'un prix reellement paye. */
  pointille?: boolean;
}

/**
 * Le document affiche dans la WebView.
 *
 * Tout est injecte a la construction plutot que charge : la WebView n'a
 * aucun acces a l'application, et les bougies sont deja en memoire cote
 * React Native. Une seule ressource vient du reseau, la bibliotheque de
 * dessin.
 */
function documentHtml(
  bougies: Bougie[], niveaux: NiveauTrace[],
  couleurs: { fond: string; texte: string; grille: string;
              hausse: string; baisse: string },
): string {
  return `<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<style>
  html,body{margin:0;padding:0;background:${couleurs.fond};height:100%;overflow:hidden}
  #g{position:absolute;inset:0}
  #vide{position:absolute;inset:0;display:flex;align-items:center;
        justify-content:center;color:${couleurs.texte};opacity:.6;
        font:14px -apple-system,Roboto,sans-serif;text-align:center;padding:0 16px}
</style></head>
<body>
<div id="g"></div>
<div id="vide" hidden>Cotations indisponibles pour cette unité de temps.</div>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
(function () {
  var donnees = ${JSON.stringify(bougies)};
  var niveaux = ${JSON.stringify(niveaux)};
  var vide = document.getElementById('vide');
  // Sans la bibliotheque (reseau coupe) ou sans bougie, on le DIT.
  // Un cadre vide laisserait croire a un marche plat.
  if (!window.LightweightCharts || !donnees.length) { vide.hidden = false; return; }

  var chart = LightweightCharts.createChart(document.getElementById('g'), {
    layout: { background: { color: '${couleurs.fond}' }, textColor: '${couleurs.texte}' },
    grid: { vertLines: { color: '${couleurs.grille}' },
            horzLines: { color: '${couleurs.grille}' } },
    rightPriceScale: { borderColor: '${couleurs.grille}' },
    timeScale: { borderColor: '${couleurs.grille}', timeVisible: true,
                 secondsVisible: false },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    localization: { locale: 'fr-FR' },
    handleScroll: true, handleScale: true,
  });

  var serie = chart.addCandlestickSeries({
    upColor: '${couleurs.hausse}', downColor: '${couleurs.baisse}',
    borderUpColor: '${couleurs.hausse}', borderDownColor: '${couleurs.baisse}',
    wickUpColor: '${couleurs.hausse}', wickDownColor: '${couleurs.baisse}',
    // Assez de decimales pour le PEPE (0,0000035) sans en mettre sur le
    // BTC : une precision unique serait fausse a l'une des deux bouts.
    priceFormat: { type: 'price', precision: ${bougies.length && bougies[bougies.length - 1].close < 1 ? 8 : 2},
                   minMove: ${bougies.length && bougies[bougies.length - 1].close < 1 ? 0.00000001 : 0.01} },
  });
  serie.setData(donnees);

  niveaux.forEach(function (n) {
    serie.createPriceLine({
      price: n.prix, color: n.couleur, lineWidth: 2,
      lineStyle: n.pointille ? LightweightCharts.LineStyle.Dashed
                             : LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true, title: n.libelle,
    });
  });

  chart.timeScale().fitContent();
  window.addEventListener('resize', function () {
    chart.applyOptions({ width: window.innerWidth, height: window.innerHeight });
  });
})();
</script>
</body></html>`;
}

export function Graphique({ bougies, niveaux, hauteur = 300 }: {
  bougies: Bougie[]; niveaux: NiveauTrace[]; hauteur?: number;
}) {
  const c = useCouleurs();
  const theme = useTheme();

  // La WebView ne se recharge QUE si les donnees changent vraiment.
  // Sans cette cle, chaque rendu de l'ecran parent (il y en a un par
  // cotation recue, soit plusieurs par seconde) reconstruirait le
  // document et ferait clignoter le graphique.
  const html = React.useMemo(
    () => documentHtml(bougies, niveaux, {
      fond: c.surface, texte: c.encreDouce, grille: c.filetDoux,
      hausse: c.gain, baisse: c.perte,
    }),
    [bougies, niveaux, theme, c.surface, c.encreDouce, c.filetDoux, c.gain, c.perte],
  );

  return (
    <View style={{ height: hauteur, borderRadius: 16, overflow: "hidden",
                   backgroundColor: c.surface }}>
      <WebView
        originWhitelist={["*"]}
        source={{ html }}
        style={{ backgroundColor: c.surface }}
        scrollEnabled={false}
        // Le graphique se manipule au doigt (zoom, deplacement) : il doit
        // capter le geste avant la page qui le contient, sinon toute
        // tentative de zoom ferait defiler l'ecran.
        nestedScrollEnabled
        javaScriptEnabled
        domStorageEnabled={false}
        setSupportMultipleWindows={false}
      />
    </View>
  );
}
