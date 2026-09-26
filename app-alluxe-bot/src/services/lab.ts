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
    if (/relation .* does not exist/i.test(error.message)) return [];
    throw error;
  }
  return (data ?? []) as LabStrategy[];
}
