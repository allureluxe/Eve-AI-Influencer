/**
 * L'identite visuelle d'Eve.
 *
 * LE PROBLEME QU'ELLE RESOUT
 * --------------------------
 * Une application de signaux crypto part avec un handicap : elle
 * ressemble, par defaut, a toutes les arnaques du genre. Neon vert et
 * violet, degrades, fusees, chiffres qui clignotent, « +420 % » en gros.
 * Un utilisateur qui a deja vu ca trois fois ferme l'application avant
 * d'avoir lu une ligne — et surtout, il ne la transmet a personne.
 *
 * On prend donc l'exact oppose : un objet de BUREAU D'ANALYSE.
 *
 *   - Encre profonde plutot que noir pur. Le noir pur (#000) est le
 *     reglage par defaut de tout le monde ; une encre bleutee se lit
 *     comme un choix.
 *   - LAITON MAT pour les actions, pas de vert. Le vert dit « gain »
 *     avant meme qu'on ait lu, et promettre un gain est precisement ce
 *     que cette application ne fait pas.
 *   - Hausse et baisse en sauge et terre cuite DESATUREES. Elles
 *     informent, elles ne celebrent ni n'alarment.
 *   - Un serif editorial pour les titres, une sans d'ingenieur pour
 *     l'interface, une mono pour les chiffres. Les prix s'alignent en
 *     colonne : c'est la difference visible entre un outil et un jouet.
 *
 * Chaque couleur existe dans les deux themes. Une seule qui manque et
 * l'ecran affiche du texte d'un theme sur le fond de l'autre.
 */

export type Theme = "clair" | "sombre";

interface Palette {
  /** Le fond de l'ecran. */
  fond: string;
  /** Une surface posee dessus : carte, panneau. */
  surface: string;
  /** Une surface plus enfoncee : champ de saisie, zone inactive. */
  creux: string;
  /** Le filet. Toujours une nuance du fond, jamais du gris pur. */
  filet: string;

  /** Le texte principal. */
  encre: string;
  /** Un texte secondaire, lisible mais en retrait. */
  encreDouce: string;
  /** Une legende, une unite, un horodatage. */
  encrePale: string;

  /** L'accent : boutons, liens, elements actifs. */
  laiton: string;
  /** Le laiton pose sur un fond laiton (texte d'un bouton plein). */
  surLaiton: string;
  /** Un laiton tres pale, pour un fond d'element selectionne. */
  laitonPale: string;

  /** Hausse. Desaturee : elle informe, elle ne celebre pas. */
  hausse: string;
  /** Baisse. Desaturee : elle informe, elle n'alarme pas. */
  baisse: string;
  /** Attention (annonce a fort impact). */
  vigilance: string;
}

const CLAIR: Palette = {
  fond: "#F7F5F1",       // papier chaud, pas blanc pur
  surface: "#FFFFFF",
  creux: "#EEEBE5",
  filet: "#DFDAD1",

  encre: "#1B2027",      // encre bleutee, pas noir
  encreDouce: "#5A6169",
  encrePale: "#8B9199",

  laiton: "#96702B",
  surLaiton: "#FFFFFF",
  laitonPale: "#F2E9D6",

  hausse: "#4A7C59",     // sauge
  baisse: "#A85A47",     // terre cuite
  vigilance: "#8A6D1F",
};

const SOMBRE: Palette = {
  fond: "#14181D",       // encre profonde, pas noir pur
  surface: "#1C2127",
  creux: "#232930",
  filet: "#2E353D",

  encre: "#E9E5DE",
  encreDouce: "#A2A9B1",
  encrePale: "#727A83",

  laiton: "#C9A15C",
  surLaiton: "#14181D",
  laitonPale: "#2A2519",

  hausse: "#7FA88C",
  baisse: "#C98A76",
  vigilance: "#C9A15C",
};

export const palettes = { clair: CLAIR, sombre: SOMBRE };

/**
 * Les polices.
 *
 * Newsreader (serif editorial) porte les titres : elle donne le ton
 * d'une publication, pas d'une notification marketing.
 * IBM Plex Sans tient l'interface — dessinee pour de l'outillage, elle
 * a du caractere sans etre a la mode.
 * IBM Plex Mono porte TOUS LES CHIFFRES : les prix s'alignent en
 * colonne, et une colonne alignee est ce qui distingue visuellement un
 * instrument d'un jouet.
 */
export const polices = {
  titre: "Newsreader_600SemiBold",
  titreItalique: "Newsreader_400Regular_Italic",
  interface: "IBMPlexSans_400Regular",
  interfaceGras: "IBMPlexSans_600SemiBold",
  chiffres: "IBMPlexMono_500Medium",
} as const;

/** Une echelle typographique, pas des tailles au hasard. */
export const taille = {
  titreGrand: 30,
  titre: 22,
  sousTitre: 17,
  corps: 15,
  petit: 13,
  minuscule: 11,
} as const;

/** Un pas de 4, pour que tout s'aligne sans y penser. */
export const espace = {
  xs: 4, s: 8, m: 12, l: 16, xl: 24, xxl: 32, xxxl: 48,
} as const;

export const rayon = { s: 6, m: 10, l: 14, rond: 999 } as const;

/** Le contraste des chiffres selon le sens. */
export function couleurResultat(p: Palette, valeur: number | null): string {
  if (valeur === null || valeur === 0) return p.encreDouce;
  return valeur > 0 ? p.hausse : p.baisse;
}
