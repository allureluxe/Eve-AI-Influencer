/** Calcul pur, sans dependance : testable sans Supabase. */
export interface PointVirable { vu_le: string; capital_eur: number; }

/** Un depot (+) ou un retrait (-) publie par le serveur. */
export interface Virement { ts: string; montant: number; }

/**
 * LA COURBE NE MONTRE QUE CE QUE LE ROBOT A GAGNE OU PERDU.
 *
 * Demande de l'operateur, 2 oct. 2026 : un retrait faisait une marche
 * d'escalier qui ressemblait a une perte. Chaque point d'AVANT un virement
 * est decale de son montant : la courbe reste continue et se termine sur
 * le capital reel actuel, comme si l'argent avait ete retire des le debut.
 */
export function sansVirements<P extends PointVirable>(points: P[], virements: Virement[]): P[] {
  if (!virements.length) return points;
  const v = virements.map((x) => ({ t: new Date(x.ts).getTime(), m: Number(x.montant) || 0 }));
  return points.map((p) => {
    const t = new Date(p.vu_le).getTime();
    const apres = v.reduce((s, x) => (x.t > t ? s + x.m : s), 0);
    return apres ? { ...p, capital_eur: Number(p.capital_eur) + apres } : p;
  });
}
