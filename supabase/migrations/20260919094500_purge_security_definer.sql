-- ============================================================
--  Les declencheurs de purge tournaient avec les droits de
--  l'appelant -- 19 sept.
--
--  SYMPTOME : "l'agent vocal ne marche toujours pas, ni vocal ni
--  ecrit, il repond pas" (operateur, 19 sept.). En realite l'agent
--  n'a JAMAIS rien recu : la table `alluxe_agent_messages` etait
--  vide (0 ligne), et chaque envoi depuis l'app etait refuse en
--  403 / 42501 "permission denied for table".
--
--  CAUSE : `alluxe_agent_messages_purge` s'execute APRES chaque
--  insertion et fait un DELETE (ne garder que 300 messages). La
--  fonction n'etant PAS `security definer`, ce DELETE s'execute
--  avec les droits de l'appelant -- le role `authenticated`, qui a
--  bien INSERT/SELECT mais volontairement PAS DELETE (un
--  utilisateur ne doit pas pouvoir effacer l'historique). Resultat :
--  l'insertion entiere echouait a cause de sa propre purge.
--
--  Le piege est que le message d'erreur nomme la table et non le
--  declencheur -- il faut lire l'indice ("GRANT DELETE") pour
--  comprendre qu'un INSERT reclamait un droit de suppression.
--
--  CORRECTIF : la purge est une tache de menage, pas une action de
--  l'utilisateur -- elle passe en `security definer` (executee avec
--  les droits du proprietaire de la fonction). Le role
--  `authenticated` garde donc zero droit de suppression : personne
--  ne peut effacer un message a la main, mais la purge automatique
--  fonctionne. `search_path` est fige, regle habituelle pour toute
--  fonction `security definer`.
--
--  `purger_vieilles_alertes` porte exactement le meme defaut. Il ne
--  se voit pas aujourd'hui (seul le robot ecrit dans
--  `alluxe_bot_alertes`, avec la cle service_role qui a tous les
--  droits) mais il casserait de la meme facon le jour ou l'app y
--  ecrirait. Corrige en meme temps.
-- ============================================================

create or replace function public.purger_vieux_messages_agent()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  delete from public.alluxe_agent_messages
  where id in (
    select id from public.alluxe_agent_messages
    order by created_at desc
    offset 300
  );
  return null;
end;
$$;

create or replace function public.purger_vieilles_alertes()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  delete from public.alluxe_bot_alertes
  where id in (
    select id from public.alluxe_bot_alertes
    order by created_at desc
    offset 500
  );
  return null;
end;
$$;
