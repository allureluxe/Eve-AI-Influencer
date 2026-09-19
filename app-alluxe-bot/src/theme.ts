/**
 * L'identite visuelle ALLURE.
 *
 * MIS A JOUR LE 14 SEPT. : deux decisions ci-dessous ont ete inversees
 * depuis, sur demande explicite de l'operateur -- gardees en l'etat
 * pour la logique du raisonnement, pas parce qu'elles tiennent encore.
 *   - le jaune n'est plus #EFE73C mais #FCFF00 (couleur reelle du logo
 *     dessine par le frere de l'operateur, mesuree dans le fichier
 *     d'origine -- voir `jaune` plus bas) ;
 *   - les rayons ne sont plus nets mais arrondis (voir `rayon`, 13 sept.,
 *     « trop comme un journal, plus moderne »).
 *
 * CE N'EST PAS UNE PALETTE INVENTEE POUR L'OCCASION.
 * Elle est reprise a l'identique des rapports ALLURE deja produits
 * (`rapports/allure_tete.html`) : meme jaune, meme encre, memes filets,
 * memes polices. Une application qui reprend exactement la charte des
 * documents que l'operateur envoie deja est une application qui a l'air
 * d'appartenir a la meme maison — et c'est precisement ce qui distingue
 * un produit officiel d'une application generique.
 *
 * LE JAUNE #EFE73C EST LA SIGNATURE. Il est acide, il ne ressemble a
 * rien d'autre dans la categorie, et surtout : ce n'est pas du vert.
 * Le vert dit « gain » avant meme qu'on ait lu — et promettre un gain
 * est exactement ce que cette application ne fait pas.
 *
 * LES FILETS SONT NOIRS ET EPAIS (2 px). C'est le trait le plus
 * reconnaissable de la charte. La ou les applications du genre posent
 * des ombres douces et des coins tres arrondis pour paraitre amicales,
 * ALLURE trace des traits nets. Ca se lit comme un document imprime,
 * pas comme une notification marketing.
 *
 * Chaque couleur existe dans les deux themes. Une seule qui manque, et
 * l'ecran affiche le texte d'un theme sur le fond de l'autre.
 */

export type Theme = "clair" | "sombre";

interface Palette {
  fond: string;
  surface: string;
  creux: string;
  /** Le filet fort : noir, epais. La signature graphique. */
  filet: string;
  /** Le filet discret, pour separer sans decouper. */
  filetDoux: string;

  encre: string;
  encreDouce: string;
  encrePale: string;

  /** LE JAUNE ALLURE. Accent, selections, elements actifs. */
  jaune: string;
  /**
   * LE MEME JAUNE, POUR LES GRANDES SURFACES.
   *
   * `jaune` vaut #FCFF00, mesure au pixel dans le logo : saturation
   * 100 %, luminosite 98 %, le jaune le plus lumineux qui existe. Sur un
   * embleme entoure d'autre chose, il claque — c'est ce qu'on veut.
   * Etale en aplat (pastille d'onglet, gros bouton, bulle de
   * conversation), et surtout en theme sombre, il eblouit.
   *
   * Retour de l'operateur le 19 sept. : « les couleurs jaunes de
   * l'application sont plus flashy que sur le logo, ca attaque les
   * yeux ». La mesure dit pourtant que les deux couleurs sont
   * IDENTIQUES — ce qui differe est la surface couverte.
   *
   * Regle : `jaune` pour le logo, les traits fins et les petits
   * reperes ; `jauneAplat` des qu'une zone pleine depasse la taille
   * d'une icone. Ne jamais toucher a `jaune` : c'est la marque, et
   * l'operateur a deja demande le 14 sept. qu'elle colle au dessin.
   */
  jauneAplat: string;
  /** Le jaune tres pale, pour un fond d'element mis en avant. */
  jaunePale: string;
  /** L'olive : du texte lisible POSE SUR le jaune. */
  olive: string;
  /** Ce qu'on ecrit sur un aplat jaune. */
  surJaune: string;

  gain: string;
  perte: string;
  vigilance: string;
}

const CLAIR: Palette = {
  fond: "#FFFFFF",
  surface: "#FFFFFF",
  creux: "#F6F6F0",
  filet: "#15150F",
  filetDoux: "#E9E9DE",

  encre: "#15150F",
  encreDouce: "#55554A",
  encrePale: "#8E8E80",

  // Jaune ajuste le 14 sept. sur la couleur reelle du logo dessine par
  // le frere de l'operateur (#FCFF00 mesure dans le fichier d'origine)
  // -- l'ancien #EFE73C, plus doux, ne correspondait pas au vrai
  // dessin : « je veux que les couleurs de l'appli soient avec ces
  // couleurs, ce que je ne vois toujours pas ».
  jaune: "#FCFF00",
  // Un cran de saturation en moins, un cran de profondeur en plus. Assez
  // proche pour rester la meme couleur de marque, assez calme pour
  // couvrir un bouton entier sans fatiguer.
  jauneAplat: "#EDEF3A",
  jaunePale: "#FDFFD0",
  olive: "#5C570C",
  surJaune: "#15150F",

  gain: "#2C6B3F",
  perte: "#A8382A",
  vigilance: "#5C570C",
};

/**
 * Le theme sombre.
 *
 * L'encre devient le fond, et le jaune reste le jaune — il tient sur
 * fond sombre sans rien changer, ce qui est rare et precieux. Le filet
 * fort, lui, ne peut plus etre noir : il passe a une encre claire, en
 * gardant son epaisseur. C'est le trait qui fait la charte, pas sa
 * couleur.
 */
const SOMBRE: Palette = {
  fond: "#15150F",
  surface: "#1D1D16",
  creux: "#26261D",
  // 19 sept. : etait #E9E9DE, un blanc casse. Sur le fond #15150F, ca
  // cernait chaque carte et chaque barre d'un trait clair, dur a l'oeil.
  // Personne ne l'avait vu parce que ce theme n'avait JAMAIS ete affiche
  // -- il etait code depuis le debut mais debranché (voir
  // FournisseurTheme). Un theme qu'on n'affiche pas ne se relit pas.
  filet: "#3E3E33",
  filetDoux: "#2A2A22",

  encre: "#F2F2E8",
  encreDouce: "#A8A89A",
  encrePale: "#77776B",

  jaune: "#FCFF00",
  // Plus sourd encore que sur fond clair : c'est la nuit, sur un fond
  // presque noir, qu'un aplat de #FCFF00 fait le plus mal aux yeux.
  jauneAplat: "#D6D93A",
  jaunePale: "#2E2C10",
  olive: "#D6CE5A",
  surJaune: "#15150F",

  gain: "#63A87A",
  perte: "#D4715C",
  vigilance: "#D6CE5A",
};

export const palettes = { clair: CLAIR, sombre: SOMBRE };

/**
 * Les polices de la charte ALLURE.
 *
 * Fraunces (serif a caractere) porte les titres — elle donne le ton
 * d'une publication.
 * Archivo tient l'interface : une grotesque etroite et solide, qui
 * tient bien en petit corps.
 * IBM Plex Mono porte TOUS LES CHIFFRES. Les prix s'alignent en
 * colonne, et une colonne alignee est ce qui distingue visuellement un
 * instrument d'un jouet.
 */
export const polices = {
  titre: "Fraunces_600SemiBold",
  titreItalique: "Fraunces_400Regular_Italic",
  interface: "Archivo_400Regular",
  interfaceGras: "Archivo_600SemiBold",
  chiffres: "IBMPlexMono_500Medium",
} as const;

/** L'epaisseur du filet fort. La signature. */
export const TRAIT = 2;

export const taille = {
  titreGrand: 40,
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

/**
 * Rayons modernises (13 sept., retour reel : « trop comme un journal,
 * plus moderne, une app bancaire »). L'ancienne charte voulait des
 * angles nets ; l'operateur a tranche pour des cartes arrondies, dans
 * le genre Revolut/N26/Binance. Decision produit, pas un oubli.
 */
export const rayon = { s: 12, m: 16, l: 22, rond: 999 } as const;

export function couleurResultat(p: Palette, valeur: number | null): string {
  if (valeur === null || valeur === 0) return p.encreDouce;
  return valeur > 0 ? p.gain : p.perte;
}
