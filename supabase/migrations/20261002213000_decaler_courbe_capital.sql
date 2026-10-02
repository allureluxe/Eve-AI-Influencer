-- La courbe du capital neutralise les virements COTE SERVEUR (2 oct. 2026) :
-- l'application installee ne recevait pas la mise a jour OTA qui le faisait.
-- Chaque virement decale une seule fois les releves anterieurs.
create table if not exists public.alluxe_bot_virements_appliques (
  compte text not null,
  ts timestamptz not null,
  montant numeric not null,
  applique_le timestamptz not null default now(),
  primary key (compte, ts)
);
alter table public.alluxe_bot_virements_appliques enable row level security;

create or replace function public.decaler_courbe_capital(p_compte text, p_ts timestamptz, p_montant numeric)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare n integer;
begin
  insert into alluxe_bot_virements_appliques(compte, ts, montant) values (p_compte, p_ts, p_montant)
  on conflict do nothing;
  if not found then
    return 0;
  end if;
  update alluxe_bot_capital set capital_eur = capital_eur + p_montant
   where compte = p_compte and vu_le < p_ts;
  get diagnostics n = row_count;
  return n;
end;
$$;
revoke all on function public.decaler_courbe_capital(text, timestamptz, numeric) from public, anon, authenticated;
grant execute on function public.decaler_courbe_capital(text, timestamptz, numeric) to service_role;
