/**
 * Les abonnements Allure, via RevenueCat.
 *
 * LA REGLE QUI GOUVERNE CE FICHIER
 * --------------------------------
 * L'APPLICATION NE DECIDE JAMAIS QUEL PALIER QUELQU'UN A.
 *
 * RevenueCat sait ce que Google Play a facture, et il previent notre
 * serveur par un webhook, qui met a jour `profiles.tier`. L'application
 * LIT ce champ. Elle ne le calcule pas, ne le devine pas, ne le met pas
 * en cache pour « aller plus vite ».
 *
 * Ce n'est pas de la mefiance envers l'utilisateur, c'est de la
 * cohesion : le serveur filtre deja les signaux sur ce champ. Si
 * l'application se croyait abonnee alors que le serveur ne la reconnait
 * pas, elle afficherait un ecran d'abonne vide — et un abonne qui paie
 * et ne voit rien est bien pire qu'un resiliement.
 */

import Constants from "expo-constants";
import { Linking, Platform } from "react-native";
import Purchases, { PurchasesPackage } from "react-native-purchases";
import { Offre, Palier } from "./api";
import { supabase } from "./supabase";

let initialise = false;

/**
 * Branche RevenueCat sur l'identifiant Supabase de l'utilisateur.
 *
 * L'`appUserID` DOIT etre l'identifiant Supabase : c'est lui que le
 * webhook renverra, et c'est comme ca que le serveur sait quel profil
 * mettre a jour. Laisser RevenueCat generer un identifiant anonyme
 * rendrait le rapprochement impossible.
 */
export async function demarrerAbonnement(idUtilisateur: string): Promise<void> {
  const cle = (Constants.expoConfig?.extra as Record<string, string>)
    ?.revenueCatAndroidKey;
  if (!cle || Platform.OS !== "android") return;

  if (!initialise) {
    Purchases.configure({ apiKey: cle, appUserID: idUtilisateur });
    initialise = true;
  } else {
    await Purchases.logIn(idUtilisateur);
  }
}

/** Les paquets du magasin, indexes par identifiant de produit. */
let paquets: Map<string, PurchasesPackage> = new Map();

/**
 * La grille d'offres, et les prix reels du magasin.
 *
 * La GRILLE vient de la base : c'est la meme table que celle sur
 * laquelle le serveur filtre, donc l'ecran ne peut pas promettre une
 * capacite que le serveur refuse.
 *
 * Les PRIX viennent de Google Play : la devise, les taxes et les
 * promotions locales changent selon le pays. Le prix indicatif de la
 * base ne sert que de repli, et il est alors annonce comme indicatif.
 */
export async function lireOffres(): Promise<{
  grille: Offre[];
  prix: Record<string, string>;
}> {
  const { data } = await supabase
    .from("offres")
    .select(`tier, rang, nom, accroche, toutes_paires, retard_minutes,
             positions_direct, note_du_matin, historique_complet,
             export_csv, produit_id, prix_indicatif_eur,
             produit_id_annuel, prix_indicatif_annuel_eur`)
    .order("rang");

  const grille = (data ?? []) as Offre[];
  const prix: Record<string, string> = {};

  try {
    const offres = await Purchases.getOfferings();
    for (const p of offres.current?.availablePackages ?? []) {
      paquets.set(p.product.identifier, p);
      prix[p.product.identifier] = p.product.priceString;
    }
  } catch {
    // Magasin injoignable : on rend la grille sans prix, et l'ecran
    // affiche l'indicatif en le disant.
  }

  return { grille, prix };
}

export type ResultatAchat = "ok" | "annule" | "echec" | "indisponible";

export async function souscrire(produitId: string): Promise<ResultatAchat> {
  const paquet = paquets.get(produitId);
  if (!paquet) return "indisponible";
  try {
    const { customerInfo } = await Purchases.purchasePackage(paquet);
    // Ce retour sert seulement a savoir si l'achat a abouti cote
    // magasin. Le deblocage viendra du webhook, via le profil.
    return Object.keys(customerInfo.entitlements.active).length > 0
      ? "ok" : "echec";
  } catch (e: unknown) {
    const err = e as { userCancelled?: boolean };
    return err?.userCancelled ? "annule" : "echec";
  }
}

/** « J'ai deja paye sur un autre telephone. » */
export async function restaurer(): Promise<boolean> {
  try {
    const info = await Purchases.restorePurchases();
    return Object.keys(info.entitlements.active).length > 0;
  } catch {
    return false;
  }
}

/** La date du prochain prelevement, pour l'ecran de gestion. */
export async function prochainPrelevement(): Promise<Date | null> {
  try {
    const info = await Purchases.getCustomerInfo();
    const actifs = Object.values(info.entitlements.active);
    const date = actifs[0]?.expirationDate;
    return date ? new Date(date) : null;
  } catch {
    return null;
  }
}

/**
 * Ouvre la page d'abonnements de Google Play.
 *
 * ON NE RESILIE PAS DEPUIS L'APPLICATION, et c'est une obligation :
 * Google Play exige que la resiliation passe par sa propre interface.
 * Un bouton « resilier » qui ferait autre chose — desactiver le compte,
 * envoyer un e-mail au support — laisserait l'utilisateur convaincu
 * d'avoir arrete alors qu'il continue d'etre preleve. C'est le grief
 * numero un contre ce genre d'applications.
 */
export async function ouvrirGestionPlay(): Promise<void> {
  const paquet = "fr.allure.trading";
  await Linking.openURL(
    `https://play.google.com/store/account/subscriptions?package=${paquet}`);
}

/** Le palier REEL, lu sur le serveur. La seule source de verite. */
export async function lirePalier(): Promise<Palier> {
  const { data: session } = await supabase.auth.getSession();
  const id = session.session?.user?.id;
  if (!id) return "free";
  const { data } = await supabase
    .from("profiles").select("tier").eq("id", id).single();
  return (data?.tier as Palier) ?? "free";
}

/**
 * La remise pour parrainage Bitvavo, CALCULEE PAR LA BASE.
 *
 * Une fonction plutot qu'une colonne : un pourcentage recopie sur le
 * profil se desynchroniserait le jour ou une confirmation est retiree,
 * et l'utilisateur garderait une remise a laquelle il n'a plus droit.
 */
export async function lireRemise(): Promise<number> {
  const { data: session } = await supabase.auth.getSession();
  const id = session.session?.user?.id;
  if (!id) return 0;
  const { data } = await supabase.rpc("remise_pct", { qui: id });
  return Number(data) || 0;
}
