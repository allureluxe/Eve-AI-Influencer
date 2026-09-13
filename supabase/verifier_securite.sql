-- ============================================================
--  Audit de securite. A lancer AVANT chaque mise en production.
-- ============================================================
--
--    psql "$SUPABASE_DB_URL" -f supabase/verifier_securite.sql
--
--  Chaque requete rend les lignes A CORRIGER. Une sortie vide veut
--  dire que le controle passe.
--
--  Pourquoi un script et pas une relecture : la RLS se verifie table
--  par table, et une table ajoutee six mois plus tard sans politique
--  ne declenche aucune erreur. Elle est simplement lisible par tout le
--  monde, en silence, jusqu'a ce que quelqu'un s'en apercoive.

\echo ''
\echo '=== 1. Une table publique sans RLS activee ==================='
\echo '    Sans RLS, la cle anonyme — qui est dans l APK et que'
\echo '    n importe qui peut extraire — lit la table entiere.'
select tablename as table_sans_rls
  from pg_tables
 where schemaname = 'public'
   and not rowsecurity
 order by tablename;

\echo ''
\echo '=== 2. Une table avec RLS mais AUCUNE politique =============='
\echo '    Cas plus sournois : la RLS est active, donc tout est'
\echo '    refuse. La table est invisible, y compris pour ses'
\echo '    utilisateurs legitimes — et personne ne voit le probleme'
\echo '    tant que l ecran concerne n est pas ouvert.'
select t.tablename as table_sans_politique
  from pg_tables t
 where t.schemaname = 'public'
   and t.rowsecurity
   and not exists (
     select 1 from pg_policies p
      where p.schemaname = 'public' and p.tablename = t.tablename)
 order by t.tablename;

\echo ''
\echo '=== 3. Une politique d ECRITURE ouverte aux utilisateurs ====='
\echo '    signals, economic_events et market_notes ne doivent etre'
\echo '    ecrites QUE par service_role. Une politique d insertion'
\echo '    ouverte a `authenticated` laisserait n importe quel'
\echo '    utilisateur publier son propre signal.'
select tablename, policyname, cmd, roles
  from pg_policies
 where schemaname = 'public'
   and tablename in ('signals', 'economic_events', 'market_notes')
   and cmd in ('INSERT', 'UPDATE', 'DELETE', 'ALL')
   and (roles::text like '%authenticated%' or roles::text like '%anon%')
 order by tablename;

\echo ''
\echo '=== 4. Le palier d abonnement est-il protege ? ==============='
\echo '    profiles.tier decide de ce que l utilisateur voit. S il'
\echo '    peut l ecrire lui-meme, l abonnement ne vaut rien. Le'
\echo '    verrou doit etre un DECLENCHEUR, pas une politique — une'
\echo '    politique UPDATE ne sait pas distinguer les colonnes.'
select tgname as declencheur_sur_profiles
  from pg_trigger
 where tgrelid = 'public.profiles'::regclass
   and not tgisinternal;

\echo ''
\echo '=== 5. L immuabilite des signaux est-elle armee ? ============'
\echo '    Sans ce declencheur, un signal publie peut etre reecrit,'
\echo '    et la courbe de performance affichee dans l application'
\echo '    n a aucune valeur.'
select tgname as declencheur_sur_signals
  from pg_trigger
 where tgrelid = 'public.signals'::regclass
   and not tgisinternal
   and tgname = 'signals_immuables';

\echo ''
\echo '=== 6. Une fonction SECURITY DEFINER sans search_path ========'
\echo '    Une fonction definer sans search_path fige peut etre'
\echo '    detournee : l appelant place une table de meme nom dans'
\echo '    son propre schema, et la fonction l utilise avec les'
\echo '    droits du proprietaire.'
select p.proname as fonction_definer_a_risque
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public'
   and p.prosecdef
   and coalesce(array_to_string(p.proconfig, ','), '') not like '%search_path%'
 order by p.proname;

\echo ''
\echo '=== 7. Recapitulatif des politiques en place ================='
select tablename, policyname, cmd, roles::text
  from pg_policies
 where schemaname = 'public'
 order by tablename, cmd, policyname;

\echo ''
\echo '=== Fin. Les sections 1 a 6 doivent etre VIDES, sauf 4 et 5 ==='
\echo '    qui doivent au contraire nommer un declencheur.'
