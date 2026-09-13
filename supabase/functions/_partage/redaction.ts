/**
 * Le texte des notifications, et la garantie qu'il reste sobre.
 *
 * POURQUOI C'EST UN FICHIER A PART, TESTE
 * ---------------------------------------
 * Une notification est ce que l'utilisateur voit le plus souvent de
 * l'application — souvent la seule chose qu'il en voit. C'est elle qui
 * la fait passer pour un outil serieux ou pour une arnaque de plus.
 *
 * Trois interdits, sans exception :
 *   - jamais de point d'exclamation ;
 *   - jamais d'emoji ;
 *   - jamais de promesse de gain, ni d'incitation a agir.
 *
 * Ces regles sont faciles a respecter le jour ou on ecrit le code, et
 * faciles a perdre six mois plus tard quand on ajoute un message « pour
 * faire revenir les gens ». D'ou le controle `verifierLeTon()`, appele
 * par chaque redacteur : le texte fautif ne part pas.
 */

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2190}-\u{21FF}]/u;

const PROMESSE =
  /(garanti|assure|sans risque|profit certain|a coup sur|argent facile|ne rate pas|derniere chance|il faut acheter|fonce)/i;

export class TonRefuse extends Error {}

/** Refuse un texte qui enfreint les trois interdits. */
export function verifierLeTon(texte: string): string {
  if (texte.includes("!")) {
    throw new TonRefuse(`point d'exclamation : ${texte}`);
  }
  if (EMOJI.test(texte)) {
    throw new TonRefuse(`emoji : ${texte}`);
  }
  const promesse = texte.match(PROMESSE);
  if (promesse) {
    throw new TonRefuse(`promesse de gain : ${promesse[0]}`);
  }
  return texte;
}

/** « 58420.5 » -> « 58 420 EUR ». Sans decimales inutiles. */
export function prixLisible(prix: number): string {
  const decimales = prix >= 100 ? 0 : prix >= 1 ? 2 : 6;
  return `${prix.toLocaleString("fr-FR", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })} EUR`;
}

const NOMS: Record<string, string> = {
  BTC: "Bitcoin", ETH: "Ethereum", SOL: "Solana", XRP: "XRP",
  ADA: "Cardano", DOGE: "Dogecoin", LINK: "Chainlink",
  AVAX: "Avalanche", DOT: "Polkadot", LTC: "Litecoin",
};

export function nomCourant(paire: string): string {
  const base = paire.split("/")[0].toUpperCase();
  return NOMS[base] ?? base;
}

export interface Message {
  titre: string;
  corps: string;
}

/** « Nouveau signal — Bitcoin, achat a 58 420 EUR » */
export function texteSignal(paire: string, sens: string, prix: number): Message {
  const action = sens === "buy" ? "achat" : "vente";
  return {
    titre: verifierLeTon("Nouveau signal"),
    corps: verifierLeTon(
      `${nomCourant(paire)}, ${action} a ${prixLisible(prix)}`),
  };
}

/** « Inflation americaine dans 15 minutes. » */
export function texteMacro(nom: string, minutes: number): Message {
  return {
    titre: verifierLeTon("Annonce economique"),
    corps: verifierLeTon(
      `${nom} dans ${minutes} minutes. ` +
      `Pense a verifier tes positions ouvertes.`),
  };
}

/** « Ton trade Bitcoin est termine : +4,2 % » */
export function texteCloture(paire: string, resultatPct: number): Message {
  const chiffre = `${resultatPct >= 0 ? "+" : ""}${
    resultatPct.toFixed(1).replace(".", ",")} %`;
  return {
    titre: verifierLeTon("Trade termine"),
    // ON ANNONCE LES DEUX SENS DE LA MEME FACON. Ne notifier que les
    // gains donnerait une impression de reussite que l'historique ne
    // porte pas, et c'est precisement le mensonge par omission que
    // l'application doit ne jamais faire.
    corps: verifierLeTon(`${nomCourant(paire)} : ${chiffre}`),
  };
}
