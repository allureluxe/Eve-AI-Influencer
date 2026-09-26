/**
 * Luna -- donnees du personnage, creation des jobs medias/edito et
 * indicateurs de croissance. La generation reelle reste sur le VPS :
 * l'app depose un job puis observe son traitement via Supabase.
 */
import { supabase } from "./supabase";

export interface Persona {
  prenom: string;
  age: number;
  metier: string;
  contexte: string;
  caractere: string[];
  passions: string[];
}

export async function persona(): Promise<Persona | null> {
  const { data, error } = await supabase
    .from("luna_persona")
    .select("prenom, age, metier, contexte, caractere, passions")
    .eq("id", "luna")
    .maybeSingle();
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return null;
    throw error;
  }
  return data as unknown as Persona | null;
}

export type StatutPublication = "en_attente" | "en_cours" | "terminee" | "echec";
export type FormatLuna =
  | "legacy" | "feed_photo" | "story" | "highlight_story" | "reel"
  | "tiktok_short" | "tiktok_rewards" | "tiktok_photo";
export type PlateformeLuna = "instagram" | "tiktok" | "both";
export type TypeLieu =
  | "restaurant" | "bar" | "cafe" | "hotel" | "landmark"
  | "street" | "travel" | "other";
export type TrackMonetisation =
  | "growth" | "instagram_gifts" | "instagram_subscriptions"
  | "tiktok_creator_rewards" | "tiktok_series" | "brand_deals";

export interface Publication {
  id: string;
  created_at: string;
  demande: string;
  statut: StatutPublication;
  media_type: "auto" | "photo" | "video";
  reference_path: string | null;
  aspect_ratio: string;
  duration_seconds: number;
  quality: "brouillon" | "finale";
  provider: string | null;
  provider_task_id: string | null;
  generation_status: "queued" | "generating" | "succeeded" | "failed";
  publish_requested: boolean;
  published_at: string | null;
  published_platform: string | null;
  published_media_id: string | null;
  publication_task_id: string | null;
  publication_status: "pending" | "processing" | "published" | "failed" | null;
  highlight_status: "not_requested" | "pending_manual" | "saved" | null;
  content_format: FormatLuna;
  platform: PlateformeLuna;
  scheduled_at: string | null;
  timezone: string;
  location_name: string | null;
  location_city: string | null;
  location_type: TypeLieu | null;
  highlight_name: string | null;
  hook: string | null;
  call_to_action: string | null;
  hashtags: string[];
  ai_disclosure: boolean;
  monetization_track: TrackMonetisation;
  strategy_version: string;
  source_job: string | null;
  legende: string;
  scene_prompt: string;
  chemin_photo: string | null;
  chemin_voix: string | null;
  chemin_video: string | null;
  erreurs: Record<string, string>;
}

const COLONNES_PUBLICATION =
  "id, created_at, demande, statut, media_type, reference_path, aspect_ratio, duration_seconds, quality, provider, provider_task_id, generation_status, publish_requested, published_at, published_platform, published_media_id, publication_task_id, publication_status, highlight_status, content_format, platform, scheduled_at, timezone, location_name, location_city, location_type, highlight_name, hook, call_to_action, hashtags, ai_disclosure, monetization_track, strategy_version, source_job, legende, scene_prompt, chemin_photo, chemin_voix, chemin_video, erreurs";

export async function publications(limite = 60): Promise<Publication[]> {
  const { data, error } = await supabase
    .from("luna_publications")
    .select(COLONNES_PUBLICATION)
    .order("created_at", { ascending: false })
    .limit(limite);
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return [];
    throw error;
  }
  return (data ?? []) as unknown as Publication[];
}

export interface DemandeMediaLuna {
  demande?: string;
  content_format?: FormatLuna;
  platform?: PlateformeLuna;
  scheduled_at?: string | null;
  media_type?: "auto" | "photo" | "video";
  reference_path?: string | null;
  aspect_ratio?: string;
  duration_seconds?: number;
  quality?: "brouillon" | "finale";
  publish_requested?: boolean;
  location_name?: string | null;
  location_city?: string | null;
  location_type?: TypeLieu | null;
  highlight_name?: string | null;
  hook?: string | null;
  call_to_action?: string | null;
  hashtags?: string[];
  monetization_track?: TrackMonetisation;
  ai_disclosure?: boolean;
  source_job?: string | null;
}

function defaultsMedia(format: FormatLuna): {
  media_type: "auto" | "photo" | "video";
  aspect_ratio: string;
  duration_seconds: number;
} {
  if (format === "feed_photo") return { media_type: "photo", aspect_ratio: "3:4", duration_seconds: 1 };
  if (format === "story" || format === "highlight_story") {
    return { media_type: "video", aspect_ratio: "9:16", duration_seconds: 10 };
  }
  if (format === "reel" || format === "tiktok_short") {
    return { media_type: "video", aspect_ratio: "9:16", duration_seconds: 10 };
  }
  if (format === "tiktok_rewards") {
    return { media_type: "video", aspect_ratio: "9:16", duration_seconds: 60 };
  }
  if (format === "tiktok_photo") return { media_type: "photo", aspect_ratio: "3:4", duration_seconds: 1 };
  return { media_type: "auto", aspect_ratio: "3:4", duration_seconds: 10 };
}

export async function demanderGeneration(
  demande: string,
  options: DemandeMediaLuna = {},
): Promise<void> {
  const content_format = options.content_format ?? "legacy";
  const d = defaultsMedia(content_format);
  const row: Record<string, unknown> = {
    demande: demande.trim(),
    media_type: options.media_type ?? d.media_type,
    aspect_ratio: options.aspect_ratio ?? d.aspect_ratio,
    duration_seconds: options.duration_seconds ?? d.duration_seconds,
    quality: options.quality ?? "finale",
    publish_requested: options.publish_requested ?? true,
    content_format,
    platform: options.platform ?? "instagram",
    scheduled_at: options.scheduled_at ?? null,
    timezone: "Europe/Paris",
    location_name: options.location_name ?? null,
    location_city: options.location_city ?? null,
    location_type: options.location_type ?? null,
    highlight_name: options.highlight_name ?? null,
    hook: options.hook ?? null,
    call_to_action: options.call_to_action ?? null,
    hashtags: options.hashtags ?? [],
    ai_disclosure: options.ai_disclosure ?? true,
    monetization_track: options.monetization_track ?? "growth",
  };
  if (options.reference_path) row.reference_path = options.reference_path;
  if (options.source_job) row.source_job = options.source_job;

  const { error } = await supabase.from("luna_publications").insert(row);
  if (error) throw error;
}

const CACHE_URLS = new Map<string, { url: string; expire: number }>();

export async function urlSignee(cheminStockage: string): Promise<string | null> {
  const dejaConnue = CACHE_URLS.get(cheminStockage);
  if (dejaConnue && dejaConnue.expire > Date.now()) return dejaConnue.url;
  const { data, error } = await supabase.storage
    .from("luna")
    .createSignedUrl(cheminStockage, 3600);
  if (error || !data) return null;
  CACHE_URLS.set(cheminStockage, { url: data.signedUrl, expire: Date.now() + 55 * 60 * 1000 });
  return data.signedUrl;
}

export interface PerformanceLuna {
  publication_id: string;
  platform: string;
  measured_at: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  watch_time_seconds: number;
  completion_rate: number | null;
  followers_delta: number;
  revenue_eur: number;
  qualified_views: number;
  sponsored: boolean;
}

const COLONNES_PERFORMANCE =
  "publication_id, platform, measured_at, views, likes, comments, shares, saves, watch_time_seconds, completion_rate, followers_delta, revenue_eur, qualified_views, sponsored";

export async function performances(limite = 250): Promise<PerformanceLuna[]> {
  const { data, error } = await supabase
    .from("luna_performance")
    .select(COLONNES_PERFORMANCE)
    .order("measured_at", { ascending: false })
    .limit(limite);
  if (error) {
    if (/relation .* does not exist/i.test(error.message)) return [];
    throw error;
  }
  return (data ?? []) as unknown as PerformanceLuna[];
}
