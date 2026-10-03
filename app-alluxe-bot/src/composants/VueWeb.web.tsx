/**
 * Navigateur : react-native-webview n'existe pas sur le web. Les ecrans
 * ne lui passent que du HTML construit par l'appli (`source.html`) :
 * une iframe `srcDoc` affiche la meme page. Les reglages propres a la
 * WebView native (zoom, fenetres, filtrage de navigation) sont ignores ;
 * le bac a sable (scripts seuls, origine opaque) empeche la page de lire
 * la session de l'appli ou d'ouvrir d'autres fenetres.
 */
import React from "react";
import { View } from "react-native";

export function VueWeb({ source, style }: { source: { html: string }; style?: any; [k: string]: any }) {
  return (
    <View style={[{ flex: 1 }, style]}>
      {React.createElement("iframe", {
        srcDoc: source.html,
        sandbox: "allow-scripts",
        style: { border: 0, width: "100%", height: "100%", background: "transparent" },
      })}
    </View>
  );
}
