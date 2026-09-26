/**
 * Alluxe -- l'agent personnel (tab 4). Meme principe de file que Luna :
 * l'app depose un message `user`, `ops/agent_alluxe.py` (service
 * permanent sur le VPS, PAS un cron) le lit et depose la reponse.
 */
import { supabase } from "./supabase";
import { tableAbsente } from "./postgrest";

export interface Message {
  id: number;
  created_at: string;
  role: "user" | "assistant";
  contenu: string;
  outils: string[];
}

const COLONNES = "id, created_at, role, contenu, outils";

export async function conversation(limite = 50): Promise<Message[]> {
  // LES DERNIERS MESSAGES, PAS LES PREMIERS.
  //
  // Cette fonction demandait « les 50 plus ANCIENS » : un tri croissant
  // suivi d'un `limit`. Tant que la conversation tenait sous 50
  // messages, personne ne pouvait s'en apercevoir — les 50 premiers
  // ETAIENT toute la conversation.
  //
  // Au 81e message, le 26 septembre, l'ecran s'est fige sur des
  // echanges de la mi-septembre. Les messages partaient, l'agent
  // repondait en deux secondes, et RIEN ne s'affichait. L'operateur :
  // « j'ai ecrit slt, ca s'ecrit meme pas ».
  //
  // On trie donc a l'ENVERS pour prendre la fin, puis on remet dans
  // l'ordre de lecture. Une erreur d'un mot, invisible pendant deux
  // semaines, et qui cassait entierement la conversation.
  const { data, error } = await supabase
    .from("alluxe_agent_messages")
    .select(COLONNES)
    .order("created_at", { ascending: false })
    .limit(limite);
  if (error) {
    if (tableAbsente(error)) return [];
    throw error;
  }
  // Remis dans l'ordre chronologique pour l'affichage.
  return ((data ?? []) as unknown as Message[]).reverse();
}

export async function envoyerMessage(contenu: string): Promise<void> {
  const { error } = await supabase
    .from("alluxe_agent_messages")
    .insert({ role: "user", contenu: contenu.trim() });
  if (!error) return;

  // UN REFUS DE DROITS NE DOIT PAS RESSEMBLER A UNE PANNE RESEAU.
  //
  // La regle d'ecriture exige `profiles.is_admin`. Le 26 septembre,
  // l'operateur avait SIX comptes sur la meme adresse, dont trois sans
  // ce droit : selon celui avec lequel il ouvrait l'application, l'envoi
  // partait ou etait refuse — et le message brut de PostgREST (« new row
  // violates row-level security policy ») ne dit rien a personne.
  //
  // Il decrivait le symptome ainsi : « les messages ne s'envoient pas,
  // tout le systeme de chat ne va pas ». La conversation paraissait
  // vide en plus, la lecture exigeant le meme droit.
  if (error.code === "42501" || /row-level security/i.test(error.message)) {
    throw new Error(
      "Ce compte n'a pas les droits d'administration : l'envoi est "
      + "refusé et la conversation reste vide. Connectez-vous avec le "
      + "compte administrateur, ou faites passer celui-ci en admin.");
  }
  throw error;
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
export interface AgentStatus {
  id: string;
  state: string;
  task: string;
  tool: string;
  detail: string;
  last_error: string;
  updated_at: string;
}

export interface AgentEvent {
  id: number;
  created_at: string;
  event_type: string;
  tool: string;
  status: string;
  summary: string;
  duration_ms: number;
}

export async function agentStatus(): Promise<AgentStatus | null> {
  const { data, error } = await supabase.from("alluxe_agent_status")
    .select("*").eq("id", "agent").maybeSingle();
  if (error) {
    if (tableAbsente(error)) return null;
    throw error;
  }
  return data as AgentStatus | null;
}

export async function agentEvents(limite = 20): Promise<AgentEvent[]> {
  const { data, error } = await supabase.from("alluxe_agent_events")
    .select("*").order("created_at", { ascending: false }).limit(limite);
  if (error) {
    if (tableAbsente(error)) return [];
    throw error;
  }
  return (data ?? []) as AgentEvent[];
}

export function ecouterAgent(
  onStatus: (status: AgentStatus) => void,
  onEvent: (event: AgentEvent) => void,
): () => void {
  const canal = supabase.channel("alluxe-agent-control")
    .on("postgres_changes", {event:"INSERT", schema:"public", table:"alluxe_agent_status"},
      p => onStatus(p.new as AgentStatus))
    .on("postgres_changes", {event:"UPDATE", schema:"public", table:"alluxe_agent_status"},
      p => onStatus(p.new as AgentStatus))
    .on("postgres_changes", {event:"INSERT", schema:"public", table:"alluxe_agent_events"},
      p => onEvent(p.new as AgentEvent))
    .subscribe();
  return () => { void supabase.removeChannel(canal); };
}
