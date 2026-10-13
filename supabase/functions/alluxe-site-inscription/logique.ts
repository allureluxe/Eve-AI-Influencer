/** Validation d'une inscription à la liste d'e-mails d'alluxe.fr. Pure : testable sans réseau. */

export const INTERETS = ["noel", "livres", "offres", "tout"];
export const MAX_PAR_VISITEUR = 5;   // par jour
export const MAX_PAR_JOUR = 300;

export type Inscription = { email: string; interet: string; page: string | null };

const coupe = (v: unknown, n: number) => (typeof v === "string" ? v.trim().slice(0, n) : "");

/** Rend l'inscription propre, « spam », ou un message d'erreur pour le visiteur. */
export function valider(brut: Record<string, unknown>): Inscription | string {
  if (coupe(brut.site_web, 200)) return "spam";            // champ piège invisible
  if (brut.consentement !== true) return "Coche la case pour accepter de recevoir les e-mails.";
  const email = coupe(brut.email, 200).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return "Adresse e-mail invalide.";
  const interet = INTERETS.includes(coupe(brut.interet, 20)) ? coupe(brut.interet, 20) : "tout";
  const page = coupe(brut.page, 120).replace(/[^\w./#-]/g, "") || null;
  return { email, interet, page };
}
