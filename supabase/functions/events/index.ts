/**
 * GET /events — les annonces economiques des 14 prochains jours.
 *
 * Sans distinction de palier : savoir que l'inflation americaine sort
 * jeudi n'est pas une information qu'on vend. C'est ce que le robot en
 * FAIT qui a de la valeur.
 */

import { reponse, servir } from "../_partage/commun.ts";

Deno.serve((requete) =>
  servir(requete, "events", async (_visiteur, service) => {
    const maintenant = new Date();
    const dans14jours = new Date(maintenant.getTime() + 14 * 86400_000);

    const { data } = await service
      .from("economic_events")
      .select("id, event_time, name_fr, country, impact, eve_policy, actual, forecast, previous")
      .gte("event_time", maintenant.toISOString())
      .lte("event_time", dans14jours.toISOString())
      .order("event_time", { ascending: true });

    return reponse({ evenements: data ?? [] });
  })
);
