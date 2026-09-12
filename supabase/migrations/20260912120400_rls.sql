-- =====================================================================
--  ROW LEVEL SECURITY
-- =====================================================================
--
--  CE QU'IL FAUT AVOIR EN TETE AVANT DE LIRE CE FICHIER.
--
--  La cle `anon` est EMBARQUEE DANS L'APPLICATION MOBILE. N'importe qui
--  peut l'extraire d'un APK en dix minutes et interroger la base
--  directement. RLS n'est donc pas une precaution : c'est la seule chose
--  qui separe les donnees d'un utilisateur de celles des autres.
--
--  `service_role`, elle, CONTOURNE RLS par construction. Le robot ecrit
--  avec cette cle depuis le VPS. Il suffit donc de n'ecrire AUCUNE
--  politique d'ecriture pour que seul le robot puisse ecrire — et c'est
--  volontairement ce qu'on fait plus bas. Ne jamais mettre cette cle dans
--  l'application : elle ouvre tout.
--
--  Regle appliquee partout : on ACTIVE RLS sur chaque table, y compris
--  celles dites « publiques ». Une table sans RLS est lisible par tout
--  porteur de la cle anon, sans exception et sans trace.

alter table public.signals         enable row level security;
alter table public.economic_events enable row level security;
alter table public.market_notes    enable row level security;
alter table public.profiles        enable row level security;
alter table public.signal_taken    enable row level security;

-- On force la regle meme pour le proprietaire des tables : sans cela, un
-- script connecte en tant que `postgres` passerait a cote sans le vouloir.
alter table public.profiles     force row level security;
alter table public.signal_taken force row level security;


-- ---------------------------------------------------------------------
--  LECTURE PUBLIQUE (utilisateurs connectes uniquement)
-- ---------------------------------------------------------------------

--  Les BROUILLONS NE SORTENT PAS. `published_at is null` signifie « en
--  preparation » : le filtre est dans la politique et non dans la requete
--  de l'application, parce qu'une requete s'oublie et qu'une politique
--  non. Un signal en cours de calcul ne doit jamais etre suivi.
create policy "signaux publies, lecture connectee"
  on public.signals for select
  to authenticated
  using (published_at is not null);

create policy "agenda, lecture connectee"
  on public.economic_events for select
  to authenticated
  using (true);

create policy "analyses publiees, lecture connectee"
  on public.market_notes for select
  to authenticated
  using (published_at is not null);


-- ---------------------------------------------------------------------
--  DONNEES PERSONNELLES : chacun chez soi
-- ---------------------------------------------------------------------

create policy "profil : lire le sien"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = id);

--  MODIFICATION LIMITEE AUX PREFERENCES.
--
--  La politique garde la ligne chez son proprietaire. Le verrou sur le
--  PALIER, lui, est un declencheur — pas une clause `with check`.
--
--  POURQUOI, ET C'EST UNE ERREUR QUE J'AI FAITE PUIS MESUREE. La version
--  d'abord ecrite comparait le nouveau `tier` a l'ancien par une
--  sous-requete sur `public.profiles`. Une politique qui interroge la
--  table qu'elle protege se rappelle elle-meme :
--
--      ERROR: infinite recursion detected in policy for relation "profiles"
--
--  Le changement de palier etait bien refuse — mais pour la mauvaise
--  raison, et TOUTE modification l'etait aussi, y compris les
--  preferences legitimes. Une protection qui casse la fonctionnalite
--  qu'elle protege n'est pas une protection.
create policy "profil : modifier ses preferences"
  on public.profiles for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

--  LE PALIER NE SE CHANGE QUE PAR service_role.
--
--  Sans ce verrou, un utilisateur passe son propre `tier` a 'plus' depuis
--  l'application : il s'offre l'abonnement. Le declencheur voit l'ancienne
--  ET la nouvelle ligne, ce qu'une politique RLS ne peut pas faire sans
--  se relire elle-meme.
--  DEUX PIEGES ICI, TOUS DEUX TROUVES EN EXECUTANT LE TEST.
--
--  1. PAS DE `security definer`. Il remplace `current_user` par le
--     proprietaire de la fonction pendant l'execution : le controle de
--     role deviendrait toujours vrai, et le verrou toujours ouvert. La
--     fonction n'a besoin d'aucun droit particulier — elle ne fait que
--     refuser.
--
--  2. ON REGARDE `current_user`, PAS `session_user`. Supabase ouvre la
--     connexion avec le role `authenticator` puis bascule par `SET ROLE`
--     vers `authenticated`, `anon` ou `service_role`. `session_user`
--     garde l'ancien, `current_user` suit la bascule — c'est lui qui dit
--     au nom de qui la requete s'execute vraiment.
--
--  La premiere version testait `session_user <> 'postgres'` et laissait
--  passer le changement de palier. Le test l'a montre en une ligne :
--  « palier apres tentative : plus ».
create or replace function public.palier_reserve_au_serveur()
returns trigger
language plpgsql
as $$
begin
  if new.tier is distinct from old.tier
     and current_user in ('authenticated', 'anon') then
    raise exception
      'le palier d''abonnement ne se change pas depuis l''application'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$$;

create trigger profiles_palier_verrouille
  before update on public.profiles
  for each row execute function public.palier_reserve_au_serveur();

--  Pas de politique INSERT : le profil nait avec le compte, par trigger.
--  Pas de politique DELETE : la suppression suit celle du compte.

create policy "trades pris : lire les siens"
  on public.signal_taken for select
  to authenticated
  using ((select auth.uid()) = user_id);

--  On ne peut marquer QUE des signaux publies : marquer un brouillon
--  reviendrait a en deviner l'existence.
create policy "trades pris : marquer un signal"
  on public.signal_taken for insert
  to authenticated
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.signals s
      where s.id = signal_id and s.published_at is not null
    )
  );

create policy "trades pris : se retracter"
  on public.signal_taken for delete
  to authenticated
  using ((select auth.uid()) = user_id);


-- ---------------------------------------------------------------------
--  DROITS DE TABLE
-- ---------------------------------------------------------------------
--
--  RLS filtre les LIGNES ; les droits SQL decident des VERBES. Les deux
--  sont necessaires : une politique de lecture ne sert a rien si le role
--  detient encore `insert` par heritage d'un `grant all` oublie.

revoke all on public.signals, public.economic_events, public.market_notes,
              public.profiles, public.signal_taken
  from anon, authenticated;

grant select on public.signals, public.economic_events, public.market_notes
  to authenticated;
grant select, update          on public.profiles     to authenticated;
grant select, insert, delete  on public.signal_taken to authenticated;

--  `anon` (visiteur non connecte) ne recoit RIEN. L'application doit
--  authentifier avant d'afficher quoi que ce soit — y compris l'agenda.
