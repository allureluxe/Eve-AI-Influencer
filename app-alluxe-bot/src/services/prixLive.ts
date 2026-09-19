/**
 * Cotations Bitvavo EN DIRECT, cote client -- demande explicite de
 * l'operateur (18 sept.) : « que ce soit du direct, pas toutes les
 * 10 secondes ».
 *
 * Le robot ne republie PAS le prix courant des positions ouvertes (il ne
 * publie qu'a l'ouverture/la cloture, voir gold_bot/signal_publisher.py) :
 * repasser par Supabase pour ca ajouterait un aller-retour serveur inutile
 * pour une donnee deja publique. L'API ticker de Bitvavo ne demande
 * aucune cle et rend TOUS les marches en un seul appel -- un seul
 * `fetch`, quel que soit le nombre de positions ouvertes.
 */
import React from "react";

export type PrixLive = Record<string, number>;

export async function prixBitvavoTousMarches(): Promise<PrixLive> {
  const reponse = await fetch("https://api.bitvavo.com/v2/ticker/price");
  if (!reponse.ok) {
    throw new Error(`Bitvavo ticker : HTTP ${reponse.status}`);
  }
  const lignes: Array<{ market: string; price: string }> = await reponse.json();
  const carte: PrixLive = {};
  for (const l of lignes) {
    // "BTC-EUR" -> "BTC/EUR", le meme format que `signals.pair`.
    carte[l.market.replace("-", "/")] = parseFloat(l.price);
  }
  return carte;
}

/**
 * Rafraichit la carte des prix a un rythme rapide tant que `actif` est
 * vrai (typiquement : au moins une position ouverte a suivre). Garde le
 * dernier prix connu si un appel echoue, plutot que d'afficher un trou.
 */
export function usePrixLive(actif: boolean, rythmeMs = 3000): PrixLive {
  const [prix, setPrix] = React.useState<PrixLive>({});

  React.useEffect(() => {
    if (!actif) return;
    let vivant = true;
    const tick = async () => {
      try {
        const carte = await prixBitvavoTousMarches();
        if (vivant) setPrix(carte);
      } catch {
        // pas grave : on garde les derniers prix connus jusqu'au prochain tick
      }
    };
    tick();
    const id = setInterval(tick, rythmeMs);
    return () => { vivant = false; clearInterval(id); };
  }, [actif, rythmeMs]);

  return prix;
}
