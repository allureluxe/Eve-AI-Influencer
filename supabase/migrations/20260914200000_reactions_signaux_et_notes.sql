-- =====================================================================
--  REACTIONS ET COMMENTAIRES SUR LE CONTENU DU ROBOT
-- =====================================================================
--
-- Demande de l'operateur (14 sept.) : « il faut rajouter sur chaque
-- position, ou analyse et signaux, la possibilite aux utilisateurs de
-- laisser un commentaire, un j'aime ou un negatif ».
--
-- DEUX TABLES DE REACTIONS, PAS UNE SEULE POLYMORPHE. `signals` et
-- `market_notes` sont deja deux tables distinctes dans ce depot (voir
-- `20260912120100_signals.sql` et `20260912120200_agenda_et_analyse.sql`) ;
-- leur donner chacune leurs propres tables de reactions/commentaires,
-- comme `posts` a les siennes, suit la meme discipline plutot que
-- d'inventer une colonne "type de cible" qu'aucune contrainte de cle
-- etrangere ne peut plus verifier.
--
-- J'AIME / PAS J'AIME, PAS UN SIMPLE BOOLEEN. Contrairement a
-- `post_likes` (aimer ou rien), l'operateur demande explicitement les
-- deux sens -- une reaction existe ou non, et si elle existe, son
-- `type` dit lequel.

create type public.type_reaction as enum ('jaime', 'pas_jaime');

-- ---------------------------------------------------------------------
--  SUR LES SIGNAUX (couvre Direct -- positions ouvertes -- et Signaux
--  -- l'historique -- puisque les deux affichent des lignes de la meme
--  table `signals`)
-- ---------------------------------------------------------------------

create table public.signal_reactions (
  signal_id  uuid not null references public.signals (id) on delete cascade,
  user_id    uuid not null references auth.users (id)     on delete cascade,
  type       public.type_reaction not null,
  created_at timestamptz not null default now(),

  -- Une seule reaction par personne et par signal : changer d'avis
  -- remplace la ligne, ca n'en ajoute pas une deuxieme.
  primary key (signal_id, user_id)
);

comment on table public.signal_reactions is
  'J''aime / pas j''aime sur un signal, un par personne et par signal.';

create index signal_reactions_par_signal_idx on public.signal_reactions (signal_id, type);

create table public.signal_comments (
  id         uuid primary key default gen_random_uuid(),
  signal_id  uuid not null references public.signals (id) on delete cascade,
  auteur     uuid not null references auth.users (id)     on delete cascade,
  created_at timestamptz not null default now(),
  texte      text not null check (char_length(texte) between 1 and 500)
);

comment on table public.signal_comments is 'Commentaires sur un signal, par ordre chronologique.';

create index signal_comments_par_signal_idx on public.signal_comments (signal_id, created_at);

-- ---------------------------------------------------------------------
--  SUR LE POINT DU MATIN (market_notes, onglet Analyse)
-- ---------------------------------------------------------------------

create table public.note_reactions (
  note_id    uuid not null references public.market_notes (id) on delete cascade,
  user_id    uuid not null references auth.users (id)          on delete cascade,
  type       public.type_reaction not null,
  created_at timestamptz not null default now(),
  primary key (note_id, user_id)
);

comment on table public.note_reactions is
  'J''aime / pas j''aime sur le point du matin, un par personne et par note.';

create index note_reactions_par_note_idx on public.note_reactions (note_id, type);

create table public.note_comments (
  id         uuid primary key default gen_random_uuid(),
  note_id    uuid not null references public.market_notes (id) on delete cascade,
  auteur     uuid not null references auth.users (id)          on delete cascade,
  created_at timestamptz not null default now(),
  texte      text not null check (char_length(texte) between 1 and 500)
);

comment on table public.note_comments is 'Commentaires sur le point du matin.';

create index note_comments_par_note_idx on public.note_comments (note_id, created_at);


-- =====================================================================
--  ROW LEVEL SECURITY -- meme discipline que posts/post_likes/post_comments
-- =====================================================================

alter table public.signal_reactions enable row level security;
alter table public.signal_comments  enable row level security;
alter table public.note_reactions   enable row level security;
alter table public.note_comments    enable row level security;

alter table public.signal_reactions force row level security;
alter table public.signal_comments  force row level security;
alter table public.note_reactions   force row level security;
alter table public.note_comments    force row level security;

-- Reactions et commentaires se lisent des qu'on est connecte -- comme les
-- signaux et les notes eux-memes -- et chacun ne pose/efface que les siens.

create policy "reactions signal : lecture connectee"
  on public.signal_reactions for select to authenticated using (true);
create policy "reactions signal : poser la sienne"
  on public.signal_reactions for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy "reactions signal : changer la sienne"
  on public.signal_reactions for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "reactions signal : retirer la sienne"
  on public.signal_reactions for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy "commentaires signal : lecture connectee"
  on public.signal_comments for select to authenticated using (true);
create policy "commentaires signal : ecrire le sien"
  on public.signal_comments for insert to authenticated
  with check ((select auth.uid()) = auteur);
create policy "commentaires signal : supprimer le sien"
  on public.signal_comments for delete to authenticated
  using ((select auth.uid()) = auteur);

create policy "reactions note : lecture connectee"
  on public.note_reactions for select to authenticated using (true);
create policy "reactions note : poser la sienne"
  on public.note_reactions for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy "reactions note : changer la sienne"
  on public.note_reactions for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "reactions note : retirer la sienne"
  on public.note_reactions for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy "commentaires note : lecture connectee"
  on public.note_comments for select to authenticated using (true);
create policy "commentaires note : ecrire le sien"
  on public.note_comments for insert to authenticated
  with check ((select auth.uid()) = auteur);
create policy "commentaires note : supprimer le sien"
  on public.note_comments for delete to authenticated
  using ((select auth.uid()) = auteur);

revoke all on public.signal_reactions, public.signal_comments,
              public.note_reactions, public.note_comments
  from anon, authenticated;

grant select, insert, update, delete on public.signal_reactions to authenticated;
grant select, insert, delete         on public.signal_comments  to authenticated;
grant select, insert, update, delete on public.note_reactions   to authenticated;
grant select, insert, delete         on public.note_comments    to authenticated;


-- =====================================================================
--  VUES AGREGEES -- meme raison que posts_public : ne jamais compter
--  cote client
-- =====================================================================

create view public.signals_avec_reactions
with (security_invoker = true)
as
select
  s.id,
  (select count(*) from public.signal_reactions r
    where r.signal_id = s.id and r.type = 'jaime')     as jaime_count,
  (select count(*) from public.signal_reactions r
    where r.signal_id = s.id and r.type = 'pas_jaime')  as pas_jaime_count,
  (select count(*) from public.signal_comments cm
    where cm.signal_id = s.id)                          as comments_count,
  (select r.type from public.signal_reactions r
    where r.signal_id = s.id and r.user_id = (select auth.uid()))
                                                          as ma_reaction
from public.signals s;

comment on view public.signals_avec_reactions is
  'Compteurs de reactions/commentaires par signal, plus la reaction de '
  'l''utilisateur courant. A joindre a `signals` cote application.';

grant select on public.signals_avec_reactions to authenticated;

create view public.notes_avec_reactions
with (security_invoker = true)
as
select
  n.id,
  (select count(*) from public.note_reactions r
    where r.note_id = n.id and r.type = 'jaime')     as jaime_count,
  (select count(*) from public.note_reactions r
    where r.note_id = n.id and r.type = 'pas_jaime')  as pas_jaime_count,
  (select count(*) from public.note_comments cm
    where cm.note_id = n.id)                          as comments_count,
  (select r.type from public.note_reactions r
    where r.note_id = n.id and r.user_id = (select auth.uid()))
                                                        as ma_reaction
from public.market_notes n;

comment on view public.notes_avec_reactions is
  'Compteurs de reactions/commentaires par note du matin, plus la '
  'reaction de l''utilisateur courant.';

grant select on public.notes_avec_reactions to authenticated;
