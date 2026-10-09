-- Audit du 9 oct. 2026 (avis de sécurité Supabase).
--
-- 1. Les fonctions-déclencheurs n'ont pas à être appelables par l'API :
--    un déclencheur s'exécute sans vérifier EXECUTE, donc retirer ce droit
--    ne change rien à leur fonctionnement, et les sort de /rest/v1/rpc.
revoke execute on function public.creer_profil_au_signup() from public, anon, authenticated;
revoke execute on function public.purger_vieilles_alertes() from public, anon, authenticated;
revoke execute on function public.purger_vieux_messages_agent() from public, anon, authenticated;
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;

-- 2. verifier_identite : prévue pour les comptes connectés seulement
--    (migration du 15 sept.), mais restée ouverte aux visiteurs anonymes.
revoke execute on function public.verifier_identite(text) from public, anon;
grant execute on function public.verifier_identite(text) to authenticated;

-- 3. search_path figé (avis « function_search_path_mutable »).
alter function public.touch_updated_at() set search_path = public, pg_temp;
alter function public.palier_reserve_au_serveur() set search_path = public, pg_temp;
alter function public.signals_fige_apres_publication() set search_path = public, pg_temp;
alter function public.heure_denvoi_autorisee(timestamp with time zone, text, boolean) set search_path = public, pg_temp;
alter function public.parrainage_non_auto_confirme() set search_path = public, pg_temp;
alter function public.remise_pct(uuid) set search_path = public, pg_temp;

-- NON TOUCHÉ, volontairement :
--   email_pour_pseudo : la connexion par pseudo en dépend (anon). Elle
--     révèle l'e-mail d'un pseudo connu -> à remplacer par une fonction Edge
--     qui fait la connexion elle-même.
--   vue profils_publics (security definer) : l'écran Communauté en dépend.
