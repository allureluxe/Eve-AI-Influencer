/**
 * GET /performance — la courbe simulee et les statistiques.
 *
 * DEUX EXIGENCES QUI SE CONTREDISENT, ET COMMENT ELLES SONT TRANCHEES
 * -------------------------------------------------------------------
 * La specification de l'API demande « une courbe de capital simulee
 * depuis 10 000 EUR en suivant tous les signaux ». La specification de
 * mise en production interdit « tout chiffre de performance non
 * verifiable ».
 *
 * Les deux tiennent ensemble a trois conditions, appliquees ici :
 *
 * 1. TOUT EST CALCULE DEPUIS LES SIGNAUX REELS DE LA BASE. Aucune
 *    valeur ecrite en dur, aucune donnee de backtest. Si la base est
 *    vide, la reponse est vide.
 *
 * 2. RIEN N'EST RENDU SOUS 30 TRADES CLOTURES. En dessous, une serie
 *    de chance produit une courbe magnifique qui ne prouve rien —
 *    c'est exactement le chiffre invraisemblable que la conformite
 *    interdit. Le champ `fiable` dit franchement ou on en est, et
 *    l'application affiche « pas encore assez d'historique ».
 *
 * 3. LES HYPOTHESES VOYAGENT AVEC LES CHIFFRES. `hypotheses` decrit ce
 *    que la simulation suppose. Une courbe sans ses hypotheses est une
 *    affirmation ; avec elles, c'est un calcul verifiable.
 *
 * Ce que la simulation N'EST PAS : le resultat d'un utilisateur. Elle
 * ne connait ni ses frais, ni son moment d'entree, ni s'il a suivi tous
 * les signaux. L'application doit le dire a l'ecran, pas seulement ici.
 */

import { filtrerPourLePalier, reponse, servir, Signal } from "../_partage/commun.ts";

/** Capital de depart de la simulation. */
const DEPART = 10_000;

/** En dessous, on ne montre pas de courbe. Voir la regle 2 ci-dessus. */
const MINIMUM_TRADES = 30;

/** Part du capital engagee par signal, faute de mieux. */
const PART_PAR_DEFAUT = 0.6;

Deno.serve((requete) =>
  servir(requete, "performance", async (visiteur, service) => {
    const { data } = await service
      .from("signals")
      .select(`id, published_at, pair, side, closed_at, result_pct,
               position_size_pct, entry_price, stop_loss, status`)
      .not("published_at", "is", null)
      .not("closed_at", "is", null)
      .not("result_pct", "is", null)
      .order("closed_at", { ascending: true })
      .limit(2000);

    // La courbe suit ce que l'utilisateur POUVAIT voir : un compte
    // gratuit qui n'a jamais recu les signaux payants ne doit pas se
    // voir promettre leur performance.
    const signaux = filtrerPourLePalier(
      (data ?? []) as unknown as Signal[], visiteur.capacites);

    if (signaux.length < MINIMUM_TRADES) {
      return reponse({
        fiable: false,
        trades: signaux.length,
        minimum: MINIMUM_TRADES,
        message:
          `Il faut ${MINIMUM_TRADES} trades termines pour qu'un historique ` +
          `veuille dire quelque chose. Il y en a ${signaux.length}.`,
        courbe: [],
        stats: null,
      });
    }

    let capital = DEPART;
    let pic = DEPART;
    let reculMax = 0;
    let gains = 0;
    let sommeGains = 0;
    let sommePertes = 0;
    const courbe: { date: string; capital: number }[] = [
      { date: signaux[0].closed_at!, capital: DEPART },
    ];

    for (const s of signaux) {
      // position_size_pct est le RISQUE du signal, pas la somme engagee.
      // Pour rester coherent avec le moteur, on reconstruit la mise a partir
      // de la distance au stop. Avant ce correctif, la demo traitait 0,6 %
      // de risque comme 0,6 % du capital engage : elle sous-estimait donc
      // l'exposition d'un facteur pouvant etre tres important.
      const risque = (s.position_size_pct ?? PART_PAR_DEFAUT) / 100;
      const distanceStop = s.entry_price && s.stop_loss
        ? Math.abs(s.entry_price - s.stop_loss) / Math.abs(s.entry_price)
        : 0;
      const part = distanceStop > 0
        ? Math.min(0.90, risque / distanceStop)
        : 0;

      const variationPrix = (s.result_pct ?? 0) / 100;
      const notionnel = capital * part;
      // Bitvavo spot : taker a l'entree ET a la sortie, palier de base.
      // La simulation publique doit etre prudente et annoncer ce cout.
      const frais = notionnel * 0.0025 + notionnel * (1 + variationPrix) * 0.0025;
      const resultat = notionnel * variationPrix - frais;
      capital += resultat;

      if (resultat > 0) { gains += 1; sommeGains += resultat; }
      else { sommePertes += Math.abs(resultat); }

      pic = Math.max(pic, capital);
      if (pic > 0) reculMax = Math.max(reculMax, (pic - capital) / pic * 100);

      courbe.push({
        date: s.closed_at!,
        capital: Math.round(capital * 100) / 100,
      });
    }

    const n = signaux.length;
    return reponse({
      fiable: true,
      trades: n,
      depart: DEPART,
      courbe,
      stats: {
        capital_final: Math.round(capital * 100) / 100,
        variation_pct: Math.round((capital / DEPART - 1) * 1000) / 10,
        taux_reussite: Math.round(gains / n * 1000) / 10,
        gain_moyen: Math.round(sommeGains / Math.max(1, gains) * 100) / 100,
        perte_moyenne:
          Math.round(sommePertes / Math.max(1, n - gains) * 100) / 100,
        recul_max_pct: Math.round(reculMax * 10) / 10,
        // Combien d'euros gagnes pour un euro perdu. Sans perte du tout,
        // le rapport est infini : on rend `null` plutot qu'un nombre
        // spectaculaire qui ne veut rien dire sur un petit echantillon.
        facteur_profit: sommePertes > 0
          ? Math.round(sommeGains / sommePertes * 100) / 100
          : null,
      },
      hypotheses: [
        `Depart a ${DEPART.toLocaleString("fr-FR")} EUR.`,
        "Tous les signaux suivis, aucun manque.",
        "Frais taker Bitvavo de 0,25 % a l'entree et a la sortie deduits.",
        "Mise reconstruite depuis le risque du signal et la distance au stop, plafonnee a 90 % du capital.",
        "Le spread et le slippage reel peuvent encore rendre le resultat reel different.",
        "Ceci est une simulation, pas le resultat d'un compte reel.",
      ],
    });
  })
);
