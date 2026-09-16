/**
 * Pont vers le service natif Android ServiceReveilVocal (voir
 * plugins/reveil-vocal/). Rend toujours quelque chose de sur meme si le
 * module natif n'existe pas (par ex. build sans le plugin, ou iOS un
 * jour) -- jamais de plantage, juste "indisponible".
 */
import { NativeModules, Platform } from "react-native";

const { ReveilVocal } = NativeModules as {
  ReveilVocal?: {
    demarrer(): Promise<boolean>;
    arreter(): Promise<boolean>;
    estActif(): Promise<boolean>;
  };
};

export const reveilVocalDisponible = Platform.OS === "android" && !!ReveilVocal;

export async function demarrerReveilVocal(): Promise<void> {
  if (!ReveilVocal) throw new Error("Reveil vocal indisponible sur cet appareil");
  await ReveilVocal.demarrer();
}

export async function arreterReveilVocal(): Promise<void> {
  if (!ReveilVocal) return;
  await ReveilVocal.arreter();
}

export async function reveilVocalActif(): Promise<boolean> {
  if (!ReveilVocal) return false;
  try {
    return await ReveilVocal.estActif();
  } catch {
    return false;
  }
}
