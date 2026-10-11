/** Validation d'une commande de la boutique de Noël. Pure : testable sans réseau.
 *  Les prix ne viennent JAMAIS du navigateur : seul catalogue.json (lu sur le site) fait foi. */

export const MAX_PHOTO_OCTETS = 6_000_000;   // après redimensionnement côté navigateur (~2048 px)
export const PAYS_LIVRES = ["FR", "BE", "LU", "CH", "DE", "ES", "IT", "NL", "PT", "AT", "IE"];

export type Produit = { id: string; nom: string; prix: number; actif: boolean };
export type Catalogue = { commandes_ouvertes: boolean; styles: { id: string }[]; produits: Produit[] };
export type Commande = { produit: Produit; style: string; sujet: string; prenom: string; email: string;
  photo: Uint8Array; type: "image/jpeg" | "image/png" };

const coupe = (v: unknown, n: number) => (typeof v === "string" ? v.trim().slice(0, n) : "");
export const SUJETS = ["Ma famille", "Mon couple", "Mes enfants", "Mon enfant", "Mon bébé", "Une femme", "Un homme", "Mon chien", "Mon chat", "Un autre animal"];

function decoder(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Rend la commande propre, « spam » pour un robot, ou un message pour le visiteur. */
export function valider(brut: Record<string, unknown>, cat: Catalogue): Commande | string {
  if (coupe(brut.site_web, 200)) return "spam";
  if (!cat.commandes_ouvertes) return "Les commandes ne sont pas encore ouvertes.";
  if (brut.cgv !== true) return "Merci d'accepter les conditions de vente.";
  const produit = cat.produits.find((p) => p.actif && p.id === coupe(brut.produit, 40));
  if (!produit) return "Choisissez un support.";
  const style = coupe(brut.style, 40);
  if (!cat.styles.some((s) => s.id === style)) return "Choisissez un style.";
  const sujet = coupe(brut.sujet, 40);
  if (!SUJETS.includes(sujet)) return "Dites-nous pour qui est le portrait.";
  const prenom = coupe(brut.prenom, 80), email = coupe(brut.email, 200).toLowerCase();
  if (prenom.length < 2) return "Indiquez votre prénom.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return "Adresse e-mail invalide.";
  const m = /^data:(image\/(?:jpeg|png));base64,([A-Za-z0-9+/=]+)$/.exec(coupe(brut.photo, 9_000_000));
  if (!m) return "Ajoutez une photo (JPEG ou PNG).";
  let photo: Uint8Array;
  try { photo = decoder(m[2]); } catch { return "Photo illisible, essayez-en une autre."; }
  if (photo.length < 20_000) return "Photo trop petite : prenez-en une plus nette.";
  if (photo.length > MAX_PHOTO_OCTETS) return "Photo trop lourde.";
  return { produit, style, sujet, prenom, email, photo, type: m[1] as Commande["type"] };
}

/** Corps x-www-form-urlencoded d'une session Stripe Checkout (adresse collectée par Stripe). */
export function corpsStripe(c: Commande, id: string, base: string): URLSearchParams {
  const p = new URLSearchParams({
    mode: "payment",
    customer_email: c.email,
    client_reference_id: id,
    "metadata[commande]": id,
    success_url: `${base}/merci.html?c=${id}`,
    cancel_url: `${base}/#commander`,
    "line_items[0][quantity]": "1",
    "line_items[0][price_data][currency]": "eur",
    "line_items[0][price_data][unit_amount]": String(Math.round(c.produit.prix * 100)),
    "line_items[0][price_data][product_data][name]": `Portrait de Noël — ${c.produit.nom}`,
    "phone_number_collection[enabled]": "true",
    locale: "fr",
  });
  PAYS_LIVRES.forEach((pays, i) => p.set(`shipping_address_collection[allowed_countries][${i}]`, pays));
  return p;
}
