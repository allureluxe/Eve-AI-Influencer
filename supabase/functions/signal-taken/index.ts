/**
 * POST /signal-taken — l'utilisateur declare avoir pris ce trade.
 *
 * Sert a deux choses : lui notifier la cloture, et rien d'autre. Ce
 * n'est PAS une execution d'ordre — Eve ne touche jamais a son argent.
 */

import { erreur, filtrerPourLePalier, reponse, servir, Signal } from "../_partage/commun.ts";

Deno.serve((requete) =>
  servir(requete, "signal-taken", async (visiteur, service, req) => {
    if (req.method !== "POST") return erreur("POST attendu", 405);

    let corps: { signal_id?: string };
    try {
      corps = await req.json();
    } catch {
      return erreur("corps JSON attendu", 400);
    }
    const signalId = corps.signal_id;
    if (!signalId) return erreur("signal_id manquant", 400);

    // ON NE MARQUE QUE CE QU'ON A LE DROIT DE VOIR.
    // Sans ce controle, un compte gratuit pourrait deviner l'existence
    // d'un signal payant en essayant des identifiants, et surtout
    // recevoir sa notification de cloture — donc son resultat.
    const { data: signal } = await service
      .from("signals")
      .select("id, pair, published_at")
      .eq("id", signalId)
      .not("published_at", "is", null)
      .maybeSingle();

    if (!signal) return erreur("signal introuvable", 404);
    if (filtrerPourLePalier([signal as unknown as Signal], visiteur.capacites).length === 0) {
      return erreur("signal introuvable", 404);   // meme message : pas d'indice
    }

    const { error } = await service
      .from("signal_taken")
      .upsert({ user_id: visiteur.id, signal_id: signalId },
              { onConflict: "user_id,signal_id" });

    if (error) return erreur("enregistrement impossible", 500);
    return reponse({ ok: true });
  }, 30)
);
