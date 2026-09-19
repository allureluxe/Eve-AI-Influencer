/**
 * La voix d'Alluxe.
 *
 * Demande de l'operateur (19 sept.) : « je veux une autre voix, j'aime
 * pas celle-la, utilise la meme voix que Jarvis ». Jusqu'ici l'appli
 * appelait `Speech.speak(texte, { language: "fr-FR" })` -- aucun reglage,
 * donc la voix par defaut du telephone, souvent feminine et rapide.
 *
 * CE QU'ON PEUT ET CE QU'ON NE PEUT PAS. On ne peut pas installer la
 * vraie voix du film : `expo-speech` lit avec les voix DEJA presentes sur
 * l'appareil (moteur Google sur Android). Ce qu'on peut faire, et qui
 * change tout a l'oreille, c'est CHOISIR parmi elles et regler la
 * hauteur et le debit :
 *
 *   - une voix MASCULINE francaise, choisie explicitement ;
 *   - la meilleure qualite disponible (les voix "network" de Google sont
 *     nettement plus naturelles que les "local") ;
 *   - une hauteur legerement plus GRAVE et un debit un peu plus LENT --
 *     c'est ce qui donne le calme un peu detache du personnage, plus que
 *     le timbre lui-meme.
 *
 * Si rien de tout ca n'existe sur l'appareil, on retombe sur la voix par
 * defaut : Alluxe parle quand meme.
 */
import * as Speech from "expo-speech";

const GRAVITE = 0.85;   // 1 = normal. Plus bas = plus grave.
const DEBIT = 0.94;     // 1 = normal. Un peu plus lent = plus pose.

/** Codes de voix Google connus pour etre masculins en francais. */
const MASCULINES = ["frd", "frb", "frc", "-male", "male"];

let voixChoisie: string | undefined;
let rechercheFaite = false;

async function choisirLaVoix(): Promise<string | undefined> {
  if (rechercheFaite) return voixChoisie;
  rechercheFaite = true;
  try {
    const toutes = await Speech.getAvailableVoicesAsync();
    const francaises = toutes.filter((v) =>
      (v.language || "").toLowerCase().startsWith("fr"));
    if (francaises.length === 0) return undefined;

    const estMasculine = (id: string) =>
      MASCULINES.some((code) => id.toLowerCase().includes(code));
    const estMeilleureQualite = (id: string) =>
      id.toLowerCase().includes("network");

    // Par ordre de preference : masculine ET haute qualite, puis
    // masculine, puis haute qualite, puis n'importe quelle francaise.
    const classee =
      francaises.find((v) => estMasculine(v.identifier) && estMeilleureQualite(v.identifier))
      ?? francaises.find((v) => estMasculine(v.identifier))
      ?? francaises.find((v) => estMeilleureQualite(v.identifier))
      ?? francaises[0];

    voixChoisie = classee?.identifier;
  } catch {
    voixChoisie = undefined;   // pas grave : voix par defaut
  }
  return voixChoisie;
}

/** Fait parler Alluxe. Remplace tout appel direct a Speech.speak. */
export async function parler(texte: string): Promise<void> {
  if (!texte || !texte.trim()) return;
  const voice = await choisirLaVoix();
  Speech.speak(texte, {
    language: "fr-FR",
    pitch: GRAVITE,
    rate: DEBIT,
    ...(voice ? { voice } : {}),
  });
}

export function seTaire(): void {
  Speech.stop();
}

/** Pour un ecran de reglages : ce que l'appareil sait faire. */
export async function voixDisponibles(): Promise<
  { identifier: string; name?: string; language?: string }[]
> {
  try {
    const toutes = await Speech.getAvailableVoicesAsync();
    return toutes
      .filter((v) => (v.language || "").toLowerCase().startsWith("fr"))
      .map((v) => ({ identifier: v.identifier, name: v.name, language: v.language }));
  } catch {
    return [];
  }
}
