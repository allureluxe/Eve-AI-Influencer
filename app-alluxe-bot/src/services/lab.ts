import { supabase } from "./supabase";

export interface LabStatus {
  id: string;
  stage: string;
  detail: string;
  completed: number;
  candidates: number;
  validated: number;
  updated_at: string;
}

export interface LabResearch {
  id: number;
  created_at: string;
  sujet: string;
  mode: string;
  famille: string;
  titre: string;
  url: string;
  hypothese: string;
  conditions: string;
  statut: string;
}

export interface LabStrategy {
  strategy_id: string;
  agent: string;
  parent_id: string | null;
  stage: string;
  fingerprint: string;
  params: Record<string, unknown>;
  backtest: Record<string, any>;
  forward_test: Record<string, any> | null;
  reason: string;
  created_at: string;
}

export async function labStatus(): Promise<LabStatus | null> {
  const { data, error } = await supabase
    .from("lab_status").select("*").eq("id", "robot").maybeSingle();
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return null;
    throw error;
  }
  return data as LabStatus | null;
}

export async function labStrategies(limite = 30): Promise<LabStrategy[]> {
  const { data, error } = await supabase
    .from("lab_strategies").select("*")
    .order("created_at", { ascending: false }).limit(limite);
  if (error) {
    // LES DEUX FORMULATIONS. PostgREST ne dit PAS « relation does not
    // exist » quand une table manque : il repond « Could not find the
    // table 'public.lab_research' in the schema cache ». Ce garde-fou,
    // ecrit pour le message de PostgreSQL, ne rattrapait donc rien et
    // l'ecran Laboratoire levait l'erreur — constate le 26 septembre,
    // la table n'ayant jamais ete creee.
    if (/relation .* does not exist/i.test(error.message)
        || /could not find the table/i.test(error.message)
        || error.code === "PGRST205") return [];
    throw error;
  }
  return (data ?? []) as LabStrategy[];
}


export function ecouterLab(
  onStatus: (status: LabStatus) => void,
  onStrategy: (strategy: LabStrategy) => void,
): () => void {
  const canal = supabase
    .channel("strategy-lab-live")
    .on(
      "postgres_changes",
      { event: "INSERT", schema: "public", table: "lab_status" },
      (payload) => onStatus(payload.new as LabStatus),
    )
    .on(
      "postgres_changes",
      { event: "UPDATE", schema: "public", table: "lab_status" },
      (payload) => onStatus(payload.new as LabStatus),
    )
    .on(
      "postgres_changes",
      { event: "INSERT", schema: "public", table: "lab_strategies" },
      (payload) => onStrategy(payload.new as LabStrategy),
    )
    .on(
      "postgres_changes",
      { event: "UPDATE", schema: "public", table: "lab_strategies" },
      (payload) => onStrategy(payload.new as LabStrategy),
    )
    .subscribe();

  return () => {
    void supabase.removeChannel(canal);
  };
}


export async function labResearch(limite = 20): Promise<LabResearch[]> {
  const { data, error } = await supabase
    .from("lab_research").select("*")
    .order("created_at", { ascending: false }).limit(limite);
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return [];
    throw error;
  }
  return (data ?? []) as LabResearch[];
}
