/**
 * L'etat des comptes sociaux de Luna -- Instagram, TikTok.
 *
 * LE JETON N'EST JAMAIS ICI. Il vit dans `.env`, sur le serveur, et rien
 * d'autre. Une application mobile est un fichier que n'importe qui peut
 * ouvrir : un jeton qui s'y trouve est un jeton publie.
 *
 * Le serveur (`ops/luna_reseaux.py`) interroge Instagram avec le jeton
 * puis depose un JSON de CHIFFRES dans le seau public `marque`. On le
 * lit comme on lit le logo, par une URL publique.
 *
 * Pourquoi un fichier et pas une table : le jeton d'administration
 * Supabase a expire le 21 septembre, donc aucune migration ne passait.
 * L'ecran ne connait qu'une adresse ; le jour ou ca deviendra une
 * table, il ne changera pas d'une ligne.
 */
const URL_RESEAUX =
  "https://jwksajhtvhwktkbkpits.supabase.co/storage/v1/object/public/marque/reseaux.json";

export interface Reseau {
  connecte: boolean;
  identifiant: string | null;
  type?: string;
  abonnes?: number | null;
  abonnements?: number | null;
  publications?: number | null;
  detail?: string;
}

export interface EtatReseaux {
  vu_le: string;
  instagram: Reseau;
  tiktok: Reseau;
}

export async function etatReseaux(): Promise<EtatReseaux | null> {
  try {
    // `cache: "no-store"` : sans lui, le navigateur embarque sert un
    // fichier vieux de plusieurs heures et l'ecran annonce un nombre
    // d'abonnes perime sans rien signaler.
    const r = await fetch(`${URL_RESEAUX}?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as EtatReseaux;
  } catch {
    return null;
  }
}
