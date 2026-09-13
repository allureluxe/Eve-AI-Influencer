/**
 * L'abonnement Eve Plus, via RevenueCat.
 *
 * LA REGLE QUI GOUVERNE CE FICHIER
 * --------------------------------
 * L'APPLICATION NE DECIDE JAMAIS SI QUELQU'UN EST ABONNE.
 *
 * RevenueCat sait ce que Google Play a facture, et il previent notre
 * serveur par un webhook, qui met a jour `profiles.tier`. L'application
 * LIT ce champ. Elle ne le calcule pas, ne le devine pas, ne le met pas
 * en cache pour « aller plus vite ».
 *
 * Ce n'est pas de la mefiance envers l'utilisateur, c'est de la
 * cohesion : le serveur filtre deja les signaux par palier. Si
 * l'application se croyait abonnee alors que le serveur ne la reconnait
 * pas, elle afficherait un ecran d'abonne vide — et un abonne qui paie
 * et ne voit rien est bien pire qu'un resiliement.
 *
 * Le seul role de RevenueCat ici : ouvrir la fenetre d'achat, et
 * prevenir le serveur. Le statut, lui, vient toujours du profil.
 */

import Constants from "expo-constants";
import { Linking, Platform } from "react-native";
import Purchases, { PurchasesPackage } from "react-native-purchases";
import { supabase } from "./supabase";

/** L'identifiant du droit, tel que declare dans RevenueCat. */
const DROIT = "plus";

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

export interface OffrePlus {
  identifiant: string;
  prix: string;
  periode: string;
  essaiJours: number | null;
  paquet: PurchasesPackage;
}

/** L'offre telle que Google Play la facture, dans la devise du compte. */
export async function lireOffre(): Promise<OffrePlus | null> {
  try {
    const offres = await Purchases.getOfferings();
    const paquet = offres.current?.monthly ?? offres.current?.availablePackages?.[0];
    if (!paquet) return null;

    const p = paquet.product;
    // La periode d'essai vient du produit, pas d'une constante : si un
    // jour l'essai passe de 7 a 14 jours dans Play Console, l'ecran
    // suit tout seul. Un « 7 jours » ecrit en dur deviendrait faux
    // sans que personne ne le remarque — et un prix ou une duree faux
    // affiches avant un achat sont un probleme reglementaire.
    const essai = p.introPrice?.periodNumberOfUnits ?? null;
    return {
      identifiant: paquet.identifier,
      prix: p.priceString,
      periode: "par mois",
      essaiJours: essai !== null && p.introPrice?.periodUnit === "DAY"
        ? essai
        : essai !== null && p.introPrice?.periodUnit === "WEEK"
        ? essai * 7 : null,
      paquet,
    };
  } catch {
    return null;
  }
}

export type ResultatAchat = "ok" | "annule" | "echec";

export async function souscrire(offre: OffrePlus): Promise<ResultatAchat> {
  try {
    const { customerInfo } = await Purchases.purchasePackage(offre.paquet);
    // On ne se fie pas a ce retour pour DEBLOQUER quoi que ce soit : il
    // sert seulement a savoir si l'achat a abouti cote magasin. Le
    // deblocage viendra du webhook, via le profil.
    return customerInfo.entitlements.active[DROIT] ? "ok" : "echec";
  } catch (e: unknown) {
    const err = e as { userCancelled?: boolean };
    return err?.userCancelled ? "annule" : "echec";
  }
}

/** « J'ai deja paye sur un autre telephone. » */
export async function restaurer(): Promise<boolean> {
  try {
    const info = await Purchases.restorePurchases();
    return Boolean(info.entitlements.active[DROIT]);
  } catch {
    return false;
  }
}

/** La date du prochain prelevement, pour l'ecran de gestion. */
export async function prochainPrelevement(): Promise<Date | null> {
  try {
    const info = await Purchases.getCustomerInfo();
    const droit = info.entitlements.active[DROIT];
    return droit?.expirationDate ? new Date(droit.expirationDate) : null;
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
  const paquet = "app.eve.signaux";
  const url = `https://play.google.com/store/account/subscriptions?package=${paquet}`;
  await Linking.openURL(url);
}

/**
 * Le palier REEL, lu sur le serveur. La seule source de verite.
 */
export async function lirePalier(): Promise<"free" | "plus"> {
  const { data: session } = await supabase.auth.getSession();
  const id = session.session?.user?.id;
  if (!id) return "free";
  const { data } = await supabase
    .from("profiles").select("tier").eq("id", id).single();
  return (data?.tier as "free" | "plus") ?? "free";
}
