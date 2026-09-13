/**
 * Les reglages locaux : ce que l'utilisateur declare sur lui-meme.
 *
 * LE CAPITAL EST DECLARATIF ET RESTE SUR LE TELEPHONE.
 *
 * Il sert uniquement a convertir les pourcentages en euros — « au pire
 * tu perds 2,40 € » plutot que « 0,6 % de risque ». C'est la conversion
 * qui rend l'application comprehensible, et c'est aussi la raison pour
 * laquelle ce chiffre ne doit JAMAIS partir sur un serveur : Eve ne
 * touche pas a l'argent de l'utilisateur, ne connait pas son compte, et
 * n'a aucune raison de savoir combien il a.
 *
 * Conserver cette information la ou elle n'est pas necessaire, c'est
 * creer une fuite potentielle sans contrepartie.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import React from "react";

const CLE_CAPITAL = "eve:capital";
const CLE_ACCUEIL = "eve:accueil-vu";

/** Valeur par defaut tant que l'utilisateur n'a rien declare. */
export const CAPITAL_DEFAUT = 1000;

export function useCapital(): number {
  const [capital, setCapital] = React.useState(CAPITAL_DEFAUT);
  React.useEffect(() => {
    AsyncStorage.getItem(CLE_CAPITAL).then((v) => {
      const n = Number(v);
      if (Number.isFinite(n) && n > 0) setCapital(n);
    }).catch(() => { /* valeur par defaut */ });
  }, []);
  return capital;
}

export async function enregistrerCapital(valeur: number): Promise<void> {
  if (!Number.isFinite(valeur) || valeur <= 0) return;
  await AsyncStorage.setItem(CLE_CAPITAL, String(valeur));
}

export async function accueilDejaVu(): Promise<boolean> {
  return (await AsyncStorage.getItem(CLE_ACCUEIL)) === "1";
}

export async function marquerAccueilVu(): Promise<void> {
  await AsyncStorage.setItem(CLE_ACCUEIL, "1");
}
