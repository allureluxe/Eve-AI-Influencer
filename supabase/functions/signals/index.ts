/**
 * GET /signals — les signaux en cours et les 50 derniers clotures.
 *
 * Un compte gratuit ne recoit que BTC, ETH et SOL, et seulement deux
 * heures apres publication. Ce filtrage est applique ICI, sur des
 * lignes deja chargees mais jamais envoyees — l'application ne peut
 * pas le contourner.
 */

import { filtrerPourLePalier, reponse, servir, Signal } from "../_partage/commun.ts";

const CHAMPS = `id, published_at, pair, side, entry_price, stop_loss,
  take_profit_1, take_profit_2, risk_reward, position_size_pct,
  conviction, rationale, status, closed_at, result_pct, macro_flag`;

Deno.serve((requete) =>
  servir(requete, "signals", async (visiteur, service) => {
    // `published_at not null` ecarte les brouillons. C'est la meme
    // condition que la politique RLS ; on la repete ici parce que le
    // client de service ne passe pas par la RLS.
    const { data: actifs } = await service
      .from("signals")
      .select(CHAMPS)
      .eq("status", "active")
      .not("published_at", "is", null)
      .order("published_at", { ascending: false });

    // On en demande plus que 50 : le filtrage par palier va en retirer,
    // et un compte gratuit se retrouverait avec trois lignes d'historique
    // si on coupait avant de filtrer.
    const { data: clos } = await service
      .from("signals")
      .select(CHAMPS)
      .neq("status", "active")
      .not("published_at", "is", null)
      .order("closed_at", { ascending: false })
      .limit(300);

    const visibles = filtrerPourLePalier((actifs ?? []) as Signal[],
                                         visiteur.capacites);
    const historique = filtrerPourLePalier((clos ?? []) as Signal[],
                                           visiteur.capacites);
    return reponse({
      tier: visiteur.palier,
      capacites: visiteur.capacites,
      actifs: visibles,
      // L'historique complet est une capacite du palier : sans elle on
      // s'arrete a dix trades, assez pour se faire une idee, pas assez
      // pour reconstituer la strategie.
      clotures: historique.slice(0, visiteur.capacites.historique_complet ? 50 : 10),
      // Sert a l'ecran d'invitation a l'abonnement : « 4 signaux de plus
      // sont disponibles ». On annonce un NOMBRE, jamais leur contenu —
      // annoncer « BTC vient de passer a l'achat, abonne-toi » serait
      // donner le signal tout en pretendant le vendre.
      masques: (actifs ?? []).length - visibles.length,
    });
  })
);
