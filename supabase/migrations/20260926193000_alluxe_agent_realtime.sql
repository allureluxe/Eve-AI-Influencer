-- Alluxe Agent : diffusion temps reel des reponses vers l'application.
-- Le VPS continue d'ecrire dans alluxe_agent_messages ; l'app recoit
-- immediatement les nouveaux messages via Supabase Realtime.

do $$
begin
  alter publication supabase_realtime add table public.alluxe_agent_messages;
exception
  when duplicate_object then null;
end
$$;
