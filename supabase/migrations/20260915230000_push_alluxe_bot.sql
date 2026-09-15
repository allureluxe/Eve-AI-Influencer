-- ============================================================
--  Jeton de notification push pour Alluxe Bot.
--
--  Un seul appareil (l'operateur), stocke sur la ligne unique deja
--  utilisee pour les stats privees. Mise a jour par l'application
--  elle-meme a chaque lancement (comme profiles.push_token pour
--  Allure) -- d'ou la policy UPDATE, absente jusqu'ici (la table
--  n'etait lue que par service_role en ecriture).
-- ============================================================

alter table public.alluxe_bot_prive add column if not exists push_token text;

create policy "alluxe bot prive : l'admin met a jour son jeton push"
  on public.alluxe_bot_prive for update
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  )
  with check (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.is_admin
    )
  );

grant update (push_token) on public.alluxe_bot_prive to authenticated;
