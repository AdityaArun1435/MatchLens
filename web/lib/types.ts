// Shapes returned by the MatchLens FastAPI backend (matchlens/api.py and matchlens/models.py).

export type Audience = "analyst" | "broadcaster" | "fan";
export type Language = "en" | "hi" | "ta";
export type Length = "short" | "medium";
export type Quality = "stable" | "machine-translated" | "experimental";

export interface MatchListItem {
  match_id: number;
  competition: string;
  season: string;
  stage: string;
  date: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  stadium: string | null;
  went_to_extra_time: boolean;
  shootout_winner: string | null;
  moment_count: number;
}

export interface TimelinePoint {
  period: number;
  minute: number;
  label: string;
  xg: Record<string, number>;
  cumulative_xg: Record<string, number>;
}

export interface MatchSummary {
  meta: Omit<MatchListItem, "went_to_extra_time" | "shootout_winner" | "moment_count">;
  final_score: [number, number];
  score_after_90: [number, number];
  went_to_extra_time: boolean;
  shootout: { score: Record<string, number>; winner: string } | null;
  total_xg: Record<string, number>;
  shots: Record<string, number>;
  shots_on_target: Record<string, number>;
  possession_share: Record<string, number>;
  xg_timeline: TimelinePoint[];
}

export type MomentType =
  | "goal"
  | "big_chance_missed"
  | "red_card"
  | "second_yellow"
  | "momentum_swing"
  | "substitution_impact"
  | "penalty_shootout"
  | "quick_response";

export interface Moment {
  id: string;
  minute: number;
  clock_label: string;
  period: number;
  type: MomentType;
  team: string | null;
  player_display_names: string[];
  score_before: [number, number];
  score_after: [number, number];
  importance: number;
  headline: string;
  stats: Record<string, unknown>;
  first_index: number;
}

export interface RecapParagraph {
  text: string;
  cites: string[];
  language: string | null;
  note: string | null;
}

export interface AttemptReport {
  attempt: number;
  items_total: number;
  items_valid: number;
  errors: string[];
  llm_error: string | null;
}

export interface UnitTranslation {
  unit: string;
  status: "translated" | "english_fallback";
  attempts: number;
  errors: string[];
  notes: string[];
}

export interface TranslationReport {
  language: string;
  units: UnitTranslation[];
  names_added: string[];
  names_missing: string[];
  seconds: number;
  fallbacks: number;
  retries: number;
}

export interface ValidationReport {
  method: "llm" | "fallback";
  attempts: AttemptReport[];
  retried: boolean;
  dropped: { index: number; text: string; cites: string[]; errors: string[] }[];
  title_replaced: boolean;
  fallback_reason: string | null;
  notes: string[];
  translation: TranslationReport | null;
}

export interface RecapResult {
  match_id: number;
  audience: Audience;
  length: Length;
  language: Language;
  model: string;
  recap: { title: string; paragraphs: RecapParagraph[] };
  report: ValidationReport;
  generation_seconds: number;
  cached: boolean;
  source_recap: { title: string; paragraphs: RecapParagraph[] } | null;
  quality: Quality;
}

export interface ExplainResult {
  match_id: number;
  moment_id: string;
  audience: Audience;
  language: Language;
  model: string;
  explanation: { moment_id: string; why_it_mattered: string; context: string; cites: string[]; language: string | null; notes: string[] };
  report: ValidationReport;
  generation_seconds: number;
  cached: boolean;
  quality: Quality;
}

export interface Health {
  status: string;
  llm: { provider: string; model: string; available: boolean };
  quality: Record<Language, Quality>;
}
