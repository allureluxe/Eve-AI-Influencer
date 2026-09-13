/**
 * Remplit la file de notifications. Appele toutes les 5 minutes.
 *
 * Ne parle a personne : il regarde ce qui est nouveau en base et cree
 * les lignes a envoyer, avec leur heure. Tout le calcul de « qui » et
 * « quand » est ici ; l'envoi lui-meme est un autre metier.
 *
 * LE TON DES MESSAGES est verrouille par `redaction.ts` et teste :
 * jamais de point d'exclamation, jamais d'emoji, jamais de promesse de
 * gain. Ce n'est pas une preference de style — une notification est ce
 * que l'utilisateur voit le plus souvent de l'application, et c'est ce
 * qui la fait passer pour un outil serieux ou pour une arnaque.
 */

import { clientService, reponse } from "../_partage/commun.ts";
import { texteCloture, texteMacro, texteSignal } from "../_partage/redaction.ts";

/** Combien de temps avant l'annonce on previent. */
const PREAVIS_MACRO_MIN = 15;

interface Destinataire {
  id: string;
  tier: string;
  timezone: string;
  notif_nuit: boolean;
  notif_signals: boolean;
  notif_macro: boolean;
  /** Le retard du palier, lu dans `offres`. Zero = temps reel. */
  retard_minutes: number;
}

Deno.serve(async (requete) => {
  // Fonction interne, appelee par le planificateur : elle se protege
  // par un secret partage, pas par un compte utilisateur.
  const secret = requete.headers.get("x-eve-cron") ?? "";
  if (secret !== Deno.env.get("EVE_CRON_SECRET")) {
    return reponse({ error: "non autorise" }, 401);
  }

  const service = clientService();
  const maintenant = Date.now();
  let crees = 0;

  // Le retard vient de la GRILLE, pas du nom du palier. Sans cette
  // jointure, un abonne « essentiel » recevrait sa notification deux
  // heures apres avoir vu le signal dans l'application — il paie le
  // temps reel et l'alerte arrive en retard.
  const { data: profils } = await service
    .from("profiles")
    .select(`id, tier, timezone, notif_nuit, notif_signals, notif_macro,
             offres!inner (retard_minutes)`)
    .not("push_token", "is", null);

  const destinataires = ((profils ?? []) as Array<Record<string, any>>)
    .map((p) => ({
      id: p.id, tier: p.tier, timezone: p.timezone,
      notif_nuit: p.notif_nuit, notif_signals: p.notif_signals,
      notif_macro: p.notif_macro,
      retard_minutes: p.offres?.retard_minutes ?? 120,
    })) as Destinataire[];

  /** Ajoute une ligne dans la file, sauf si elle y est deja. */
  async function empiler(
    qui: Destinataire, kind: string, refId: string,
    titre: string, corps: string, quand: Date,
  ) {
    // L'heure autorisee est calculee EN BASE : c'est la seule qui
    // connaisse vraiment les fuseaux et les changements d'heure.
    const { data: heure } = await service.rpc("heure_denvoi_autorisee", {
      souhaitee: quand.toISOString(),
      fuseau: qui.timezone,
      // Seul un palier en temps reel peut recevoir la nuit, et
      // seulement s'il l'a explicitement accepte : reveiller quelqu'un
      // pour un signal vieux de deux heures n'a aucun sens.
      nuit_permise: qui.notif_nuit && qui.retard_minutes === 0 &&
                    kind === "signal_nouveau",
    });

    const { error } = await service.from("notifications").insert({
      user_id: qui.id, kind, ref_id: refId,
      title: titre, body: corps,
      a_envoyer_a: heure ?? quand.toISOString(),
    });
    // 23505 = doublon. C'est le fonctionnement normal : la contrainte
    // unique est ce qui garantit qu'on n'envoie jamais deux fois.
    if (!error) crees += 1;
    else if (error.code !== "23505") console.error("empiler :", error);
  }

  // ---------------------------------------------------- 1. signaux
  //
  // On regarde 24 h en arriere, pas seulement les 5 dernieres minutes :
  // le palier gratuit doit etre servi DEUX HEURES apres la publication,
  // donc son tour vient bien apres. La contrainte unique fait le tri.
  const { data: signaux } = await service
    .from("signals")
    .select("id, pair, side, entry_price, published_at")
    .not("published_at", "is", null)
    .gte("published_at", new Date(maintenant - 86_400_000).toISOString());

  for (const s of signaux ?? []) {
    const publie = Date.parse(s.published_at);
    const { titre, corps } = texteSignal(s.pair, s.side, s.entry_price);
    for (const qui of destinataires) {
      if (!qui.notif_signals) continue;
      const quand = new Date(publie + qui.retard_minutes * 60_000);
      await empiler(qui, "signal_nouveau", s.id, titre, corps, quand);
    }
  }

  // ------------------------------------------- 2. annonces macro
  const debut = new Date(maintenant + (PREAVIS_MACRO_MIN - 5) * 60_000);
  const fin = new Date(maintenant + (PREAVIS_MACRO_MIN + 5) * 60_000);
  const { data: evenements } = await service
    .from("economic_events")
    .select("id, name_fr, event_time, impact")
    .eq("impact", "high")
    .gte("event_time", debut.toISOString())
    .lte("event_time", fin.toISOString());

  for (const e of evenements ?? []) {
    const { titre, corps } = texteMacro(e.name_fr, PREAVIS_MACRO_MIN);
    for (const qui of destinataires) {
      if (!qui.notif_macro) continue;
      await empiler(qui, "evenement_macro", e.id, titre, corps, new Date());
    }
  }

  // -------------------------- 3. clotures des trades marques pris
  const { data: closSuivis } = await service
    .from("signal_taken")
    .select(`user_id, signal_id,
             signals!inner (id, pair, status, closed_at, result_pct)`)
    .not("signals.closed_at", "is", null)
    .gte("signals.closed_at", new Date(maintenant - 86_400_000).toISOString());

  for (const ligne of (closSuivis ?? []) as Array<Record<string, any>>) {
    const s = ligne.signals;
    const qui = destinataires.find((d) => d.id === ligne.user_id);
    if (!qui) continue;
    const { titre, corps } = texteCloture(s.pair, s.result_pct ?? 0);
    await empiler(qui, "signal_cloture", s.id, titre, corps, new Date());
  }

  return reponse({ crees, destinataires: destinataires.length });
});
