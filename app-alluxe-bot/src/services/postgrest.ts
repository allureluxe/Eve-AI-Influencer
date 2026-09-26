/**
 * Ce que PostgREST repond vraiment, et ce que le code croyait.
 *
 * LE DEFAUT, TROUVE TROIS FOIS LE MEME JOUR (26 septembre 2026).
 *
 * Six endroits de l'application prevoyaient le cas d'une table absente
 * — une precaution juste, puisque les migrations sont appliquees a la
 * main. Mais tous testaient le message de POSTGRESQL :
 *
 *     attendu  : "relation ... does not exist"
 *     recu     : "Could not find the table 'public.x' in the schema
 *                 cache"   (code PGRST205)
 *
 * Aucun ne rattrapait donc rien. Consequences observees :
 *
 *   - l'ecran LABORATOIRE levait au chargement (`lab_research`) ;
 *   - l'ecran AGENT ne montrait plus la conversation et n'envoyait
 *     plus rien (`alluxe_agent_status`, `alluxe_agent_events`), alors
 *     que le serveur repondait en UNE SECONDE. Deux tables secondaires
 *     absentes cassaient la fonction principale.
 *
 * UN SEUL ENDROIT POUR CETTE VERIFICATION, desormais. Six copies d'une
 * meme condition, c'est six occasions de n'en corriger que cinq — le
 * piege que le CLAUDE.md de ce depot raconte sept fois.
 *
 * Le code PGRST205 vient en premier : un code est stable, un message
 * se reecrit d'une version a l'autre.
 */
export function tableAbsente(
  error: { message?: string; code?: string } | null | undefined,
): boolean {
  if (!error) return false;
  if (error.code === "PGRST205") return true;
  const m = error.message ?? "";
  return /relation .* does not exist/i.test(m)
    || /could not find the table/i.test(m);
}
