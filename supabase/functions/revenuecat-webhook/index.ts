/**
 * Le webhook RevenueCat : la SEULE chose qui change `profiles.tier`.
 *
 * POURQUOI PERSONNE D'AUTRE N'A LE DROIT
 * --------------------------------------
 * Trois candidats voulaient decider du palier : l'application (qui sait
 * qu'un achat a abouti), le client RevenueCat (qui connait les droits
 * actifs), et ce webhook. Les deux premiers tournent sur le telephone
 * de l'utilisateur. Un palier decide la-bas est un palier qu'on peut
 * changer avec un telephone modifie — et comme le serveur filtre les
 * signaux sur ce champ, ce serait l'abonnement entier qui tomberait.
 *
 * Le webhook, lui, arrive de RevenueCat, qui l'a appris de Google Play,
 * qui a reellement encaisse. C'est la seule chaine ou chaque maillon
 * sait quelque chose que l'utilisateur ne peut pas inventer.
 *
 * Le `app_user_id` est l'identifiant Supabase : l'application le donne
 * a `Purchases.configure` au demarrage. Sans lui, le webhook ne saurait
 * pas quel profil mettre a jour.
 */

import { clientService, reponse } from "../_partage/commun.ts";

/** L'identifiant du droit, tel que declare dans RevenueCat. */
const DROIT = "plus";

/**
 * Les evenements qui DONNENT l'acces.
 * `INITIAL_PURCHASE` couvre l'essai gratuit : pendant l'essai,
 * l'utilisateur a le droit, meme si rien n'a encore ete preleve.
 */
const OUVRE = new Set([
  "INITIAL_PURCHASE", "RENEWAL", "PRODUCT_CHANGE",
  "UNCANCELLATION", "SUBSCRIPTION_EXTENDED", "TRANSFER",
]);

/**
 * Les evenements qui RETIRENT l'acces.
 *
 * `CANCELLATION` N'EN FAIT PAS PARTIE, et c'est le piege classique :
 * RevenueCat l'envoie au moment ou l'utilisateur clique « resilier »,
 * mais celui-ci a paye jusqu'a la fin de la periode. Couper la est un
 * vol, et c'est le motif de litige le plus frequent sur ce genre
 * d'abonnement. C'est `EXPIRATION` qui marque la vraie fin.
 */
const FERME = new Set(["EXPIRATION", "BILLING_ISSUE", "REFUND"]);

Deno.serve(async (requete) => {
  if (requete.method !== "POST") return reponse({ error: "POST" }, 405);

  // RevenueCat signe par un en-tete Authorization fixe, configure dans
  // son tableau de bord. Sans ce controle, n'importe qui pourrait
  // s'offrir un abonnement en envoyant un JSON.
  const attendu = Deno.env.get("REVENUECAT_WEBHOOK_SECRET");
  if (!attendu || requete.headers.get("Authorization") !== attendu) {
    return reponse({ error: "non autorise" }, 401);
  }

  let corps: { event?: Record<string, unknown> };
  try {
    corps = await requete.json();
  } catch {
    return reponse({ error: "JSON attendu" }, 400);
  }

  const ev = corps.event ?? {};
  const type = String(ev.type ?? "");
  const utilisateur = String(ev.app_user_id ?? "");
  const droit = ev.entitlement_ids as string[] | undefined;

  if (!utilisateur) return reponse({ error: "app_user_id manquant" }, 400);

  // Un evenement portant sur un autre droit ne nous concerne pas.
  if (droit && droit.length > 0 && !droit.includes(DROIT)) {
    return reponse({ ignore: `droit ${droit.join(",")}` });
  }

  let palier: "free" | "plus" | null = null;
  if (OUVRE.has(type)) palier = "plus";
  else if (FERME.has(type)) palier = "free";

  if (palier === null) {
    // CANCELLATION arrive ici : on l'enregistre sans rien changer.
    // L'acces tombera a l'EXPIRATION, pas avant.
    console.log(`revenuecat : ${type} pour ${utilisateur}, sans effet`);
    return reponse({ ignore: type });
  }

  const service = clientService();
  const { error } = await service
    .from("profiles").update({ tier: palier }).eq("id", utilisateur);

  if (error) {
    console.error("revenuecat :", error);
    // On rend une erreur pour que RevenueCat REESSAIE. Repondre 200 sur
    // un echec ferait perdre l'evenement definitivement, et un abonne
    // paierait sans jamais recevoir son acces.
    return reponse({ error: "mise a jour impossible" }, 500);
  }

  console.log(`revenuecat : ${utilisateur} -> ${palier} (${type})`);
  return reponse({ ok: true, tier: palier });
});
