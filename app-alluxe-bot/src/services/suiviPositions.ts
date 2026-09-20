/**
 * Suivi EN DIRECT des positions ouvertes -- reel ou demo selon `estDemo`.
 *
 * Deux ressorts, jamais un rafraichissement periodique de la liste
 * elle-meme (demande explicite de l'operateur, 18 sept. : « que ce soit
 * du direct, pas toutes les 10 secondes ») :
 *
 * 1. La LISTE des positions (ouverture/cloture) change rarement -- elle
 *    est suivie par abonnement Supabase Realtime sur `signals`, filtre
 *    `is_demo`. Un changement recharge la liste, mais rien ne l'interroge
 *    en boucle.
 * 2. Le PRIX de chaque position change en continu -- il vient de
 *    `usePrixLive` (Bitvavo direct, un seul appel pour tous les marches),
 *    qui tourne seulement tant qu'il y a au moins une position a suivre.
 */
import React from "react";
import { supabase } from "./supabase";
import { Position, positionsOuvertes, positionsOuvertesDemo, etatCapital } from "./robot";
import { usePrixLive, PrixLive } from "./prixLive";

export interface SuiviPositions {
  positions: Position[] | null;
  capital: number;
  prixLive: PrixLive;
  erreur: string;
  rafraichir: () => Promise<void>;
}

/** `compte` : quelle simulation suivre. Sans objet en mode reel. */
export function useSuiviPositions(estDemo: boolean, capitalDemo: number,
                                  compte = "demo"): SuiviPositions {
  const [positions, setPositions] = React.useState<Position[] | null>(null);
  const [capital, setCapital] = React.useState<number>(capitalDemo);
  const [erreur, setErreur] = React.useState("");

  const charger = React.useCallback(async () => {
    try {
      const p = await (estDemo ? positionsOuvertesDemo(compte) : positionsOuvertes());
      setPositions(p);
      setErreur("");
    } catch (err: any) {
      setErreur(err?.message ?? "Erreur de chargement");
    }
  }, [estDemo, compte]);

  React.useEffect(() => {
    charger();
    // Realtime : toute ouverture/cloture republiee (voir SignalPublisher)
    // recharge la liste. Filtre cote serveur -- un canal demo n'est
    // jamais reveille par un changement reel, et inversement.
    const canal = supabase
      .channel(`positions-direct-${estDemo ? "demo" : "reel"}`)
      .on("postgres_changes", {
        event: "*", schema: "public", table: "signals",
        filter: `is_demo=eq.${estDemo}`,
      }, () => { charger(); })
      .subscribe();
    return () => { supabase.removeChannel(canal); };
  }, [charger, estDemo]);

  React.useEffect(() => {
    // Le capital demo est une constante connue (500 EUR virtuels, voir
    // robot.demo.json) -- aucune table ne le publie, ca n'a pas de sens
    // d'interroger le reseau pour une valeur fixe.
    if (estDemo) return;
    let vivant = true;
    etatCapital().then((e) => { if (vivant && e) setCapital(e.capital_eur); }).catch(() => {});
    return () => { vivant = false; };
  }, [estDemo, compte]);

  const paires = React.useMemo(
    () => Array.from(new Set((positions ?? []).map((p) => p.pair))),
    [positions],
  );
  const prixLive = usePrixLive(paires.length > 0);

  return { positions, capital, prixLive, erreur, rafraichir: charger };
}
