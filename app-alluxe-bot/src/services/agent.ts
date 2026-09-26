/**
 * Alluxe -- l'agent personnel (tab 4). Meme principe de file que Luna :
 * l'app depose un message `user`, `ops/agent_alluxe.py` (service
 * permanent sur le VPS, PAS un cron) le lit et depose la reponse.
 */
import { supabase } from "./supabase";

export interface Message {
  id: number;
  created_at: string;
  role: "user" | "assistant";
  contenu: string;
  outils: string[];
}

const COLONNES = "id, created_at, role, contenu, outils";

export async function conversation(limite = 50): Promise<Message[]> {
  const { data, error } = await supabase
    .from("alluxe_agent_messages")
    .select(COLONNES)
    .order("created_at", { ascending: true })
    .limit(limite);
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return [];
    throw error;
  }
  return (data ?? []) as unknown as Message[];
}

export async function envoyerMessage(contenu: string): Promise<void> {
  const { error } = await supabase
    .from("alluxe_agent_messages")
    .insert({ role: "user", contenu: contenu.trim() });
  if (error) throw error;
}

/**
 * Ecoute temps reel de la conversation.
 *
 * Le polling reste le filet de securite, mais l'interface n'attend plus
 * son prochain passage pour afficher une reponse. Le service VPS continue
 * de deposer les reponses dans la meme table.
 */
export function ecouterConversation(
  onMessage: (message: Message) => void,
): () => void {
  const canal = supabase
    .channel("alluxe-agent-conversation")
    .on(
      "postgres_changes",
      {
        event: "INSERT",
        schema: "public",
        table: "alluxe_agent_messages",
      },
      (payload) => {
        const message = payload.new as unknown as Message;
        if (message?.id) onMessage(message);
      },
    )
    .subscribe();

  return () => {
    void supabase.removeChannel(canal);
  };
}
