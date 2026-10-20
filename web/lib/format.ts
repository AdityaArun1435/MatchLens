import { ArrowLeftRight, CircleDot, Crosshair, Square, Target, TrendingUp, Zap, type LucideIcon } from "lucide-react";
import type { Audience, Language, Moment, MomentType, Quality } from "./types";

export const MOMENT_META: Record<MomentType, { label: string; icon: LucideIcon; tone: string }> = {
  goal: { label: "Goal", icon: CircleDot, tone: "text-accent" },
  big_chance_missed: { label: "Big chance missed", icon: Crosshair, tone: "text-amber" },
  red_card: { label: "Red card", icon: Square, tone: "text-danger" },
  second_yellow: { label: "Second yellow", icon: Square, tone: "text-amber" },
  momentum_swing: { label: "Momentum swing", icon: TrendingUp, tone: "text-home" },
  substitution_impact: { label: "Substitution", icon: ArrowLeftRight, tone: "text-muted" },
  penalty_shootout: { label: "Penalty shootout", icon: Target, tone: "text-accent" },
  quick_response: { label: "Quick response", icon: Zap, tone: "text-amber" },
};

export const AUDIENCES: { id: Audience; label: string }[] = [
  { id: "analyst", label: "Analyst" },
  { id: "broadcaster", label: "Broadcaster" },
  { id: "fan", label: "Fan" },
];

export const LANGUAGES: { id: Language; label: string; native: string }[] = [
  { id: "en", label: "EN", native: "English" },
  { id: "hi", label: "HI", native: "हिन्दी" },
  { id: "ta", label: "TA", native: "தமிழ்" },
];

export const QUALITY: Record<Quality, { label: string; hint: string; className: string }> = {
  stable: { label: "Stable", hint: "Written in English and checked against the match data.", className: "border-accent/40 bg-accent/10 text-accent" },
  "machine-translated": {
    label: "Machine-translated",
    hint: "Translated by the local model from the checked English. Numbers, names and football terms are verified; grammar and nuance are not.",
    className: "border-amber/40 bg-amber/10 text-amber",
  },
  experimental: {
    label: "Experimental",
    hint: "Tamil from this model can change meaning even when every number and name is right. Read it with care.",
    className: "border-danger/50 bg-danger/10 text-danger",
  },
};

export function sideColor(team: string | null, home: string): string {
  return team === home ? "text-home" : "text-away";
}

export function scoreLine(m: Moment, home: string, away: string): string {
  const [h, a] = m.score_after;
  return `${home} ${h}-${a} ${away}`;
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

/** "Paragraph 4: number 0.78 ..." -> { where: "Paragraph 4", text: "number 0.78 ..." } */
export function splitError(e: string): { where: string | null; text: string } {
  const m = /^((?:Paragraph \d+|Title)):\s*([\s\S]*)$/.exec(e);
  return m ? { where: m[1], text: m[2] } : { where: null, text: e };
}
