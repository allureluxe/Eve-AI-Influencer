/**
 * GET /direct — les positions du robot, AVEC LE PRIX DU MOMENT.
 *
 * POURQUOI CE N'EST PAS /signals AVEC UN CHAMP EN PLUS
 * ----------------------------------------------------
 * `/signals` rend ce que le robot a DECIDE : une entree, un stop, une
 * explication. Ces valeurs sont figees et ne changent jamais — c'est
 * meme garanti par un declencheur en base.
 *
 * Le direct rend autre chose : ce que la position VAUT maintenant.
 * C'est une donnee vivante, qui n'est stockee nulle part et ne doit
 * jamais l'etre. Les melanger dans une meme reponse ferait croire que
 * le gain courant fait partie du signal — et un jour quelqu'un
 * l'ecrirait en base « pour aller plus vite », ce qui rendrait
 * l'historique retouchable.
 *
 * Les prix viennent de l'API publique de Bitvavo, sans cle : ce sont
 * les memes cotations que celles sur lesquelles le robot travaille.
 * Aller les chercher chez un autre fournisseur afficherait un gain
 * different de celui que le robot constate.
 */

import { filtrerPourLePalier, reponse, servir, Signal } from "../_partage/commun.ts";

/** Les cotations changent vite ; ce cache evite de marteler Bitvavo. */
const CACHE_MS = 10_000;
let cotations: { a: number; prix: Map<string, number> } | null = null;

async function lirePrix(paires: string[]): Promise<Map<string, number>> {
  if (cotations && Date.now() - cotations.a < CACHE_MS) return cotations.prix;

  const prix = new Map<string, number>();
  try {
    // Un seul appel pour tout le marche : demander paire par paire
    // ferait soixante-dix requetes par visiteur.
    const rep = await fetch("https://api.bitvavo.com/v2/ticker/price");
    if (rep.ok) {
      for (const t of (await rep.json()) as { market: string; price: string }[]) {
        const valeur = Number(t.price);
        if (Number.isFinite(valeur)) prix.set(t.market, valeur);
      }
    }
  } catch (e) {
    console.error("cotations Bitvavo :", e);
  }
  // On ne remplace le cache que si l'appel a rendu quelque chose : une
  // panne momentanee doit servir les derniers prix connus, pas du vide.
  if (prix.size > 0) cotations = { a: Date.now(), prix };
  return cotations?.prix ?? prix;
}

const CHAMPS = `id, published_at, pair, side, entry_price, stop_loss,
  take_profit_1, take_profit_2, risk_reward, position_size_pct,
  conviction, rationale, status, closed_at, result_pct, macro_flag`;

Deno.serve((requete) =>
  servir(requete, "direct", async (visiteur, service) => {
    const { data } = await service
      .from("signals").select(CHAMPS)
      .eq("status", "active")
      .not("published_at", "is", null)
      .order("published_at", { ascending: false });

    const signaux = filtrerPourLePalier((data ?? []) as Signal[], visiteur.capacites);
    const prix = await lirePrix(signaux.map((s) => s.pair));

    const positions = signaux.map((s) => {
      // « BTC/EUR » -> « BTC-EUR », le format de marche Bitvavo.
      const marche = s.pair.replace("/", "-");
      const courant = prix.get(marche) ?? null;

      let variation: number | null = null;
      let distanceStop: number | null = null;
      if (courant !== null && s.entry_price > 0) {
        const sens = s.side === "buy" ? 1 : -1;
        variation = sens * (courant - s.entry_price) / s.entry_price * 100;
        // Combien il reste avant que la protection se declenche.
        // C'est la question que se pose vraiment quelqu'un qui regarde
        // une position ouverte, et personne ne l'affiche.
        distanceStop = Math.abs(courant - s.stop_loss) / courant * 100;
      }

      return {
        ...s,
        prix_courant: courant,
        variation_pct: variation === null ? null : Math.round(variation * 100) / 100,
        distance_stop_pct:
          distanceStop === null ? null : Math.round(distanceStop * 100) / 100,
        // Le stop est-il deja passe au-dessus du prix d'entree ? Si oui,
        // la position ne peut plus rien couter. C'est l'information la
        // plus rassurante qu'on puisse donner, et elle est verifiable.
        a_l_abri: s.side === "buy"
          ? s.stop_loss >= s.entry_price
          : s.stop_loss <= s.entry_price,
      };
    });

    return reponse({
      tier: visiteur.palier,
      positions,
      // L'heure de la cotation, pour que l'application puisse dire
      // « il y a 4 secondes » plutot que de laisser croire au temps reel.
      cotations_a: cotations ? new Date(cotations.a).toISOString() : null,
      cotations_disponibles: prix.size > 0,
    });
  }, 120)     // debit plus large : cet ecran se rafraichit souvent
);
