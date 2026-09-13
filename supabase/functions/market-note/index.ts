/**
 * GET /market-note — la derniere note PUBLIEE.
 *
 * Les brouillons (`published_at` nul) ne sortent jamais d'ici : une note
 * generee par une machine et non relue n'a rien a faire dans une
 * application financiere.
 */

import { reponse, servir } from "../_partage/commun.ts";

Deno.serve((requete) =>
  servir(requete, "market-note", async (_visiteur, service) => {
    const { data } = await service
      .from("market_notes")
      .select(`id, published_at, headline, body_fr, trend_score,
               volatility_score, fear_greed, btc_dominance`)
      .not("published_at", "is", null)
      .order("published_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    // Pas de note aujourd'hui n'est pas une erreur : le redacteur refuse
    // de publier plutot que d'ecrire n'importe quoi, et l'application
    // doit savoir l'afficher calmement.
    return reponse({ note: data ?? null });
  })
);
