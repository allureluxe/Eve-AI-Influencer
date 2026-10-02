/**
 * Mises a jour OTA appliquees TOUT DE SUITE.
 *
 * 2 oct. 2026 : une mise a jour publiee n'apparaissait pas sur le
 * telephone. Le serveur la servait bien ; c'est le comportement par
 * defaut d'expo-updates qui trompait : elle se telecharge a l'ouverture
 * et ne s'applique qu'a l'ouverture SUIVANTE, apres une fermeture
 * complete de l'application. Ici, des qu'une version plus recente existe,
 * on la telecharge et on relance l'application dessus -- a l'ouverture et
 * a chaque retour au premier plan.
 */
import React from "react";
import { AppState } from "react-native";
import * as Updates from "expo-updates";

let enCours = false;

export async function appliquerMiseAJour(): Promise<void> {
  if (__DEV__ || !Updates.isEnabled || enCours) return;
  enCours = true;
  try {
    const verif = await Updates.checkForUpdateAsync();
    if (!verif.isAvailable) return;
    const recue = await Updates.fetchUpdateAsync();
    if (recue.isNew) await Updates.reloadAsync();
  } catch {
    // Pas de reseau ou serveur indisponible : on reessaiera au prochain retour.
  } finally {
    enCours = false;
  }
}

export function useMiseAJourAuto(): void {
  React.useEffect(() => {
    appliquerMiseAJour();
    const abonnement = AppState.addEventListener("change", (etat) => {
      if (etat === "active") appliquerMiseAJour();
    });
    return () => abonnement.remove();
  }, []);
}

/** Version qui tourne, pour la lire a l'ecran : « integree » ou l'id OTA. */
export function versionAffichee(): string {
  if (!Updates.isEnabled) return "dev";
  if (Updates.isEmbeddedLaunch || !Updates.updateId) return "version integree";
  return `maj ${Updates.updateId.slice(0, 8)}`;
}
