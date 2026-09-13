-- ============================================================
--  Le lien robot <-> application, et l'interdiction de reecrire
-- ============================================================
--
--  Deux manques du schema initial, decouverts en branchant le robot.
--
--  1. Rien ne reliait une ligne `signals` a la position du robot. Sans
--     ce lien, la cloture ne sait pas quelle ligne fermer, et un
--     redemarrage republie les memes signaux en double.
--
--  2. La promesse « un signal publie n'est jamais modifie » n'etait
--     ecrite nulle part. Une promesse tenue uniquement par le code qui
--     ecrit n'est pas une promesse : c'est une intention. Ici c'est la
--     base qui refuse.

-- ---------------------------------------------------------- reference
alter table public.signals
  add column reference text;

comment on column public.signals.reference is
  'Identifiant de la position cote robot. Jamais expose a l''application ; '
  'sert a retrouver la ligne au moment de la cloture.';

-- Unique, mais seulement quand elle existe : les signaux saisis a la
-- main (demonstration, rattrapage) n'en portent pas.
create unique index signals_reference_idx
  on public.signals (reference)
  where reference is not null;

-- ------------------------------------------------------- immuabilite
--
--  CE QUI PEUT CHANGER APRES PUBLICATION, ET RIEN D'AUTRE :
--    status, closed_at, result_pct, updated_at
--
--  Tout le reste — le prix d'entree, le stop, l'objectif, l'explication,
--  la conviction — est fige des que `published_at` est pose.
--
--  Pourquoi c'est le point le plus important du schema : un historique
--  qu'on peut retoucher ne vaut rien. Si le prix d'entree d'un signal
--  perdant peut etre corrige apres coup, la courbe de performance
--  affichee dans l'application est une fiction, et l'abonnement qu'elle
--  justifie est une escroquerie. La contrainte vaut donc pour
--  service_role aussi : elle ne protege pas contre un attaquant, elle
--  protege contre nous-memes.
--
--  Un signal encore en brouillon (published_at nul) reste librement
--  modifiable — c'est justement a ca que sert le brouillon.

create or replace function public.signals_fige_apres_publication()
returns trigger
language plpgsql
as $$
begin
  if old.published_at is null then
    return new;                      -- brouillon : tout est permis
  end if;

  if new.published_at is distinct from old.published_at then
    raise exception
      'signal deja publie le % : la date de publication ne se change pas',
      old.published_at;
  end if;

  if (new.pair,  new.side,  new.entry_price, new.stop_loss,
      new.take_profit_1,   new.take_profit_2, new.risk_reward,
      new.position_size_pct, new.conviction,  new.rationale,
      new.macro_flag,      new.reference)
     is distinct from
     (old.pair,  old.side,  old.entry_price, old.stop_loss,
      old.take_profit_1,   old.take_profit_2, old.risk_reward,
      old.position_size_pct, old.conviction,  old.rationale,
      old.macro_flag,      old.reference)
  then
    raise exception
      'signal % deja publie : seuls status, closed_at et result_pct '
      'peuvent encore changer', old.id;
  end if;

  -- Une cloture ne se rouvre pas et ne se rejoue pas.
  if old.status <> 'active' and new.status is distinct from old.status then
    raise exception
      'signal % deja cloture en % : le statut est definitif',
      old.id, old.status;
  end if;

  return new;
end;
$$;

comment on function public.signals_fige_apres_publication() is
  'Un signal publie ne change plus, sauf sa cloture. Voir la migration '
  '20260913090000 pour le raisonnement.';

create trigger signals_immuables
  before update on public.signals
  for each row execute function public.signals_fige_apres_publication();
