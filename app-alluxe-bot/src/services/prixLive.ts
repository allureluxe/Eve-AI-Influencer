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

/**
 * LE CARNET D'ORDRES, PAS LE DERNIER PRIX D'ECHANGE.
 *
 * `/ticker/price` rend le prix du DERNIER ECHANGE. Sur un marche peu
 * anime, il ne bouge pas tant que personne n'echange -- et il affiche
 * alors un cours vieux d'une heure sans rien signaler.
 *
 * Releve par l'operateur le 21 septembre : « une position qui ne bouge
 * pas d'un centime en 1 h, je n'ai jamais vu ca ». Il avait raison, et
 * j'avais d'abord conclu a tort que le marche etait simplement plat.
 * Mesure sur RUNE-EUR, a la meme seconde :
 *
 *     /ticker/price        0,53083   <- fige depuis une heure
 *     /ticker/24h « last » 0,53502   <- dernier echange reel
 *     carnet : achat       0,53553
 *              vente       0,53695
 *
 * Le carnet, lui, suit en continu : il donne ce que quelqu'un est pret a
 * payer MAINTENANT, meme si aucun echange n'a eu lieu depuis vingt
 * minutes. C'est aussi ce que lit le robot (`BitvavoProvider.fetch_tick`),
 * donc l'ecran et le robot parlent enfin du meme prix.
 *
 * Le milieu entre achat et vente est retenu : c'est la convention du
 * reste du depot, et elle ne favorise ni l'acheteur ni le vendeur.
 */
export async function prixBitvavoTousMarches(): Promise<PrixLive> {
  const reponse = await fetch("https://api.bitvavo.com/v2/ticker/book");
  if (!reponse.ok) {
    throw new Error(`Bitvavo ticker : HTTP ${reponse.status}`);
  }
  const lignes: Array<{ market: string; bid?: string; ask?: string }> =
    await reponse.json();
  const carte: PrixLive = {};
  for (const l of lignes) {
    const achat = parseFloat(l.bid ?? "0");
    const vente = parseFloat(l.ask ?? "0");
    const valeur = achat > 0 && vente > 0 ? (achat + vente) / 2
                 : achat > 0 ? achat : vente;
    // "BTC-EUR" -> "BTC/EUR", le meme format que `signals.pair`.
    if (valeur > 0) carte[l.market.replace("-", "/")] = valeur;
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
