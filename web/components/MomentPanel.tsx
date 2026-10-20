"use client";

import { Lightbulb, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getExplanation } from "@/lib/api";
import { MOMENT_META } from "@/lib/format";
import type { ExplainResult, Moment } from "@/lib/types";
import { ErrorNotice, QualityBadge, Spinner } from "./Bits";
import { CiteChips } from "./CiteChips";
import { MomentIcon } from "./MomentsTimeline";
import type { Settings } from "./RecapPanel";
import { ValidationReportView } from "./ValidationReportView";

const LABELS: Record<string, string> = {
  goal_kind: "Kind",
  scorer: "Scorer",
  assist: "Assist",
  xg: "Shot xG",
  result_change: "Effect",
  buildup_passes: "Build-up passes",
  outcome: "Outcome",
  shot_type: "Shot type",
  card: "Card",
  previous_leader: "Previous leader",
  new_leader: "New leader",
  window_minutes: "Window (min)",
  held_minutes: "Held for (min)",
  span_seconds: "Span (s)",
  winner: "Winner",
};

function fmt(v: unknown): string | null {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "string") return v.replaceAll("_", " ");
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v) && v.every((x) => typeof x === "string")) return v.join(", ");
  return null;
}

/** The handful of facts worth showing for a moment, in plain labels. */
function statRows(m: Moment): [string, string][] {
  const rows: [string, string][] = [];
  for (const [k, v] of Object.entries(m.stats)) {
    const label = LABELS[k];
    const text = label ? fmt(v) : null;
    if (label && text) rows.push([label, text]);
  }
  const s = m.stats as Record<string, unknown>;
  if (m.type === "substitution_impact") {
    rows.push(["Off", fmt(s.off) ?? ""], ["On", fmt(s.on) ?? ""]);
  }
  if (m.type === "quick_response" && Array.isArray(s.reasons)) rows.push(["Pattern", (s.reasons as string[]).join(", ").replaceAll("_", " ")]);
  return rows.filter(([, v]) => v);
}

export function MomentPanel({
  matchId,
  moment,
  settings,
  home,
  away,
  byId,
  onClose,
  onCite,
}: {
  matchId: number;
  moment: Moment;
  settings: Settings;
  home: string;
  away: string;
  byId: Map<string, Moment>;
  onClose: () => void;
  onCite: (id: string) => void;
}) {
  const key = `${moment.id}|${settings.audience}|${settings.language}`;
  const [results, setResults] = useState<Record<string, ExplainResult>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<{ key: string; err: unknown } | null>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  async function explain() {
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    setLoading(key);
    setError(null);
    try {
      const res = await getExplanation(matchId, moment.id, settings.audience, settings.language, ctl.signal);
      setResults((r) => ({ ...r, [key]: res }));
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) setError({ key, err });
    } finally {
      if (abort.current === ctl) setLoading(null);
    }
  }

  const res = results[key];
  const rows = statRows(moment);
  const [bh, ba] = moment.score_before;
  const [ah, aa] = moment.score_after;

  return (
    <aside aria-label="Selected moment" data-testid="moment-panel" className="card mb-4 border-accent/30 p-4">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line bg-bg">
          <MomentIcon type={moment.type} className="h-[18px] w-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted">
            <span className="display text-base font-semibold text-ink">{moment.clock_label}</span> · {MOMENT_META[moment.type].label}
          </p>
          <p className="mt-1 text-sm font-medium leading-snug" data-testid="moment-headline">{moment.headline}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close moment" className="rounded-md p-1 text-muted hover:bg-panel2 hover:text-ink">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div className="col-span-2 flex items-baseline justify-between rounded-lg bg-bg/70 px-3 py-2">
          <span className="text-muted">Score</span>
          <span className="display text-lg font-semibold tabular-nums">
            {bh === ah && ba === aa ? `${home} ${ah}-${aa} ${away}` : `${bh}-${ba} → ${ah}-${aa}`}
          </span>
        </div>
        <div className="col-span-2 flex items-center justify-between text-muted">
          <span>Importance</span>
          <span className="tabular-nums text-ink">{moment.importance.toFixed(2)}</span>
        </div>
        {rows.map(([k, v]) => (
          <div key={k} className="col-span-2 flex justify-between gap-4 border-t border-line/70 pt-2">
            <span className="text-muted">{k}</span>
            <span className="text-right text-ink">{v}</span>
          </div>
        ))}
      </div>

      <div className="mt-4">
        {!res && loading !== key && (
          <button
            type="button"
            data-testid="explain-button"
            onClick={explain}
            className="inline-flex items-center gap-2 rounded-lg border border-accent/50 px-3 py-2 text-sm font-medium text-accent hover:bg-accent/10"
          >
            <Lightbulb className="h-4 w-4" aria-hidden /> Explain this moment
          </button>
        )}
        {loading === key && (
          <p role="status" data-testid="explain-loading" className="flex items-center gap-2 text-xs text-muted">
            <Spinner className="h-4 w-4 text-accent" /> Explaining on this computer, usually under 20 seconds{settings.language !== "en" ? " (longer in Hindi or Tamil)" : ""}…
          </p>
        )}
        {error && error.key === key && <ErrorNotice error={error.err} onRetry={explain} />}
        {res && (
          <div data-testid="explain-result" className="space-y-3">
            <div className="flex items-center gap-2"><span className="text-xs uppercase tracking-wider text-muted">Why it mattered</span><QualityBadge quality={res.quality} /></div>
            <div lang={res.explanation.language ?? res.language}>
              <p className="text-sm leading-relaxed">{res.explanation.why_it_mattered}</p>
              <p className="mt-2 text-sm leading-relaxed text-ink/80">{res.explanation.context}</p>
            </div>
            {res.explanation.notes.map((n, i) => (
              <p key={i} className="rounded-md border border-amber/30 bg-amber/5 px-2.5 py-1.5 text-xs text-amber">{n}</p>
            ))}
            <CiteChips cites={res.explanation.cites} byId={byId} onCite={onCite} />
            <ValidationReportView report={res.report} model={res.model} seconds={res.generation_seconds} cached={res.cached} quality={res.quality} noun="explanation" />
          </div>
        )}
      </div>
    </aside>
  );
}
