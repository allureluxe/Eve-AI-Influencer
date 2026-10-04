-- L'assistant du site public alluxe.fr (fonction alluxe-site-assistant).
--
-- Un seul besoin en base : COMPTER les messages, pour que des visiteurs
-- ne puissent pas vider le quota Groq gratuit partage avec l'agent.
-- Aucune conversation n'est gardee : seulement un compteur par jour,
-- sous une cle hachee (jamais l'adresse IP en clair).

create table if not exists public.alluxe_site_quota (
  cle  text    not null,
  jour date    not null default (now() at time zone 'Europe/Paris')::date,
  n    integer not null default 0,
  primary key (cle, jour)
);

alter table public.alluxe_site_quota enable row level security;
-- Aucune politique : seule la cle de service (la fonction) y touche.

-- Compte UN message pour `p_cle` et pour le total du jour, et dit s'il
-- passe. Atomique : deux messages simultanes ne franchissent pas le
-- plafond ensemble. Le message refuse n'est pas compte.
create or replace function public.alluxe_site_compter(
  p_cle text, p_max_visiteur integer, p_max_jour integer
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_jour date := (now() at time zone 'Europe/Paris')::date;
  v_visiteur integer;
  v_total integer;
begin
  select n into v_visiteur from alluxe_site_quota where cle = p_cle and jour = v_jour for update;
  select n into v_total from alluxe_site_quota where cle = '*total*' and jour = v_jour for update;
  if coalesce(v_visiteur, 0) >= p_max_visiteur or coalesce(v_total, 0) >= p_max_jour then
    return false;
  end if;
  insert into alluxe_site_quota (cle, jour, n) values (p_cle, v_jour, 1)
    on conflict (cle, jour) do update set n = alluxe_site_quota.n + 1;
  insert into alluxe_site_quota (cle, jour, n) values ('*total*', v_jour, 1)
    on conflict (cle, jour) do update set n = alluxe_site_quota.n + 1;
  -- Menage : on ne garde que 7 jours de compteurs.
  delete from alluxe_site_quota where jour < v_jour - 7;
  return true;
end;
$$;

revoke all on function public.alluxe_site_compter(text, integer, integer) from public, anon, authenticated;
grant execute on function public.alluxe_site_compter(text, integer, integer) to service_role;
