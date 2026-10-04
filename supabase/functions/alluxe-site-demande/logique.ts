/** Validation d'une commande passée sur alluxe.fr. Pure : testable sans réseau. */

export const OFFRES = ["vitrine", "shopify", "ecommerce", "agent", "robot", "complet"];
export const FORMULES = ["unique", "mensuel"];
export const MAX_PAR_VISITEUR = 5;   // par jour
export const MAX_PAR_JOUR = 60;

export type Demande = {
  offre: string; formule: string; nom: string; email: string;
  telephone: string | null; activite: string | null; message: string | null;
};

const coupe = (v: unknown, n: number) => (typeof v === "string" ? v.trim().slice(0, n) : "");

/** Rend la demande propre, ou un message d'erreur pour le visiteur. */
export function valider(brut: Record<string, unknown>): Demande | string {
  if (coupe(brut.site_web, 200)) return "spam";            // champ piège invisible
  if (brut.consentement !== true) return "Merci d'accepter d'être recontacté.";
  const offre = coupe(brut.offre, 30), formule = coupe(brut.formule, 20);
  if (!OFFRES.includes(offre)) return "Choisis une offre.";
  if (!FORMULES.includes(formule)) return "Choisis une formule.";
  const nom = coupe(brut.nom, 120), email = coupe(brut.email, 200).toLowerCase();
  if (nom.length < 2) return "Indique ton nom.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return "Adresse e-mail invalide.";
  const telephone = coupe(brut.telephone, 30).replace(/[^\d+ .-]/g, "");
  return { offre, formule, nom, email, telephone: telephone || null,
    activite: coupe(brut.activite, 200) || null, message: coupe(brut.message, 3000) || null };
}
