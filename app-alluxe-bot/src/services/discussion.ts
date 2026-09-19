/**
 * La conversation avec le robot -- ce que faisait Telegram.
 *
 * Decision de l'operateur le 19 septembre : « je n'ai plus besoin des
 * messages Telegram [...] l'onglet Discussion, je veux que ce soit ici
 * que je reçois les messages et là où je peux écrire, comme la demande
 * rapport allure ».
 *
 * Le robot repond via `ops/ecoute_discussion.py`, lance chaque minute
 * par cron -- exactement comme `ecoute_telegram.py` avant lui, et avec
 * la MEME interpretation des commandes (`gold_bot/commandes.py`).
 */
import { supabase } from "./supabase";

export interface Message {
  id: number;
  created_at: string;
  auteur: "operateur" | "robot";
  texte: string;
  /** La page ALLURE complete, quand la reponse en porte une. */
  rapport_html: string | null;
  rapport_titre: string | null;
  traite: boolean;
  /** Present seulement sur les lignes venues des ALERTES du robot :
   *  sert a les marquer visuellement (une alerte critique ne se lit pas
   *  comme une reponse a une question). */
  niveau?: "debug" | "info" | "trade" | "warning" | "critical";
}

/** Les colonnes SANS la page : elle pese ~50 ko par rapport, et charger
 *  dix rapports a l'ouverture de l'onglet rendrait la liste lente pour
 *  rien. On ne la lit qu'au moment de l'ouvrir. */
const COLONNES_LISTE =
  "id, created_at, auteur, texte, rapport_titre, traite";

/**
 * LE FIL EST UNIQUE, COMME SUR TELEGRAM.
 *
 * Telegram melait tout dans une seule conversation : les alertes du
 * robot (« achat BTC », « robot suspendu ») ET les reponses aux
 * commandes. Les separer en deux onglets aurait ete une application de
 * plus a surveiller, pas le remplacement demande -- « en gros, ce que
 * fait Telegram, tu mets tout dans le mode discussion d'Alluxbot ».
 *
 * L'onglet Alertes reste : il sert a relire par niveau de gravite, ce
 * qu'un fil chronologique ne permet pas.
 *
 * Seules les alertes REELLES entrent ici (`is_demo=false`). Celles de la
 * simulation ont leur propre place -- la confusion des deux a deja coute
 * une fausse joie le 18 septembre.
 */
export async function messages(limite = 60): Promise<Message[]> {
  const [fil, alertes] = await Promise.all([
    supabase.from("alluxe_bot_discussion")
      .select(COLONNES_LISTE)
      .order("created_at", { ascending: false }).limit(limite),
    supabase.from("alluxe_bot_alertes")
      .select("id, created_at, niveau, titre, corps")
      .eq("is_demo", false)
      .order("created_at", { ascending: false }).limit(limite),
  ]);
  if (fil.error) throw fil.error;

  const lignes: Message[] = ((fil.data ?? []) as unknown as Message[]);

  // Une panne du cote des alertes ne doit pas vider la conversation.
  if (!alertes.error) {
    for (const a of (alertes.data ?? []) as any[]) {
      lignes.push({
        // Identifiant distinct : les deux tables ont leurs propres
        // compteurs, et deux lignes de meme `id` feraient disparaitre
        // l'une des deux de la liste React.
        id: -Number(a.id),
        created_at: a.created_at,
        auteur: "robot",
        texte: a.corps ? `${a.titre}\n${a.corps}` : a.titre,
        rapport_html: null, rapport_titre: null, traite: true,
        niveau: a.niveau,
      });
    }
  }

  // Du plus ancien au plus recent : c'est une conversation.
  lignes.sort((a, b) =>
    new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  return lignes.slice(-limite);
}

/** La page d'un rapport, chargee seulement quand on l'ouvre. */
export async function rapport(id: number): Promise<string | null> {
  const { data, error } = await supabase
    .from("alluxe_bot_discussion")
    .select("rapport_html")
    .eq("id", id)
    .maybeSingle();
  if (error) throw error;
  return (data?.rapport_html as string | null) ?? null;
}

/**
 * Depose une demande. Le robot la traite dans la minute.
 *
 * La reponse n'est pas attendue ici : elle arrive par Realtime, comme
 * un message dans une conversation.
 */
export async function ecrire(texte: string): Promise<void> {
  const { error } = await supabase
    .from("alluxe_bot_discussion")
    .insert({ auteur: "operateur", texte });
  if (error) throw error;
}

/** Suit le fil en direct : une reponse doit apparaitre sans rafraichir. */
export function suivre(surNouveau: () => void): () => void {
  // LES DEUX TABLES, pas seulement la conversation : une alerte du robot
  // fait partie du fil, et n'apparaitrait sinon qu'au prochain
  // chargement manuel -- c'est-a-dire trop tard pour une alerte.
  const canal = supabase
    .channel("discussion")
    .on("postgres_changes",
        { event: "*", schema: "public", table: "alluxe_bot_discussion" },
        () => surNouveau())
    .on("postgres_changes",
        { event: "INSERT", schema: "public", table: "alluxe_bot_alertes" },
        () => surNouveau())
    .subscribe();
  return () => { supabase.removeChannel(canal); };
}

/** Ce que le robot comprend -- repris mot pour mot de `gold_bot/commandes.py`. */
export const RACCOURCIS = [
  { texte: "rapport allure", aide: "la page depuis ta dernière demande" },
  { texte: "rapport jour", aide: "les dernières 24 heures" },
  { texte: "rapport semaine", aide: "les 7 derniers jours" },
  { texte: "etat", aide: "le point en deux lignes" },
] as const;
